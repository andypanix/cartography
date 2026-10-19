"""
Sync Proxmox firewall configurations.

Follows Cartography's Get → Transform → Load pattern.
"""

import logging
import re
from typing import Any
from typing import NamedTuple

import neo4j

from cartography.client.core.tx import load
from cartography.client.core.tx import read_list_of_values_tx
from cartography.intel.proxmox import cluster
from cartography.intel.proxmox import compute
from cartography.intel.proxmox.util import cluster_scoped_id
from cartography.intel.proxmox.util import proxmox_api_retry
from cartography.models.proxmox.firewall import ProxmoxClusterFirewallOptionsSchema
from cartography.models.proxmox.firewall import ProxmoxFirewallAliasSchema
from cartography.models.proxmox.firewall import ProxmoxFirewallIPSetSchema
from cartography.models.proxmox.firewall import ProxmoxFirewallRuleSchema
from cartography.models.proxmox.firewall import ProxmoxFirewallSecurityGroupSchema
from cartography.models.proxmox.firewall import ProxmoxNodeFirewallOptionsSchema
from cartography.models.proxmox.firewall import ProxmoxVMFirewallOptionsSchema
from cartography.util import timeit

logger = logging.getLogger(__name__)

# Guest types whose firewall the sync reads. VM IDs are unique across both
# types in a cluster, so guest-level objects of both share the "vm" scope.
GUEST_TYPES = ("qemu", "lxc")

# Firewall options as (API key, value kind, Proxmox default). The default is
# the one documented in the Proxmox VE API schema; None when it documents none.
CLUSTER_FIREWALL_OPTIONS: tuple[tuple[str, str, Any], ...] = (
    ("enable", "bool", False),
    ("ebtables", "bool", True),
    ("policy_in", "str", None),
    ("policy_out", "str", None),
    ("policy_forward", "str", None),
    ("log_ratelimit", "str", None),
)

NODE_FIREWALL_OPTIONS: tuple[tuple[str, str, Any], ...] = (
    ("enable", "bool", True),
    ("log_level_in", "str", None),
    ("log_level_out", "str", None),
    ("log_level_forward", "str", None),
    ("log_nf_conntrack", "bool", False),
    ("ndp", "bool", True),
    ("nf_conntrack_allow_invalid", "bool", False),
    ("nf_conntrack_helpers", "str", None),
    ("nf_conntrack_max", "int", 262144),
    ("nf_conntrack_tcp_timeout_established", "int", 432000),
    ("nf_conntrack_tcp_timeout_syn_recv", "int", 60),
    ("nftables", "bool", False),
    ("nosmurfs", "bool", None),
    ("smurf_log_level", "str", None),
    ("tcpflags", "bool", False),
    ("tcp_flags_log_level", "str", None),
    ("protection_synflood", "bool", False),
    ("protection_synflood_burst", "int", 1000),
    ("protection_synflood_rate", "int", 200),
)

GUEST_FIREWALL_OPTIONS: tuple[tuple[str, str, Any], ...] = (
    ("enable", "bool", False),
    ("policy_in", "str", None),
    ("policy_out", "str", None),
    ("log_level_in", "str", None),
    ("log_level_out", "str", None),
    ("dhcp", "bool", False),
    ("ipfilter", "bool", None),
    ("macfilter", "bool", True),
    ("ndp", "bool", True),
    ("radv", "bool", None),
)

# Rule source and dest values that name an IP set or an alias instead of
# addresses. "dc/" points at the cluster definition, "guest/" at the guest's
# own one; without a prefix Proxmox looks in the guest first, then the cluster.
# "sdn/" IP sets belong to SDN VNets and are not resolved here.
_REFERENCE_NAME = r"[A-Za-z][A-Za-z0-9\-_]+"
IPSET_REFERENCE = re.compile(rf"^\+(?:(dc|guest|sdn)/)?({_REFERENCE_NAME})$")
ALIAS_REFERENCE = re.compile(rf"^(?:(dc|guest)/)?({_REFERENCE_NAME})$")

CLUSTER_SCOPE: tuple[str, str | None] = ("cluster", None)


class FirewallReferences(NamedTuple):
    """Transformed IP sets, aliases, and security groups that firewall rules can name."""

    ipsets: list[dict[str, Any]]
    aliases: list[dict[str, Any]]
    security_groups: list[dict[str, Any]]


# ============================================================================
# GET functions - retrieve data from Proxmox API
# ============================================================================


@timeit
@proxmox_api_retry
def get_cluster_firewall_rules(proxmox_client: Any) -> list[dict[str, Any]]:
    """
    Get cluster-level firewall rules.

    :param proxmox_client: Proxmox API client
    :return: List of firewall rule dicts
    :raises: Exception if API call fails
    """
    return proxmox_client.cluster.firewall.rules.get()


@timeit
@proxmox_api_retry
def get_node_firewall_rules(
    proxmox_client: Any, node_name: str
) -> list[dict[str, Any]]:
    """
    Get node-level firewall rules.

    :param proxmox_client: Proxmox API client
    :param node_name: Node name
    :return: List of firewall rule dicts
    :raises: Exception if API call fails
    """
    return proxmox_client.nodes(node_name).firewall.rules.get()


@timeit
@proxmox_api_retry
def get_vm_firewall_rules(
    proxmox_client: Any, node_name: str, vmid: int
) -> list[dict[str, Any]]:
    """
    Get VM-level firewall rules.

    :param proxmox_client: Proxmox API client
    :param node_name: Node name
    :param vmid: VM ID
    :return: List of firewall rule dicts
    :raises: Exception if API call fails
    """
    return proxmox_client.nodes(node_name).qemu(vmid).firewall.rules.get()


@timeit
@proxmox_api_retry
def get_container_firewall_rules(
    proxmox_client: Any, node_name: str, vmid: int
) -> list[dict[str, Any]]:
    """
    Get LXC container-level firewall rules.

    :param proxmox_client: Proxmox API client
    :param node_name: Node name
    :param vmid: Container ID
    :return: List of firewall rule dicts
    :raises: Exception if API call fails
    """
    return proxmox_client.nodes(node_name).lxc(vmid).firewall.rules.get()


@timeit
@proxmox_api_retry
def get_cluster_ipsets(proxmox_client: Any) -> list[dict[str, Any]]:
    """
    Get cluster-level IP sets.

    :param proxmox_client: Proxmox API client
    :return: List of IP set dicts
    :raises: Exception if API call fails
    """
    return proxmox_client.cluster.firewall.ipset.get()


@timeit
@proxmox_api_retry
def get_ipset_cidrs(proxmox_client: Any, ipset_name: str) -> list[dict[str, Any]]:
    """
    Get CIDR entries for a specific IP set.

    :param proxmox_client: Proxmox API client
    :param ipset_name: IP set name
    :return: List of CIDR entry dicts
    :raises: Exception if API call fails
    """
    return proxmox_client.cluster.firewall.ipset(ipset_name).get()


@timeit
@proxmox_api_retry
def get_cluster_firewall_options(proxmox_client: Any) -> dict[str, Any]:
    """
    Get cluster-wide firewall options.

    :param proxmox_client: Proxmox API client
    :return: Dict of the options that are set
    :raises: Exception if API call fails
    """
    return proxmox_client.cluster.firewall.options.get()


@timeit
@proxmox_api_retry
def get_node_firewall_options(proxmox_client: Any, node_name: str) -> dict[str, Any]:
    """
    Get host firewall options of a node.

    :param proxmox_client: Proxmox API client
    :param node_name: Node name
    :return: Dict of the options that are set
    :raises: Exception if API call fails
    """
    return proxmox_client.nodes(node_name).firewall.options.get()


@timeit
@proxmox_api_retry
def get_security_groups(proxmox_client: Any) -> list[dict[str, Any]]:
    """
    Get the security groups defined at cluster level.

    :param proxmox_client: Proxmox API client
    :return: List of security group dicts
    :raises: Exception if API call fails
    """
    return proxmox_client.cluster.firewall.groups.get()


@timeit
@proxmox_api_retry
def get_security_group_rules(
    proxmox_client: Any, group_name: str
) -> list[dict[str, Any]]:
    """
    Get the rules of a security group.

    :param proxmox_client: Proxmox API client
    :param group_name: Security group name
    :return: List of firewall rule dicts
    :raises: Exception if API call fails
    """
    return proxmox_client.cluster.firewall.groups(group_name).get()


@timeit
@proxmox_api_retry
def get_cluster_aliases(proxmox_client: Any) -> list[dict[str, Any]]:
    """
    Get the aliases defined at cluster level.

    :param proxmox_client: Proxmox API client
    :return: List of alias dicts
    :raises: Exception if API call fails
    """
    return proxmox_client.cluster.firewall.aliases.get()


def _guest_firewall(
    proxmox_client: Any, node_name: str, guest_type: str, vmid: int
) -> Any:
    """Return the firewall API resource of a QEMU VM or LXC container."""
    return proxmox_client.nodes(node_name)(guest_type)(vmid).firewall


@timeit
@proxmox_api_retry
def get_guest_firewall_options(
    proxmox_client: Any, node_name: str, guest_type: str, vmid: int
) -> dict[str, Any]:
    """
    Get firewall options of a QEMU VM or LXC container.

    :param proxmox_client: Proxmox API client
    :param node_name: Node name
    :param guest_type: qemu or lxc
    :param vmid: Guest ID
    :return: Dict of the options that are set
    :raises: Exception if API call fails
    """
    return _guest_firewall(proxmox_client, node_name, guest_type, vmid).options.get()


@timeit
@proxmox_api_retry
def get_guest_aliases(
    proxmox_client: Any, node_name: str, guest_type: str, vmid: int
) -> list[dict[str, Any]]:
    """
    Get the aliases defined in a QEMU VM or LXC container firewall.

    :param proxmox_client: Proxmox API client
    :param node_name: Node name
    :param guest_type: qemu or lxc
    :param vmid: Guest ID
    :return: List of alias dicts
    :raises: Exception if API call fails
    """
    return _guest_firewall(proxmox_client, node_name, guest_type, vmid).aliases.get()


@timeit
@proxmox_api_retry
def get_guest_ipsets(
    proxmox_client: Any, node_name: str, guest_type: str, vmid: int
) -> list[dict[str, Any]]:
    """
    Get the IP sets defined in a QEMU VM or LXC container firewall.

    :param proxmox_client: Proxmox API client
    :param node_name: Node name
    :param guest_type: qemu or lxc
    :param vmid: Guest ID
    :return: List of IP set dicts
    :raises: Exception if API call fails
    """
    return _guest_firewall(proxmox_client, node_name, guest_type, vmid).ipset.get()


@timeit
@proxmox_api_retry
def get_guest_ipset_cidrs(
    proxmox_client: Any,
    node_name: str,
    guest_type: str,
    vmid: int,
    ipset_name: str,
) -> list[dict[str, Any]]:
    """
    Get the entries of an IP set defined in a QEMU VM or LXC container firewall.

    :param proxmox_client: Proxmox API client
    :param node_name: Node name
    :param guest_type: qemu or lxc
    :param vmid: Guest ID
    :param ipset_name: IP set name
    :return: List of CIDR entry dicts
    :raises: Exception if API call fails
    """
    return (
        _guest_firewall(proxmox_client, node_name, guest_type, vmid)
        .ipset(ipset_name)
        .get()
    )


# ============================================================================
# TRANSFORM functions - manipulate data for graph ingestion
# ============================================================================


def transform_firewall_rule_data(
    rules: list[dict[str, Any]],
    cluster_id: str,
    scope: str,
    scope_id: str | None = None,
) -> list[dict[str, Any]]:
    """
    Transform firewall rule data into standard format.

    :param rules: Raw firewall rule data from API
    :param cluster_id: Parent cluster ID
    :param scope: Rule scope (cluster, node, vm, vnet, group)
    :param scope_id: Scope identifier (node name, vmid, VNet name, or security
        group name)
    :return: List of transformed firewall rule dicts
    """
    transformed_rules = []

    for rule in rules:
        # Create unique ID based on scope and position
        if scope_id:
            rule_id = f"{scope}:{scope_id}:{rule.get('pos', 0)}"
        else:
            rule_id = f"{scope}:{rule.get('pos', 0)}"
        rule_id = cluster_scoped_id(cluster_id, rule_id)

        transformed_rules.append(
            {
                "id": rule_id,
                "cluster_id": cluster_id,
                "scope": scope,
                "scope_id": scope_id,
                "pos": rule.get("pos", 0),
                "type": rule.get("type"),
                "action": rule.get("action"),
                "enable": bool(rule.get("enable", True)),  # Convert to bool
                "iface": rule.get("iface"),
                "source": rule.get("source"),
                "dest": rule.get("dest"),
                "proto": rule.get("proto"),
                "sport": rule.get("sport"),
                "dport": rule.get("dport"),
                "icmp_type": rule.get("icmp-type"),
                "ipversion": rule.get("ipversion"),
                "comment": rule.get("comment"),
                "macro": rule.get("macro"),
                "log": rule.get("log"),
                # Relationship targets: None unless the rule is scoped to a node or VM.
                "target_node_id": (
                    cluster_scoped_id(cluster_id, scope_id)
                    if scope == "node" and scope_id
                    else None
                ),
                "target_vmid": (
                    int(scope_id)
                    if scope == "vm" and scope_id and scope_id.isdigit()
                    else None
                ),
                "target_vnet_id": (
                    cluster_scoped_id(cluster_id, scope_id)
                    if scope == "vnet" and scope_id
                    else None
                ),
                "security_group_id": (
                    security_group_id(cluster_id, scope_id)
                    if scope == "group" and scope_id
                    else None
                ),
                # Set by resolve_rule_references once every referenced
                # object of the cluster is known.
                "uses_security_group_id": None,
                "source_ipset_id": None,
                "dest_ipset_id": None,
                "source_alias_id": None,
                "dest_alias_id": None,
            }
        )

    return transformed_rules


def transform_ipset_data(
    ipsets: list[dict[str, Any]],
    ipset_cidrs: dict[str, list[dict[str, Any]]],
    cluster_id: str,
    scope: str,
    scope_id: str | None = None,
    vm_id: str | None = None,
) -> list[dict[str, Any]]:
    """
    Transform IP set data into standard format.

    :param ipsets: Raw IP set data from API
    :param ipset_cidrs: Map of ipset name -> CIDR entries
    :param cluster_id: Parent cluster ID
    :param scope: IP set scope (cluster, vm)
    :param scope_id: Scope identifier (vmid for guest IP sets)
    :param vm_id: Graph ID of the guest that defines the IP set, if any
    :return: List of transformed IP set dicts
    """
    transformed_ipsets = []

    for ipset in ipsets:
        # Required field
        name = ipset["name"]

        # Create unique ID based on scope
        if scope_id:
            ipset_id = f"{scope}:{scope_id}:{name}"
        else:
            ipset_id = f"{scope}:{name}"
        ipset_id = cluster_scoped_id(cluster_id, ipset_id)

        # Entries flagged nomatch are excluded from the set, so keep them apart.
        cidrs = []
        nomatch_cidrs = []
        for cidr_entry in ipset_cidrs.get(name, []):
            if "cidr" not in cidr_entry:
                continue
            if cidr_entry.get("nomatch"):
                nomatch_cidrs.append(cidr_entry["cidr"])
            else:
                cidrs.append(cidr_entry["cidr"])

        transformed_ipsets.append(
            {
                "id": ipset_id,
                "name": name,
                "cluster_id": cluster_id,
                "scope": scope,
                "scope_id": scope_id,
                "comment": ipset.get("comment"),
                "cidrs": cidrs,
                "nomatch_cidrs": nomatch_cidrs,
                "vm_id": vm_id,
            }
        )

    return transformed_ipsets


def transform_alias_data(
    aliases: list[dict[str, Any]],
    cluster_id: str,
    scope: str,
    scope_id: str | None = None,
    vm_id: str | None = None,
) -> list[dict[str, Any]]:
    """
    Transform firewall alias data into standard format.

    :param aliases: Raw alias data from API
    :param cluster_id: Parent cluster ID
    :param scope: Alias scope (cluster, vm)
    :param scope_id: Scope identifier (vmid for guest aliases)
    :param vm_id: Graph ID of the guest that defines the alias, if any
    :return: List of transformed alias dicts
    """
    transformed_aliases = []
    for alias in aliases:
        name = alias["name"]
        natural_id = f"{scope}:{scope_id}:{name}" if scope_id else f"{scope}:{name}"
        transformed_aliases.append(
            {
                "id": cluster_scoped_id(cluster_id, natural_id),
                "name": name,
                "cluster_id": cluster_id,
                "scope": scope,
                "scope_id": scope_id,
                "cidr": alias.get("cidr"),
                "comment": alias.get("comment"),
                "vm_id": vm_id,
            }
        )
    return transformed_aliases


def security_group_id(cluster_id: str, group_name: str) -> str:
    """
    Build the graph ID of a security group.

    :param cluster_id: Parent cluster ID
    :param group_name: Security group name
    :return: ID in the form cluster_id/group:name
    """
    return cluster_scoped_id(cluster_id, f"group:{group_name}")


def transform_security_group_data(
    groups: list[dict[str, Any]],
    cluster_id: str,
) -> list[dict[str, Any]]:
    """
    Transform security group data into standard format.

    :param groups: Raw security group data from API
    :param cluster_id: Parent cluster ID
    :return: List of transformed security group dicts
    """
    return [
        {
            "id": security_group_id(cluster_id, group["group"]),
            "name": group["group"],
            "cluster_id": cluster_id,
            "comment": group.get("comment"),
        }
        for group in groups
    ]


def _option_value(value: Any, kind: str, default: Any) -> Any:
    """Convert one firewall option value, or return its default when unset."""
    if value is None or value == "":
        return default
    if kind == "bool":
        return bool(int(value))
    if kind == "int":
        return int(value)
    return value


def transform_firewall_options(
    options: dict[str, Any],
    spec: tuple[tuple[str, str, Any], ...],
    object_id: str,
) -> dict[str, Any]:
    """
    Transform firewall options into properties of the object they configure.

    Proxmox only returns the options that are set, so unset options take the
    default documented in the API schema.

    :param options: Raw firewall options from API
    :param spec: Option keys, value kinds, and defaults for this level
    :param object_id: Graph ID of the cluster, node, or guest
    :return: Dict of firewall_* properties keyed for the options schema
    """
    record: dict[str, Any] = {"id": object_id}
    for key, kind, default in spec:
        prop = "firewall_enabled" if key == "enable" else f"firewall_{key}"
        record[prop] = _option_value(options.get(key), kind, default)
    return record


def _resolve_reference(
    prefix: str | None,
    name: str,
    rule_scope: str,
    rule_scope_id: str | None,
    index: dict[tuple[str, str | None, str], str],
) -> str | None:
    """
    Find the graph ID of the IP set or alias a rule names, following Proxmox lookup order.

    Security group and node rules only see cluster definitions; guest rules
    see the guest's own definitions first.
    """
    guest_scope = ("vm", rule_scope_id) if rule_scope == "vm" else None
    if prefix == "dc":
        scopes = [CLUSTER_SCOPE]
    elif prefix == "guest":
        scopes = [guest_scope] if guest_scope else []
    elif prefix is None:
        scopes = [guest_scope, CLUSTER_SCOPE] if guest_scope else [CLUSTER_SCOPE]
    else:
        scopes = []

    # Proxmox stores alias and IP set names in lower case.
    for scope, scope_id in scopes:
        found = index.get((scope, scope_id, name.lower()))
        if found:
            return found
    return None


def resolve_rule_references(
    rules: list[dict[str, Any]],
    ipsets: list[dict[str, Any]],
    aliases: list[dict[str, Any]],
    security_groups: list[dict[str, Any]],
) -> None:
    """
    Link rules to the security groups, IP sets, and aliases they name.

    Sets uses_security_group_id, source_ipset_id, dest_ipset_id,
    source_alias_id, and dest_alias_id in place. References that do not match
    a synced object, such as SDN IP sets or the built-in local_network alias,
    stay unset.

    :param rules: Transformed rules
    :param ipsets: Transformed IP sets of the cluster and its guests
    :param aliases: Transformed aliases of the cluster and its guests
    :param security_groups: Transformed security groups
    """
    ipset_index = {
        (ipset["scope"], ipset["scope_id"], ipset["name"].lower()): ipset["id"]
        for ipset in ipsets
    }
    alias_index = {
        (alias["scope"], alias["scope_id"], alias["name"].lower()): alias["id"]
        for alias in aliases
    }
    group_index = {group["name"].lower(): group["id"] for group in security_groups}

    for rule in rules:
        if rule["type"] == "group" and rule["action"]:
            rule["uses_security_group_id"] = group_index.get(rule["action"].lower())

        for field in ("source", "dest"):
            value = rule.get(field)
            if not value:
                continue
            ipset_match = IPSET_REFERENCE.match(value)
            if ipset_match:
                rule[f"{field}_ipset_id"] = _resolve_reference(
                    ipset_match.group(1),
                    ipset_match.group(2),
                    rule["scope"],
                    rule["scope_id"],
                    ipset_index,
                )
                continue
            alias_match = ALIAS_REFERENCE.match(value)
            if alias_match:
                rule[f"{field}_alias_id"] = _resolve_reference(
                    alias_match.group(1),
                    alias_match.group(2),
                    rule["scope"],
                    rule["scope_id"],
                    alias_index,
                )


# ============================================================================
# LOAD functions - ingest data to Neo4j using modern data model
# ============================================================================


def load_firewall_rules(
    neo4j_session: neo4j.Session,
    rules: list[dict[str, Any]],
    cluster_id: str,
    update_tag: int,
) -> None:
    """
    Load firewall rule data into Neo4j using modern data model.

    :param neo4j_session: Neo4j session
    :param rules: List of transformed firewall rule dicts
    :param cluster_id: Parent cluster ID
    :param update_tag: Sync timestamp
    """
    if not rules:
        return

    load(
        neo4j_session,
        ProxmoxFirewallRuleSchema(),
        rules,
        lastupdated=update_tag,
        CLUSTER_ID=cluster_id,
    )


def load_ipsets(
    neo4j_session: neo4j.Session,
    ipsets: list[dict[str, Any]],
    cluster_id: str,
    update_tag: int,
) -> None:
    """
    Load IP set data into Neo4j using modern data model.

    :param neo4j_session: Neo4j session
    :param ipsets: List of transformed IP set dicts
    :param cluster_id: Parent cluster ID
    :param update_tag: Sync timestamp
    """
    if not ipsets:
        return

    load(
        neo4j_session,
        ProxmoxFirewallIPSetSchema(),
        ipsets,
        lastupdated=update_tag,
        CLUSTER_ID=cluster_id,
    )


def load_aliases(
    neo4j_session: neo4j.Session,
    aliases: list[dict[str, Any]],
    cluster_id: str,
    update_tag: int,
) -> None:
    """
    Load firewall aliases into Neo4j.

    :param neo4j_session: Neo4j session
    :param aliases: List of transformed alias dicts
    :param cluster_id: Parent cluster ID
    :param update_tag: Sync timestamp
    """
    if not aliases:
        return

    load(
        neo4j_session,
        ProxmoxFirewallAliasSchema(),
        aliases,
        lastupdated=update_tag,
        CLUSTER_ID=cluster_id,
    )


def load_security_groups(
    neo4j_session: neo4j.Session,
    groups: list[dict[str, Any]],
    cluster_id: str,
    update_tag: int,
) -> None:
    """
    Load firewall security groups into Neo4j.

    :param neo4j_session: Neo4j session
    :param groups: List of transformed security group dicts
    :param cluster_id: Parent cluster ID
    :param update_tag: Sync timestamp
    """
    if not groups:
        return

    load(
        neo4j_session,
        ProxmoxFirewallSecurityGroupSchema(),
        groups,
        lastupdated=update_tag,
        CLUSTER_ID=cluster_id,
    )


def load_firewall_options(
    neo4j_session: neo4j.Session,
    cluster_options: dict[str, Any],
    node_options: list[dict[str, Any]],
    guest_options: list[dict[str, Any]],
    cluster_id: str,
    update_tag: int,
) -> None:
    """
    Load firewall options onto the cluster, node, and guest nodes they configure.

    :param neo4j_session: Neo4j session
    :param cluster_options: Transformed cluster options
    :param node_options: Transformed options of each node
    :param guest_options: Transformed options of each guest
    :param cluster_id: Parent cluster ID
    :param update_tag: Sync timestamp
    """
    load(
        neo4j_session,
        ProxmoxClusterFirewallOptionsSchema(),
        [cluster_options],
        lastupdated=update_tag,
    )
    if node_options:
        load(
            neo4j_session,
            ProxmoxNodeFirewallOptionsSchema(),
            node_options,
            lastupdated=update_tag,
            CLUSTER_ID=cluster_id,
        )
    # Guest options are set on the VM nodes of the compute sync. A guest
    # created after that sync gets its options on the next sync, instead of a
    # VM node that holds only firewall options.
    known_vm_ids = set(
        neo4j_session.execute_read(
            read_list_of_values_tx,
            "MATCH (vm:ProxmoxVM) WHERE vm.id IN $VM_IDS RETURN vm.id",
            VM_IDS=[options["id"] for options in guest_options],
        ),
    )
    guest_options = [o for o in guest_options if o["id"] in known_vm_ids]
    if guest_options:
        load(
            neo4j_session,
            ProxmoxVMFirewallOptionsSchema(),
            guest_options,
            lastupdated=update_tag,
            CLUSTER_ID=cluster_id,
        )


# ============================================================================
# SYNC function - orchestrates Get → Transform → Load
# ============================================================================


def _get_guest_rules(
    proxmox_client: Any, node_name: str, guest_type: str, vmid: int
) -> list[dict[str, Any]]:
    if guest_type == "qemu":
        return get_vm_firewall_rules(proxmox_client, node_name, vmid)
    return get_container_firewall_rules(proxmox_client, node_name, vmid)


def _list_guests(proxmox_client: Any, node_name: str) -> list[dict[str, Any]]:
    return compute.get_vms_for_node(
        proxmox_client, node_name
    ) + compute.get_containers_for_node(proxmox_client, node_name)


@timeit
def sync(
    neo4j_session: neo4j.Session,
    proxmox_client: Any,
    cluster_id: str,
    update_tag: int,
    common_job_parameters: dict[str, Any],
) -> FirewallReferences:
    """
    Sync firewall configuration.

    Reads the options, rules, security groups, aliases, and IP sets of the
    cluster, its nodes, and its guests. Each guest costs four API calls plus
    one per IP set it defines.

    :param neo4j_session: Neo4j session
    :param proxmox_client: Proxmox API client
    :param cluster_id: Parent cluster ID
    :param update_tag: Sync timestamp
    :param common_job_parameters: Common parameters
    :return: The synced IP sets, aliases, and security groups, so that rules
        loaded by other syncs, such as SDN VNet rules, can link to them
    """
    logger.info("Syncing Proxmox firewall configuration")

    all_rules: list[dict[str, Any]] = []
    all_ipsets: list[dict[str, Any]] = []
    all_aliases: list[dict[str, Any]] = []
    node_options: list[dict[str, Any]] = []
    guest_options: list[dict[str, Any]] = []

    # GET - Cluster-level options, security groups, aliases, IP sets, and rules
    cluster_options = transform_firewall_options(
        get_cluster_firewall_options(proxmox_client),
        CLUSTER_FIREWALL_OPTIONS,
        cluster_id,
    )

    raw_groups = get_security_groups(proxmox_client)
    security_groups = transform_security_group_data(raw_groups, cluster_id)
    for group in raw_groups:
        all_rules.extend(
            transform_firewall_rule_data(
                get_security_group_rules(proxmox_client, group["group"]),
                cluster_id,
                "group",
                group["group"],
            )
        )

    all_aliases.extend(
        transform_alias_data(
            get_cluster_aliases(proxmox_client),
            cluster_id,
            "cluster",
        )
    )

    cluster_ipsets = get_cluster_ipsets(proxmox_client)
    ipset_cidrs = {
        ipset["name"]: get_ipset_cidrs(proxmox_client, ipset["name"])
        for ipset in cluster_ipsets
    }
    all_ipsets.extend(
        transform_ipset_data(cluster_ipsets, ipset_cidrs, cluster_id, "cluster")
    )

    all_rules.extend(
        transform_firewall_rule_data(
            get_cluster_firewall_rules(proxmox_client), cluster_id, "cluster"
        )
    )

    # GET - Node-level and guest-level firewall configuration
    for node in cluster.get_nodes(proxmox_client):
        node_name = node["node"]
        node_options.append(
            transform_firewall_options(
                get_node_firewall_options(proxmox_client, node_name),
                NODE_FIREWALL_OPTIONS,
                cluster_scoped_id(cluster_id, node_name),
            )
        )
        all_rules.extend(
            transform_firewall_rule_data(
                get_node_firewall_rules(proxmox_client, node_name),
                cluster_id,
                "node",
                node_name,
            )
        )

        # VM IDs are unique across QEMU VMs and LXC containers of a cluster,
        # so objects of both guest types share the vm scope.
        for guest in _list_guests(proxmox_client, node_name):
            guest_type = guest["type"]
            vmid = guest["vmid"]
            scope_id = str(vmid)
            vm_id = cluster_scoped_id(cluster_id, f"{node_name}/{guest_type}/{vmid}")

            all_rules.extend(
                transform_firewall_rule_data(
                    _get_guest_rules(proxmox_client, node_name, guest_type, vmid),
                    cluster_id,
                    "vm",
                    scope_id,
                )
            )
            guest_options.append(
                transform_firewall_options(
                    get_guest_firewall_options(
                        proxmox_client, node_name, guest_type, vmid
                    ),
                    GUEST_FIREWALL_OPTIONS,
                    vm_id,
                )
            )
            all_aliases.extend(
                transform_alias_data(
                    get_guest_aliases(proxmox_client, node_name, guest_type, vmid),
                    cluster_id,
                    "vm",
                    scope_id,
                    vm_id,
                )
            )
            guest_ipsets = get_guest_ipsets(proxmox_client, node_name, guest_type, vmid)
            guest_ipset_cidrs = {
                ipset["name"]: get_guest_ipset_cidrs(
                    proxmox_client, node_name, guest_type, vmid, ipset["name"]
                )
                for ipset in guest_ipsets
            }
            all_ipsets.extend(
                transform_ipset_data(
                    guest_ipsets,
                    guest_ipset_cidrs,
                    cluster_id,
                    "vm",
                    scope_id,
                    vm_id,
                )
            )

    resolve_rule_references(all_rules, all_ipsets, all_aliases, security_groups)

    # LOAD - referenced objects first so rule relationships find them
    load_firewall_options(
        neo4j_session,
        cluster_options,
        node_options,
        guest_options,
        cluster_id,
        update_tag,
    )
    load_security_groups(neo4j_session, security_groups, cluster_id, update_tag)
    load_aliases(neo4j_session, all_aliases, cluster_id, update_tag)
    load_ipsets(neo4j_session, all_ipsets, cluster_id, update_tag)
    load_firewall_rules(neo4j_session, all_rules, cluster_id, update_tag)

    logger.info(
        "Synced %d firewall rules, %d security groups, %d aliases, and %d IP sets",
        len(all_rules),
        len(security_groups),
        len(all_aliases),
        len(all_ipsets),
    )
    return FirewallReferences(all_ipsets, all_aliases, security_groups)
