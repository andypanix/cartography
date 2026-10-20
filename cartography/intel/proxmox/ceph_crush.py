"""
Parse and transform the CRUSH map of a Proxmox VE Ceph cluster.

`GET /nodes/{node}/ceph/crush` returns the CRUSH map decompiled by
`crushtool -d` (pve-manager PVE/API2/Ceph.pm), a text in the format the Ceph
documentation describes under "CRUSH Maps" (rados/operations/crush-map-edits):

    # begin crush map
    tunable choose_total_tries 50
    # devices
    device 0 osd.0 class ssd
    # types
    type 0 osd
    type 1 host
    type 11 root
    # buckets
    host pve1 {
        id -3              # do not change unnecessarily
        id -4 class ssd    # do not change unnecessarily
        # weight 0.87329
        alg straw2
        hash 0             # rjenkins1
        item osd.0 weight 0.87329
    }
    root default { ... }
    # rules
    rule replicated_rule {
        id 0
        type replicated
        step take default
        step chooseleaf firstn 0 type host
        step emit
    }
    # choose_args
    choose_args 18446744073709551615 { ... }
    # end crush map

The parser is strict about the structure (statements, blocks, braces) and
raises CrushMapParseError on text it does not understand, so the caller can
skip the CRUSH data instead of loading a wrong topology. Unknown keys inside a
bucket or rule are ignored, so new Ceph options do not break the parse.
"""

import re
from dataclasses import dataclass
from dataclasses import field
from typing import Any

from cartography.intel.proxmox.util import cluster_scoped_id

_DEVICE_NAME = re.compile(r"^osd\.(\d+)$")
_WEIGHT_COMMENT = re.compile(r"^#\s*weight\s+(\S+)")


class CrushMapParseError(ValueError):
    """Raised when the decompiled CRUSH map text has an unexpected format."""


@dataclass
class CrushBucket:
    """One bucket of the CRUSH hierarchy, such as a host, rack or root."""

    name: str
    type: str
    bucket_id: int | None = None
    class_ids: dict[str, int] = field(default_factory=dict)
    weight: float | None = None
    alg: str | None = None
    hash: str | None = None
    # (item name, item weight) in map order
    items: list[tuple[str, float | None]] = field(default_factory=list)


@dataclass
class CrushRule:
    """One CRUSH rule with its placement steps."""

    name: str
    rule_id: int | None = None
    type: str | None = None
    min_size: int | None = None
    max_size: int | None = None
    steps: list[str] = field(default_factory=list)


@dataclass
class CrushMap:
    """The parts of a decompiled CRUSH map the graph needs."""

    tunables: dict[str, str] = field(default_factory=dict)
    # OSD number -> device class, None when the device has no class
    devices: dict[int, str | None] = field(default_factory=dict)
    # type name -> type number
    types: dict[str, int] = field(default_factory=dict)
    buckets: dict[str, CrushBucket] = field(default_factory=dict)
    rules: dict[str, CrushRule] = field(default_factory=dict)

    @property
    def device_classes(self) -> list[str]:
        return sorted({c for c in self.devices.values() if c})


def _strip_comment(line: str) -> str:
    return line.split("#", 1)[0].strip()


def _to_int(value: str, line: str) -> int:
    try:
        return int(value)
    except ValueError as e:
        raise CrushMapParseError(f"expected an integer in {line!r}") from e


def _to_float(value: str, line: str) -> float:
    try:
        return float(value)
    except ValueError as e:
        raise CrushMapParseError(f"expected a number in {line!r}") from e


def _block_header(line: str) -> tuple[str, str]:
    """Split a block header such as 'host pve1 {' into keyword and name."""
    tokens = line[:-1].split()
    if len(tokens) != 2:
        raise CrushMapParseError(f"unexpected block header {line!r}")
    return tokens[0], tokens[1]


def _parse_bucket_line(bucket: CrushBucket, raw: str, line: str) -> None:
    weight_comment = _WEIGHT_COMMENT.match(raw.strip())
    if weight_comment:
        bucket.weight = _to_float(weight_comment.group(1), raw)
        return
    if not line:
        return
    tokens = line.split()
    key = tokens[0]
    if key == "id":
        if len(tokens) == 2:
            bucket.bucket_id = _to_int(tokens[1], line)
        elif len(tokens) == 4 and tokens[2] == "class":
            bucket.class_ids[tokens[3]] = _to_int(tokens[1], line)
        else:
            raise CrushMapParseError(f"unexpected bucket id line {line!r}")
    elif key == "alg" and len(tokens) == 2:
        bucket.alg = tokens[1]
    elif key == "hash" and len(tokens) == 2:
        # hash 0 is rjenkins1, the only hash Ceph implements
        bucket.hash = "rjenkins1" if tokens[1] == "0" else tokens[1]
    elif key == "item":
        if len(tokens) < 2:
            raise CrushMapParseError(f"item without name in {line!r}")
        weight: float | None = None
        options = tokens[2:]
        for option, value in zip(options[::2], options[1::2]):
            if option == "weight":
                weight = _to_float(value, line)
        bucket.items.append((tokens[1], weight))
    # Other keys are ignored so that new bucket options do not fail the parse.


def _parse_rule_line(rule: CrushRule, line: str) -> None:
    if not line:
        return
    tokens = line.split()
    key = tokens[0]
    # "ruleset" is the rule number in maps written before Ceph Luminous.
    if key in ("id", "ruleset") and len(tokens) == 2:
        rule.rule_id = _to_int(tokens[1], line)
    elif key == "type" and len(tokens) == 2:
        rule.type = tokens[1]
    elif key == "min_size" and len(tokens) == 2:
        rule.min_size = _to_int(tokens[1], line)
    elif key == "max_size" and len(tokens) == 2:
        rule.max_size = _to_int(tokens[1], line)
    elif key == "step":
        if len(tokens) < 2:
            raise CrushMapParseError(f"empty rule step {line!r}")
        rule.steps.append(" ".join(tokens[1:]))


def parse_crush_map(text: Any) -> CrushMap:
    """
    Parse a CRUSH map decompiled by crushtool.

    :param text: Response of /nodes/{node}/ceph/crush
    :return: Parsed CRUSH map
    :raises CrushMapParseError: when the text is not a decompiled CRUSH map
    """
    if not isinstance(text, str) or not text.strip():
        raise CrushMapParseError("the CRUSH map is empty or not text")

    crush = CrushMap()
    # Block being read: ("bucket", CrushBucket), ("rule", CrushRule), or
    # ("skip", None) for choose_args, whose nested braces are not needed.
    block: tuple[str, Any] | None = None
    depth = 0
    for raw in text.splitlines():
        line = _strip_comment(raw)
        if block is not None:
            kind, current = block
            if kind == "skip":
                depth += line.count("{") - line.count("}")
                if depth < 0:
                    raise CrushMapParseError("unbalanced braces in choose_args")
                if depth == 0:
                    block = None
                continue
            if line == "}":
                block = None
                continue
            if "{" in line or "}" in line:
                raise CrushMapParseError(f"unexpected brace in {line!r}")
            if kind == "bucket":
                _parse_bucket_line(current, raw, line)
            else:
                _parse_rule_line(current, line)
            continue

        if not line:
            continue
        tokens = line.split()
        key = tokens[0]
        if key == "tunable":
            if len(tokens) != 3:
                raise CrushMapParseError(f"unexpected tunable line {line!r}")
            crush.tunables[tokens[1]] = tokens[2]
        elif key == "device":
            # device <num> <name> [class <class>]
            if len(tokens) not in (3, 5) or (len(tokens) == 5 and tokens[3] != "class"):
                raise CrushMapParseError(f"unexpected device line {line!r}")
            number = _to_int(tokens[1], line)
            # Maps written before Luminous list deleted OSDs as deviceN.
            if _DEVICE_NAME.match(tokens[2]):
                crush.devices[number] = tokens[4] if len(tokens) == 5 else None
        elif key == "type":
            if len(tokens) != 3:
                raise CrushMapParseError(f"unexpected type line {line!r}")
            crush.types[tokens[2]] = _to_int(tokens[1], line)
        elif line.endswith("{"):
            keyword, name = (key, "") if key == "choose_args" else _block_header(line)
            if keyword == "choose_args":
                block, depth = ("skip", None), 1
            elif keyword == "rule":
                if name in crush.rules:
                    raise CrushMapParseError(f"duplicate rule {name!r}")
                rule = CrushRule(name=name)
                crush.rules[name] = rule
                block = ("rule", rule)
            elif keyword in crush.types:
                if name in crush.buckets:
                    raise CrushMapParseError(f"duplicate bucket {name!r}")
                bucket = CrushBucket(name=name, type=keyword)
                crush.buckets[name] = bucket
                block = ("bucket", bucket)
            else:
                raise CrushMapParseError(f"unknown block type {keyword!r}")
        else:
            raise CrushMapParseError(f"unexpected line {line!r}")

    if block is not None:
        raise CrushMapParseError("the CRUSH map ends inside a block")
    if not crush.types:
        raise CrushMapParseError("the CRUSH map declares no bucket types")
    for bucket in crush.buckets.values():
        if bucket.bucket_id is None:
            raise CrushMapParseError(f"bucket {bucket.name!r} has no id")
        for item, _ in bucket.items:
            if item not in crush.buckets and not _DEVICE_NAME.match(item):
                raise CrushMapParseError(
                    f"bucket {bucket.name!r} holds unknown item {item!r}",
                )
    return crush


# ============================================================================
# TRANSFORM functions
# ============================================================================


def crush_bucket_graph_id(cluster_id: str, bucket_name: str) -> str:
    return cluster_scoped_id(cluster_id, f"crush_bucket:{bucket_name}")


def _take_targets(rule: CrushRule) -> list[tuple[str, str | None]]:
    """Return the (bucket, device class) of each 'take' step of a rule."""
    targets = []
    for step in rule.steps:
        tokens = step.split()
        if tokens[0] != "take" or len(tokens) < 2:
            continue
        device_class = None
        if len(tokens) >= 4 and tokens[2] == "class":
            device_class = tokens[3]
        targets.append((tokens[1], device_class))
    return targets


def _failure_domain(rule: CrushRule) -> str | None:
    """
    Return the bucket type of the first choose or chooseleaf step after a take.

    The first step picks the outermost failure domain: a rule that chooses
    racks and then hosts within each rack spreads its replicas across racks.
    """
    taken = False
    for step in rule.steps:
        tokens = step.split()
        if tokens[0] == "take":
            taken = True
            continue
        if taken and tokens[0].startswith("choose") and "type" in tokens:
            index = tokens.index("type")
            if index + 1 < len(tokens):
                return tokens[index + 1]
    return None


def transform_crush_rule_details(crush: CrushMap) -> dict[str, dict[str, Any]]:
    """
    Build the CRUSH rule properties the decompiled map adds, keyed by rule name.

    :param crush: Parsed CRUSH map
    :return: Dict of rule name to rule properties
    """
    details = {}
    for name, rule in crush.rules.items():
        targets = _take_targets(rule)
        classes = sorted({c for _, c in targets if c})
        details[name] = {
            "rule_id": rule.rule_id,
            "rule_type": rule.type,
            "min_size": rule.min_size,
            "max_size": rule.max_size,
            "take_buckets": sorted({b for b, _ in targets}) or None,
            "device_class": classes[0] if len(classes) == 1 else None,
            "device_classes": classes or None,
            "failure_domain": _failure_domain(rule),
            "steps": rule.steps or None,
        }
    return details


def transform_crush_buckets(
    crush: CrushMap,
    cluster_id: str,
    ceph_cluster_id: str,
    rule_graph_id: Any,
    osd_graph_id: Any,
) -> list[dict[str, Any]]:
    """
    Transform the CRUSH buckets, ordered so every child precedes its parent.

    The order lets one load link each bucket to the child buckets and OSDs it
    contains, which must already exist.

    :param crush: Parsed CRUSH map
    :param cluster_id: Proxmox VE cluster ID
    :param ceph_cluster_id: Graph ID of the Ceph cluster
    :param rule_graph_id: Function that builds the graph ID of a CRUSH rule
    :param osd_graph_id: Function that builds the graph ID of an OSD from its number
    :return: List of bucket dicts
    """
    rules_by_bucket: dict[str, set[str]] = {}
    for rule in crush.rules.values():
        for taken, _ in _take_targets(rule):
            rules_by_bucket.setdefault(taken, set()).add(rule.name)

    ordered: list[CrushBucket] = []
    seen: set[str] = set()

    def visit(name: str, chain: frozenset[str]) -> None:
        if name in seen or name in chain:
            return
        for item, _ in crush.buckets[name].items:
            if item in crush.buckets:
                visit(item, chain | {name})
        seen.add(name)
        ordered.append(crush.buckets[name])

    for name in sorted(crush.buckets):
        visit(name, frozenset())

    result = []
    for bucket in ordered:
        child_buckets = [i for i, _ in bucket.items if i in crush.buckets]
        osds = [
            int(match.group(1))
            for match in (_DEVICE_NAME.match(i) for i, _ in bucket.items)
            if match
        ]
        weight = bucket.weight
        if weight is None and bucket.items:
            weight = sum(w or 0.0 for _, w in bucket.items)
        result.append(
            {
                "id": crush_bucket_graph_id(cluster_id, bucket.name),
                "name": bucket.name,
                "cluster_id": cluster_id,
                "ceph_cluster_id": ceph_cluster_id,
                "bucket_id": bucket.bucket_id,
                "type": bucket.type,
                "type_id": crush.types.get(bucket.type),
                "weight": weight,
                "alg": bucket.alg,
                "hash": bucket.hash,
                "device_classes": sorted(bucket.class_ids) or None,
                "item_count": len(bucket.items),
                "child_bucket_ids": [
                    crush_bucket_graph_id(cluster_id, c) for c in child_buckets
                ],
                "osd_ids": [osd_graph_id(n) for n in osds],
                # A host bucket is named after the hostname of the node that
                # holds its OSDs, the Proxmox VE node name.
                "node_id": (
                    cluster_scoped_id(cluster_id, bucket.name)
                    if bucket.type == "host"
                    else None
                ),
                "rule_ids": sorted(
                    rule_graph_id(r) for r in rules_by_bucket.get(bucket.name, ())
                ),
            }
        )
    return result
