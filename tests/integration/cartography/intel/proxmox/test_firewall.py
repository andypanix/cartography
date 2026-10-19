"""
Integration tests for Proxmox firewall sync.
"""

from typing import Any
from unittest.mock import Mock
from unittest.mock import patch

import cartography.intel.proxmox.cluster
import cartography.intel.proxmox.compute
import cartography.intel.proxmox.firewall
from tests.data.proxmox.compute import MOCK_VM_DATA
from tests.data.proxmox.firewall import MOCK_CLUSTER_ALIASES
from tests.data.proxmox.firewall import MOCK_CLUSTER_FIREWALL_OPTIONS
from tests.data.proxmox.firewall import MOCK_CLUSTER_FIREWALL_RULES
from tests.data.proxmox.firewall import MOCK_CLUSTER_IPSETS
from tests.data.proxmox.firewall import MOCK_CONTAINER_FIREWALL_RULES
from tests.data.proxmox.firewall import MOCK_GUEST_ALIASES
from tests.data.proxmox.firewall import MOCK_GUEST_FIREWALL_OPTIONS
from tests.data.proxmox.firewall import MOCK_GUEST_IPSET_CIDRS
from tests.data.proxmox.firewall import MOCK_GUEST_IPSETS
from tests.data.proxmox.firewall import MOCK_IPSET_CIDRS
from tests.data.proxmox.firewall import MOCK_NODE_FIREWALL_OPTIONS
from tests.data.proxmox.firewall import MOCK_NODE_FIREWALL_RULES
from tests.data.proxmox.firewall import MOCK_SECURITY_GROUP_RULES
from tests.data.proxmox.firewall import MOCK_SECURITY_GROUPS
from tests.data.proxmox.firewall import MOCK_VM_FIREWALL_RULES
from tests.integration.util import check_nodes
from tests.integration.util import check_rels

TEST_UPDATE_TAG = 123456789
TEST_CLUSTER_ID = "test-cluster"
FW = cartography.intel.proxmox.firewall


def _rels(neo4j_session, source_label, rel_label, target_label):
    return check_rels(
        neo4j_session,
        source_label,
        "id",
        target_label,
        "id",
        rel_label,
        rel_direction_right=True,
    )


def _seed_graph(neo4j_session) -> None:
    """Create the cluster, nodes, and guests that the earlier sync steps load."""
    neo4j_session.run(
        """
        MERGE (c:ProxmoxCluster {id: $cluster_id})
        SET c.name = $cluster_id, c.lastupdated = $update_tag
        WITH c
        UNWIND ['node1', 'node2'] AS node_name
        MERGE (n:ProxmoxNode {id: $cluster_id + '/' + node_name})
        SET n.name = node_name, n.lastupdated = $update_tag
        MERGE (c)-[:RESOURCE]->(n)
        """,
        cluster_id=TEST_CLUSTER_ID,
        update_tag=TEST_UPDATE_TAG,
    )
    neo4j_session.run(
        """
        UNWIND $guests AS guest
        MERGE (vm:ProxmoxVM {id: $cluster_id + '/' + guest.path})
        SET vm.vmid = guest.vmid, vm.type = guest.type,
            vm.cluster_id = $cluster_id, vm.lastupdated = $update_tag
        """,
        guests=[
            {"path": f"{vm['node']}/{vm['type']}/{vm['vmid']}", **vm}
            for vms in MOCK_VM_DATA.values()
            for vm in vms
        ],
        cluster_id=TEST_CLUSTER_ID,
        update_tag=TEST_UPDATE_TAG,
    )


@patch.object(
    cartography.intel.proxmox.cluster,
    "get_nodes",
    return_value=[{"node": "node1"}, {"node": "node2"}],
)
@patch.object(
    cartography.intel.proxmox.compute,
    "get_vms_for_node",
    new=lambda _client, node: [
        vm for vm in MOCK_VM_DATA.get(node, []) if vm["type"] == "qemu"
    ],
)
@patch.object(
    cartography.intel.proxmox.compute,
    "get_containers_for_node",
    new=lambda _client, node: [
        vm for vm in MOCK_VM_DATA.get(node, []) if vm["type"] == "lxc"
    ],
)
@patch.object(
    FW, "get_cluster_firewall_rules", return_value=MOCK_CLUSTER_FIREWALL_RULES
)
@patch.object(
    FW,
    "get_node_firewall_rules",
    new=lambda _client, node: MOCK_NODE_FIREWALL_RULES.get(node, []),
)
@patch.object(
    FW,
    "get_vm_firewall_rules",
    new=lambda _client, _node, vmid: MOCK_VM_FIREWALL_RULES.get(vmid, []),
)
@patch.object(
    FW,
    "get_container_firewall_rules",
    new=lambda _client, _node, vmid: MOCK_CONTAINER_FIREWALL_RULES.get(vmid, []),
)
@patch.object(FW, "get_cluster_ipsets", return_value=MOCK_CLUSTER_IPSETS)
@patch.object(
    FW,
    "get_ipset_cidrs",
    new=lambda _client, name: MOCK_IPSET_CIDRS.get(name, []),
)
@patch.object(
    FW, "get_cluster_firewall_options", return_value=MOCK_CLUSTER_FIREWALL_OPTIONS
)
@patch.object(
    FW,
    "get_node_firewall_options",
    new=lambda _client, node: MOCK_NODE_FIREWALL_OPTIONS.get(node, {}),
)
@patch.object(
    FW,
    "get_guest_firewall_options",
    new=lambda _client, _node, _type, vmid: MOCK_GUEST_FIREWALL_OPTIONS.get(vmid, {}),
)
@patch.object(FW, "get_security_groups", return_value=MOCK_SECURITY_GROUPS)
@patch.object(
    FW,
    "get_security_group_rules",
    new=lambda _client, group: MOCK_SECURITY_GROUP_RULES.get(group, []),
)
@patch.object(FW, "get_cluster_aliases", return_value=MOCK_CLUSTER_ALIASES)
@patch.object(
    FW,
    "get_guest_aliases",
    new=lambda _client, _node, _type, vmid: MOCK_GUEST_ALIASES.get(vmid, []),
)
@patch.object(
    FW,
    "get_guest_ipsets",
    new=lambda _client, _node, _type, vmid: MOCK_GUEST_IPSETS.get(vmid, []),
)
@patch.object(
    FW,
    "get_guest_ipset_cidrs",
    new=lambda _client, _node, _type, vmid, name: MOCK_GUEST_IPSET_CIDRS.get(
        (vmid, name), []
    ),
)
def test_sync_firewall(
    _mock_get_aliases,
    _mock_get_groups,
    _mock_get_cluster_options,
    _mock_get_ipsets,
    _mock_get_cluster_rules,
    _mock_get_nodes,
    neo4j_session,
):
    """
    Firewall options, rules, security groups, aliases, and IP sets sync with
    their relationships.
    """
    # Arrange
    neo4j_session.run("MATCH (n) DETACH DELETE n")
    _seed_graph(neo4j_session)
    common_job_parameters: dict[str, Any] = {
        "UPDATE_TAG": TEST_UPDATE_TAG,
        "CLUSTER_ID": TEST_CLUSTER_ID,
    }

    # Act
    FW.sync(
        neo4j_session,
        Mock(),
        TEST_CLUSTER_ID,
        TEST_UPDATE_TAG,
        common_job_parameters,
    )

    # Assert - rules of every level, attached to the cluster
    expected_rules = {
        "test-cluster/cluster:0",
        "test-cluster/cluster:1",
        "test-cluster/cluster:2",
        "test-cluster/node:node1:0",
        "test-cluster/node:node2:0",
        "test-cluster/vm:100:0",
        "test-cluster/vm:100:1",
        "test-cluster/vm:200:0",
        "test-cluster/vm:200:1",
        "test-cluster/group:webserver:0",
        "test-cluster/group:webserver:1",
    }
    assert _rels(
        neo4j_session, "ProxmoxCluster", "RESOURCE", "ProxmoxFirewallRule"
    ) == {(TEST_CLUSTER_ID, rule_id) for rule_id in expected_rules}
    assert check_nodes(
        neo4j_session,
        "ProxmoxFirewallRule",
        ["id", "scope", "scope_id", "dport"],
    ) >= {
        ("test-cluster/vm:100:0", "vm", "100", "443"),
        ("test-cluster/vm:200:0", "vm", "200", "5432"),
        ("test-cluster/group:webserver:0", "group", "webserver", "80"),
    }
    assert _rels(
        neo4j_session, "ProxmoxFirewallRule", "APPLIES_TO_VM", "ProxmoxVM"
    ) == {
        ("test-cluster/vm:100:0", "test-cluster/node1/qemu/100"),
        ("test-cluster/vm:100:1", "test-cluster/node1/qemu/100"),
        ("test-cluster/vm:200:0", "test-cluster/node2/lxc/200"),
        ("test-cluster/vm:200:1", "test-cluster/node2/lxc/200"),
    }
    assert _rels(
        neo4j_session, "ProxmoxFirewallRule", "APPLIES_TO_NODE", "ProxmoxNode"
    ) == {
        ("test-cluster/node:node1:0", "test-cluster/node1"),
        ("test-cluster/node:node2:0", "test-cluster/node2"),
    }

    # Assert - security groups hold their rules and guest rules include them
    assert check_nodes(
        neo4j_session, "ProxmoxFirewallSecurityGroup", ["id", "name", "comment"]
    ) == {("test-cluster/group:webserver", "webserver", "HTTP and HTTPS")}
    assert _rels(
        neo4j_session,
        "ProxmoxFirewallSecurityGroup",
        "HAS_RULE",
        "ProxmoxFirewallRule",
    ) == {
        ("test-cluster/group:webserver", "test-cluster/group:webserver:0"),
        ("test-cluster/group:webserver", "test-cluster/group:webserver:1"),
    }
    assert _rels(
        neo4j_session,
        "ProxmoxFirewallRule",
        "USES_SECURITY_GROUP",
        "ProxmoxFirewallSecurityGroup",
    ) == {("test-cluster/vm:100:1", "test-cluster/group:webserver")}

    # Assert - cluster and guest IP sets, with nomatch entries kept apart
    assert check_nodes(
        neo4j_session,
        "ProxmoxFirewallIPSet",
        ["id", "scope", "scope_id", "name"],
    ) == {
        ("test-cluster/cluster:management-ips", "cluster", None, "management-ips"),
        ("test-cluster/cluster:backup-servers", "cluster", None, "backup-servers"),
        ("test-cluster/vm:100:backup-servers", "vm", "100", "backup-servers"),
    }
    management = neo4j_session.run(
        "MATCH (s:ProxmoxFirewallIPSet {id: 'test-cluster/cluster:management-ips'}) "
        "RETURN s.cidrs AS cidrs, s.nomatch_cidrs AS nomatch",
    ).single()
    assert set(management["cidrs"]) == {"10.0.1.0/24", "10.0.2.0/24"}
    assert management["nomatch"] == ["10.0.2.13"]
    assert _rels(
        neo4j_session, "ProxmoxVM", "HAS_FIREWALL_IPSET", "ProxmoxFirewallIPSet"
    ) == {("test-cluster/node1/qemu/100", "test-cluster/vm:100:backup-servers")}

    # Assert - cluster and guest aliases
    assert check_nodes(
        neo4j_session, "ProxmoxFirewallAlias", ["id", "scope", "cidr"]
    ) == {
        ("test-cluster/cluster:office", "cluster", "203.0.113.0/24"),
        ("test-cluster/vm:100:office", "vm", "198.51.100.10"),
    }
    assert _rels(
        neo4j_session, "ProxmoxVM", "HAS_FIREWALL_ALIAS", "ProxmoxFirewallAlias"
    ) == {("test-cluster/node1/qemu/100", "test-cluster/vm:100:office")}

    # Assert - rules point at the IP sets and aliases they name; guest
    # definitions win over cluster ones, and unknown names are skipped
    assert _rels(
        neo4j_session, "ProxmoxFirewallRule", "HAS_SOURCE", "ProxmoxFirewallIPSet"
    ) == {
        ("test-cluster/cluster:1", "test-cluster/cluster:management-ips"),
        ("test-cluster/group:webserver:0", "test-cluster/cluster:management-ips"),
    }
    assert _rels(
        neo4j_session,
        "ProxmoxFirewallRule",
        "HAS_DESTINATION",
        "ProxmoxFirewallIPSet",
    ) == {
        ("test-cluster/vm:100:0", "test-cluster/vm:100:backup-servers"),
        ("test-cluster/vm:200:0", "test-cluster/cluster:backup-servers"),
    }
    assert _rels(
        neo4j_session, "ProxmoxFirewallRule", "HAS_SOURCE", "ProxmoxFirewallAlias"
    ) == {
        ("test-cluster/node:node1:0", "test-cluster/cluster:office"),
        ("test-cluster/vm:100:0", "test-cluster/vm:100:office"),
    }
    assert (
        _rels(
            neo4j_session,
            "ProxmoxFirewallRule",
            "HAS_DESTINATION",
            "ProxmoxFirewallAlias",
        )
        == set()
    )

    # Assert - options are stored on the objects they configure, with the
    # documented defaults for options that are not set
    assert check_nodes(
        neo4j_session,
        "ProxmoxCluster",
        [
            "id",
            "firewall_enabled",
            "firewall_ebtables",
            "firewall_policy_in",
            "firewall_policy_forward",
        ],
    ) == {(TEST_CLUSTER_ID, True, True, "DROP", None)}
    assert check_nodes(
        neo4j_session,
        "ProxmoxNode",
        [
            "id",
            "name",
            "firewall_enabled",
            "firewall_log_level_in",
            "firewall_nftables",
            "firewall_nf_conntrack_max",
        ],
    ) == {
        ("test-cluster/node1", "node1", True, "info", True, 524288),
        ("test-cluster/node2", "node2", False, None, False, 262144),
    }
    assert check_nodes(
        neo4j_session,
        "ProxmoxVM",
        [
            "id",
            "vmid",
            "firewall_enabled",
            "firewall_policy_in",
            "firewall_ipfilter",
            "firewall_macfilter",
        ],
    ) == {
        ("test-cluster/node1/qemu/100", 100, True, "DROP", True, False),
        ("test-cluster/node1/qemu/101", 101, False, None, None, True),
        ("test-cluster/node2/lxc/200", 200, False, None, None, True),
    }


def test_guest_options_do_not_create_vm_nodes(neo4j_session):
    """
    Options of a guest that the compute sync did not load, such as one created
    during the sync, are not loaded, so no VM node holds only firewall options.
    """
    # Arrange
    neo4j_session.run("MATCH (n) DETACH DELETE n")
    _seed_graph(neo4j_session)
    known = f"{TEST_CLUSTER_ID}/node1/qemu/100"
    unknown = f"{TEST_CLUSTER_ID}/node1/qemu/999"
    guest_options = [
        FW.transform_firewall_options({"enable": 1}, FW.GUEST_FIREWALL_OPTIONS, vm_id)
        for vm_id in (known, unknown)
    ]
    cluster_options = FW.transform_firewall_options(
        {}, FW.CLUSTER_FIREWALL_OPTIONS, TEST_CLUSTER_ID
    )

    # Act
    FW.load_firewall_options(
        neo4j_session,
        cluster_options,
        [],
        guest_options,
        TEST_CLUSTER_ID,
        TEST_UPDATE_TAG,
    )

    # Assert
    vm_ids = {vm_id for (vm_id,) in check_nodes(neo4j_session, "ProxmoxVM", ["id"])}
    assert known in vm_ids
    assert unknown not in vm_ids
    assert check_nodes(neo4j_session, "ProxmoxVM", ["id", "firewall_enabled"]) >= {
        (known, True)
    }
