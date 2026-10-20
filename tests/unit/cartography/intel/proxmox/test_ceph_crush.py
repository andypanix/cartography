"""
Unit tests for the Proxmox Ceph CRUSH map parser and transforms.
"""

from unittest.mock import MagicMock

import pytest
import requests
from proxmoxer.core import ResourceException

from cartography.intel.proxmox import ceph
from cartography.intel.proxmox import ceph_crush
from tests.data.proxmox.ceph import MOCK_CEPH_CRUSH_MAP

CLUSTER_ID = "test-cluster"
CEPH_ID = "test-cluster/fsid"

# A map written by an older Ceph: rules numbered with ruleset and limited by
# min_size and max_size, a deleted OSD listed as deviceN, no device classes.
LEGACY_CRUSH_MAP = """# begin crush map
tunable choose_total_tries 50

# devices
device 0 osd.0
device 1 device1
device 2 osd.2

# types
type 0 osd
type 1 host
type 10 root

# buckets
host pve-a {
\tid -2\t\t# do not change unnecessarily
\talg straw
\thash 0\t# rjenkins1
\titem osd.0 weight 1.000
\titem osd.2 weight 0.500 pos 1
}
root default {
\tid -1\t\t# do not change unnecessarily
\talg straw
\thash 0\t# rjenkins1
\titem pve-a weight 1.500
}

# rules
rule replicated_ruleset {
\truleset 0
\ttype replicated
\tmin_size 1
\tmax_size 10
\tstep take default
\tstep choose firstn 0 type osd
\tstep emit
}

# end crush map
"""


def test_parse_realistic_crush_map():
    # Act
    crush = ceph_crush.parse_crush_map(MOCK_CEPH_CRUSH_MAP)

    # Assert
    assert crush.tunables["choose_total_tries"] == "50"
    assert crush.devices == {0: "ssd", 1: "hdd"}
    assert crush.device_classes == ["hdd", "ssd"]
    assert crush.types["root"] == 11
    assert set(crush.buckets) == {"node1", "node2", "rack1", "default"}
    node1 = crush.buckets["node1"]
    assert node1.type == "host"
    assert node1.bucket_id == -3
    assert node1.class_ids == {"ssd": -4, "hdd": -7}
    assert node1.weight == 0.9
    assert node1.alg == "straw2"
    assert node1.hash == "rjenkins1"
    assert node1.items == [("osd.0", 0.9)]
    assert crush.buckets["rack1"].items == [("node1", 0.9), ("node2", 0.9)]
    rule = crush.rules["ssd_only"]
    assert rule.rule_id == 1
    assert rule.type == "replicated"
    assert rule.steps == [
        "take default class ssd",
        "chooseleaf firstn 0 type rack",
        "emit",
    ]


def test_parse_legacy_crush_map():
    # Act
    crush = ceph_crush.parse_crush_map(LEGACY_CRUSH_MAP)

    # Assert - deleted devices are dropped, ruleset is the rule ID
    assert crush.devices == {0: None, 2: None}
    assert crush.device_classes == []
    assert crush.buckets["pve-a"].weight is None
    assert crush.buckets["pve-a"].items == [("osd.0", 1.0), ("osd.2", 0.5)]
    rule = crush.rules["replicated_ruleset"]
    assert (rule.rule_id, rule.min_size, rule.max_size) == (0, 1, 10)


@pytest.mark.parametrize(
    "text",
    [
        None,
        "",
        "<html>Bad Gateway</html>",
        "type 1 host\nhost a {\n\talg straw2\n}\n",  # bucket without id
        "type 1 host\nhost a {\n\tid -1\n",  # ends inside a block
        "type 1 host\nhost a {\n\tid -1\n\titem ghost weight 1\n}\n",
        "type 1 host\nhost a {\n\tid -1\n\titem osd.0 weight heavy\n}\n",
        "type 1 host\nshelf a {\n\tid -1\n}\n",  # undeclared bucket type
        "device 0 osd.0 class\n",
        "choose_args 1 {\n  {\n}\n}\n}\n",  # unbalanced braces
        "tunable x 1\n",  # no types
    ],
)
def test_parse_crush_map_rejects_unexpected_text(text):
    with pytest.raises(ceph_crush.CrushMapParseError):
        ceph_crush.parse_crush_map(text)


def test_transform_crush_buckets_orders_children_first():
    # Arrange
    crush = ceph_crush.parse_crush_map(MOCK_CEPH_CRUSH_MAP)

    # Act
    buckets = ceph_crush.transform_crush_buckets(
        crush,
        CLUSTER_ID,
        CEPH_ID,
        lambda name: ceph.crush_rule_graph_id(CLUSTER_ID, name),
        lambda number: f"{CLUSTER_ID}/osd.{number}",
    )

    # Assert - every bucket comes after the buckets it contains
    names = [b["name"] for b in buckets]
    assert names.index("node1") < names.index("rack1") < names.index("default")
    assert names.index("node2") < names.index("rack1")
    by_name = {b["name"]: b for b in buckets}
    assert by_name["node1"] == {
        "id": "test-cluster/crush_bucket:node1",
        "name": "node1",
        "cluster_id": CLUSTER_ID,
        "ceph_cluster_id": CEPH_ID,
        "bucket_id": -3,
        "type": "host",
        "type_id": 1,
        "weight": 0.9,
        "alg": "straw2",
        "hash": "rjenkins1",
        "device_classes": ["hdd", "ssd"],
        "item_count": 1,
        "child_bucket_ids": [],
        "osd_ids": ["test-cluster/osd.0"],
        "node_id": "test-cluster/node1",
        "rule_ids": [],
    }
    assert by_name["rack1"]["child_bucket_ids"] == [
        "test-cluster/crush_bucket:node1",
        "test-cluster/crush_bucket:node2",
    ]
    assert by_name["rack1"]["node_id"] is None
    assert by_name["default"]["rule_ids"] == [
        "test-cluster/crush_rule:replicated_rule",
        "test-cluster/crush_rule:ssd_only",
    ]


def test_transform_crush_buckets_sums_item_weights_without_weight_comment():
    crush = ceph_crush.parse_crush_map(LEGACY_CRUSH_MAP)
    buckets = ceph_crush.transform_crush_buckets(crush, CLUSTER_ID, CEPH_ID, str, str)
    assert {b["name"]: b["weight"] for b in buckets} == {
        "pve-a": 1.5,
        "default": 1.5,
    }


def test_transform_crush_rule_details():
    details = ceph_crush.transform_crush_rule_details(
        ceph_crush.parse_crush_map(MOCK_CEPH_CRUSH_MAP),
    )
    assert details["ssd_only"] == {
        "rule_id": 1,
        "rule_type": "replicated",
        "min_size": None,
        "max_size": None,
        "take_buckets": ["default"],
        "device_class": "ssd",
        "device_classes": ["ssd"],
        "failure_domain": "rack",
        "steps": [
            "take default class ssd",
            "chooseleaf firstn 0 type rack",
            "emit",
        ],
    }
    assert details["replicated_rule"]["device_class"] is None
    assert details["replicated_rule"]["failure_domain"] == "host"


def test_transform_crush_rules_without_crush_map_leaves_details_empty():
    rules = ceph.transform_crush_rules([{"name": "r"}], CLUSTER_ID, CEPH_ID)
    assert rules[0]["rule_id"] is None
    assert rules[0]["steps"] is None


@pytest.mark.parametrize(
    "error",
    [
        ResourceException(500, "Internal Server Error", "crushtool failed"),
        requests.exceptions.ConnectionError("reset"),
    ],
)
def test_read_crush_map_skips_read_errors(monkeypatch, caplog, error):
    monkeypatch.setattr(ceph, "get_ceph_crush_map", MagicMock(side_effect=error))
    assert ceph._read_crush_map(MagicMock(), "node1") is None
    assert "Cannot read the Ceph CRUSH map from node node1" in caplog.text


def test_read_crush_map_skips_parse_errors(monkeypatch, caplog):
    monkeypatch.setattr(
        ceph, "get_ceph_crush_map", MagicMock(return_value="garbage line")
    )
    assert ceph._read_crush_map(MagicMock(), "node1") is None
    assert "Cannot parse the Ceph CRUSH map" in caplog.text


def test_read_crush_map_raises_unrelated_errors(monkeypatch):
    monkeypatch.setattr(
        ceph, "get_ceph_crush_map", MagicMock(side_effect=KeyError("bug"))
    )
    with pytest.raises(KeyError):
        ceph._read_crush_map(MagicMock(), "node1")
