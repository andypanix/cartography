"""
Tests for Proxmox firewall module.
"""

from unittest.mock import MagicMock

import pytest

from cartography.intel.proxmox.firewall import CLUSTER_FIREWALL_OPTIONS
from cartography.intel.proxmox.firewall import get_container_firewall_rules
from cartography.intel.proxmox.firewall import get_guest_ipset_cidrs
from cartography.intel.proxmox.firewall import GUEST_FIREWALL_OPTIONS
from cartography.intel.proxmox.firewall import NODE_FIREWALL_OPTIONS
from cartography.intel.proxmox.firewall import resolve_rule_references
from cartography.intel.proxmox.firewall import transform_alias_data
from cartography.intel.proxmox.firewall import transform_firewall_options
from cartography.intel.proxmox.firewall import transform_firewall_rule_data
from cartography.intel.proxmox.firewall import transform_ipset_data
from cartography.intel.proxmox.firewall import transform_security_group_data


def test_transform_firewall_rule_data():
    """Test firewall rule data transformation."""
    raw_rules = [
        {
            "pos": 0,
            "type": "in",
            "action": "ACCEPT",
            "enable": 1,
            "proto": "tcp",
            "dport": "22",
            "source": "10.0.0.0/8",
            "comment": "Allow SSH",
        },
        {
            "pos": 1,
            "type": "in",
            "action": "DROP",
            "enable": 0,
            "comment": "Drop disabled",
        },
    ]

    cluster_id = "test-cluster"

    # Test cluster-scoped rules
    result = transform_firewall_rule_data(raw_rules, cluster_id, "cluster")

    assert len(result) == 2

    # Test first rule
    rule1 = result[0]
    assert rule1["id"] == "test-cluster/cluster:0"
    assert rule1["scope"] == "cluster"
    assert rule1["scope_id"] is None
    assert rule1["pos"] == 0
    assert rule1["type"] == "in"
    assert rule1["action"] == "ACCEPT"
    assert rule1["enable"] is True
    assert rule1["proto"] == "tcp"
    assert rule1["dport"] == "22"
    assert rule1["source"] == "10.0.0.0/8"
    assert rule1["comment"] == "Allow SSH"

    # Test second rule
    rule2 = result[1]
    assert rule2["id"] == "test-cluster/cluster:1"
    assert rule2["enable"] is False
    assert rule2["action"] == "DROP"

    # Test node-scoped rules
    result_node = transform_firewall_rule_data(raw_rules, cluster_id, "node", "node1")

    rule_node = result_node[0]
    assert rule_node["id"] == "test-cluster/node:node1:0"
    assert rule_node["scope"] == "node"
    assert rule_node["scope_id"] == "node1"


def test_transform_ipset_data():
    """Test IP set data transformation."""
    raw_ipsets = [
        {
            "name": "management-ips",
            "comment": "Management network",
        },
        {
            "name": "backup-servers",
        },
    ]

    ipset_cidrs = {
        "management-ips": [
            {"cidr": "10.0.1.0/24"},
            {"cidr": "10.0.2.0/24"},
        ],
        "backup-servers": [
            {"cidr": "192.168.10.5/32"},
        ],
    }

    cluster_id = "test-cluster"

    # Test cluster-scoped IP sets
    result = transform_ipset_data(raw_ipsets, ipset_cidrs, cluster_id, "cluster")

    assert len(result) == 2

    # Test management-ips
    mgmt = next(s for s in result if s["name"] == "management-ips")
    assert mgmt["id"] == "test-cluster/cluster:management-ips"
    assert mgmt["scope"] == "cluster"
    assert mgmt["scope_id"] is None
    assert mgmt["comment"] == "Management network"
    assert mgmt["cidrs"] == ["10.0.1.0/24", "10.0.2.0/24"]
    assert mgmt["cluster_id"] == cluster_id

    # Test backup-servers
    backup = next(s for s in result if s["name"] == "backup-servers")
    assert backup["id"] == "test-cluster/cluster:backup-servers"
    assert backup["comment"] is None
    assert backup["cidrs"] == ["192.168.10.5/32"]

    # Test node-scoped IP sets
    result_node = transform_ipset_data(
        raw_ipsets, ipset_cidrs, cluster_id, "node", "node1"
    )

    ipset_node = result_node[0]
    assert ipset_node["id"] == "test-cluster/node:node1:management-ips"
    assert ipset_node["scope"] == "node"
    assert ipset_node["scope_id"] == "node1"


def test_transform_firewall_rule_data_sets_scope_targets():
    """Node and guest rules point at their node or VM; cluster rules point at neither."""
    rules = [{"pos": 0, "type": "in", "action": "ACCEPT"}]

    cluster_rule = transform_firewall_rule_data(rules, "c", "cluster")[0]
    node_rule = transform_firewall_rule_data(rules, "c", "node", "node1")[0]
    vm_rule = transform_firewall_rule_data(rules, "c", "vm", "100")[0]

    assert (cluster_rule["target_node_id"], cluster_rule["target_vmid"]) == (None, None)
    assert (node_rule["target_node_id"], node_rule["target_vmid"]) == ("c/node1", None)
    assert (vm_rule["target_node_id"], vm_rule["target_vmid"]) == (None, 100)


def test_get_container_firewall_rules_reads_lxc_path():
    """Container rules come from /nodes/{node}/lxc/{vmid}/firewall/rules."""
    # Arrange
    client = MagicMock()
    client.nodes.return_value.lxc.return_value.firewall.rules.get.return_value = [
        {"pos": 0}
    ]

    # Act
    rules = get_container_firewall_rules(client, "node2", 200)

    # Assert
    assert rules == [{"pos": 0}]
    client.nodes.assert_called_once_with("node2")
    client.nodes.return_value.lxc.assert_called_once_with(200)
    client.nodes.return_value.qemu.assert_not_called()


def test_transform_ipset_data_keeps_nomatch_entries_apart():
    """Entries flagged nomatch are excluded from the set, not members of it."""
    result = transform_ipset_data(
        [{"name": "trusted"}],
        {"trusted": [{"cidr": "10.0.0.0/8"}, {"cidr": "10.6.6.6", "nomatch": 1}]},
        "c",
        "vm",
        "100",
        "c/pve/qemu/100",
    )

    assert result[0]["id"] == "c/vm:100:trusted"
    assert result[0]["cidrs"] == ["10.0.0.0/8"]
    assert result[0]["nomatch_cidrs"] == ["10.6.6.6"]
    assert result[0]["vm_id"] == "c/pve/qemu/100"


def test_transform_alias_and_security_group_data():
    """Aliases and security groups get cluster-scoped IDs."""
    aliases = transform_alias_data(
        [{"name": "office", "cidr": "203.0.113.0/24", "digest": "x"}], "c", "cluster"
    )
    groups = transform_security_group_data([{"group": "web", "comment": "HTTP"}], "c")

    assert aliases == [
        {
            "id": "c/cluster:office",
            "name": "office",
            "cluster_id": "c",
            "scope": "cluster",
            "scope_id": None,
            "cidr": "203.0.113.0/24",
            "comment": None,
            "vm_id": None,
        },
    ]
    assert groups == [
        {"id": "c/group:web", "name": "web", "cluster_id": "c", "comment": "HTTP"},
    ]


def test_transform_firewall_rule_data_links_group_rules_to_their_group():
    """Rules read from a security group carry the ID of that group."""
    rule = transform_firewall_rule_data(
        [{"pos": 0, "type": "in", "action": "ACCEPT", "icmp-type": "echo-request"}],
        "c",
        "group",
        "web",
    )[0]

    assert rule["id"] == "c/group:web:0"
    assert rule["security_group_id"] == "c/group:web"
    assert rule["icmp_type"] == "echo-request"
    assert (rule["target_node_id"], rule["target_vmid"]) == (None, None)


def test_transform_firewall_options_applies_documented_defaults():
    """Unset options take the Proxmox default; set options are converted."""
    cluster = transform_firewall_options({}, CLUSTER_FIREWALL_OPTIONS, "c")
    node = transform_firewall_options(
        {"enable": 0, "nf_conntrack_max": "1000"}, NODE_FIREWALL_OPTIONS, "c/pve"
    )
    guest = transform_firewall_options(
        {"enable": 1, "policy_in": "DROP", "radv": 0},
        GUEST_FIREWALL_OPTIONS,
        "c/pve/qemu/100",
    )

    assert cluster["id"] == "c"
    assert cluster["firewall_enabled"] is False
    assert cluster["firewall_ebtables"] is True
    assert cluster["firewall_policy_in"] is None
    assert node["firewall_enabled"] is False
    assert node["firewall_nf_conntrack_max"] == 1000
    assert node["firewall_ndp"] is True
    assert guest["firewall_enabled"] is True
    assert guest["firewall_policy_in"] == "DROP"
    assert guest["firewall_radv"] is False
    assert guest["firewall_ipfilter"] is None
    assert guest["firewall_macfilter"] is True


@pytest.fixture
def referenced_objects():
    ipsets = transform_ipset_data(
        [{"name": "trusted"}], {}, "c", "cluster"
    ) + transform_ipset_data([{"name": "trusted"}], {}, "c", "vm", "100")
    aliases = transform_alias_data(
        [{"name": "office"}], "c", "cluster"
    ) + transform_alias_data([{"name": "db"}], "c", "vm", "100")
    groups = transform_security_group_data([{"group": "web"}], "c")
    return ipsets, aliases, groups


@pytest.mark.parametrize(
    ("scope", "scope_id", "source", "expected_ipset", "expected_alias"),
    [
        # Guest rules see their own definitions first, then the cluster ones
        ("vm", "100", "+trusted", "c/vm:100:trusted", None),
        ("vm", "100", "+dc/trusted", "c/cluster:trusted", None),
        ("vm", "100", "+guest/trusted", "c/vm:100:trusted", None),
        ("vm", "200", "+trusted", "c/cluster:trusted", None),
        ("vm", "200", "+guest/trusted", None, None),
        ("vm", "100", "db", None, "c/vm:100:db"),
        ("vm", "100", "guest/db", None, "c/vm:100:db"),
        ("vm", "100", "dc/db", None, None),
        ("vm", "100", "OFFICE", None, "c/cluster:office"),
        # Cluster, node, and group rules only see cluster definitions
        ("cluster", None, "+trusted", "c/cluster:trusted", None),
        ("node", "pve", "+guest/trusted", None, None),
        ("group", "web", "office", None, "c/cluster:office"),
        # Addresses, SDN IP sets, and unknown names are not resolved
        ("cluster", None, "10.0.0.0/8", None, None),
        ("cluster", None, "10.0.0.1,10.0.0.2", None, None),
        ("cluster", None, "+sdn/vnet1-all", None, None),
        ("cluster", None, "local_network", None, None),
    ],
)
def test_resolve_rule_references_follows_proxmox_lookup(
    referenced_objects, scope, scope_id, source, expected_ipset, expected_alias
):
    """Rule sources resolve to the IP set or alias Proxmox would use."""
    # Arrange
    ipsets, aliases, groups = referenced_objects
    rule = transform_firewall_rule_data(
        [{"pos": 0, "type": "in", "action": "ACCEPT", "source": source}],
        "c",
        scope,
        scope_id,
    )[0]

    # Act
    resolve_rule_references([rule], ipsets, aliases, groups)

    # Assert
    assert rule["source_ipset_id"] == expected_ipset
    assert rule["source_alias_id"] == expected_alias
    assert rule["dest_ipset_id"] is None
    assert rule["dest_alias_id"] is None


def test_resolve_rule_references_links_group_rules(referenced_objects):
    """A rule of type group uses the security group named in its action."""
    # Arrange
    ipsets, aliases, groups = referenced_objects
    rules = transform_firewall_rule_data(
        [
            {"pos": 0, "type": "group", "action": "web"},
            {"pos": 1, "type": "group", "action": "missing"},
            {"pos": 2, "type": "in", "action": "ACCEPT", "dest": "+trusted"},
        ],
        "c",
        "vm",
        "100",
    )

    # Act
    resolve_rule_references(rules, ipsets, aliases, groups)

    # Assert
    assert [r["uses_security_group_id"] for r in rules] == [
        "c/group:web",
        None,
        None,
    ]
    assert rules[2]["dest_ipset_id"] == "c/vm:100:trusted"


def test_get_guest_ipset_cidrs_reads_guest_path():
    """Guest IP set entries come from /nodes/{node}/{type}/{vmid}/firewall/ipset/{name}."""
    # Arrange
    client = MagicMock()
    guest = client.nodes.return_value.return_value.return_value
    guest.firewall.ipset.return_value.get.return_value = [{"cidr": "10.0.0.1"}]

    # Act
    entries = get_guest_ipset_cidrs(client, "pve", "lxc", 200, "trusted")

    # Assert
    assert entries == [{"cidr": "10.0.0.1"}]
    client.nodes.assert_called_once_with("pve")
    client.nodes.return_value.assert_called_once_with("lxc")
    client.nodes.return_value.return_value.assert_called_once_with(200)
    guest.firewall.ipset.assert_called_once_with("trusted")
