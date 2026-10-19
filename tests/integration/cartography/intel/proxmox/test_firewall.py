"""
Integration tests for Proxmox firewall sync.
"""

from typing import Any
from unittest.mock import Mock
from unittest.mock import patch

import cartography.intel.proxmox.compute
import cartography.intel.proxmox.firewall
from tests.data.proxmox.compute import MOCK_VM_DATA
from tests.data.proxmox.firewall import MOCK_CLUSTER_FIREWALL_RULES
from tests.data.proxmox.firewall import MOCK_CLUSTER_IPSETS
from tests.data.proxmox.firewall import MOCK_CONTAINER_FIREWALL_RULES
from tests.data.proxmox.firewall import MOCK_IPSET_CIDRS
from tests.data.proxmox.firewall import MOCK_NODE_FIREWALL_RULES
from tests.data.proxmox.firewall import MOCK_VM_FIREWALL_RULES
from tests.integration.util import check_nodes
from tests.integration.util import check_rels

TEST_UPDATE_TAG = 123456789
TEST_CLUSTER_ID = "test-cluster"


@patch.object(
    cartography.intel.proxmox.firewall,
    "get_cluster_firewall_rules",
    return_value=MOCK_CLUSTER_FIREWALL_RULES,
)
@patch.object(cartography.intel.proxmox.firewall, "get_node_firewall_rules")
@patch.object(
    cartography.intel.proxmox.firewall,
    "get_cluster_ipsets",
    return_value=MOCK_CLUSTER_IPSETS,
)
@patch.object(cartography.intel.proxmox.firewall, "get_ipset_cidrs")
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
    cartography.intel.proxmox.firewall,
    "get_vm_firewall_rules",
    new=lambda _client, _node, vmid: MOCK_VM_FIREWALL_RULES.get(vmid, []),
)
@patch.object(
    cartography.intel.proxmox.firewall,
    "get_container_firewall_rules",
    new=lambda _client, _node, vmid: MOCK_CONTAINER_FIREWALL_RULES.get(vmid, []),
)
def test_sync_firewall(
    mock_get_ipset_cidrs,
    mock_get_ipsets,
    mock_get_node_rules,
    mock_get_cluster_rules,
    neo4j_session,
):
    """
    Test that firewall rules and IP sets sync correctly.
    """

    # Arrange
    def get_node_rules_side_effect(proxmox_client, node_name):
        return MOCK_NODE_FIREWALL_RULES.get(node_name, [])

    def get_ipset_cidrs_side_effect(proxmox_client, ipset_name):
        return MOCK_IPSET_CIDRS.get(ipset_name, [])

    mock_get_node_rules.side_effect = get_node_rules_side_effect
    mock_get_ipset_cidrs.side_effect = get_ipset_cidrs_side_effect

    common_job_parameters: dict[str, Any] = {
        "UPDATE_TAG": TEST_UPDATE_TAG,
        "CLUSTER_ID": TEST_CLUSTER_ID,
    }

    # Create cluster first
    neo4j_session.run(
        """
        MERGE (c:ProxmoxCluster {id: $cluster_id})
        SET c.name = $cluster_id,
            c.lastupdated = $update_tag
        """,
        cluster_id=TEST_CLUSTER_ID,
        update_tag=TEST_UPDATE_TAG,
    )

    # Create nodes for relationship tests
    neo4j_session.run(
        """
        MERGE (n1:ProxmoxNode {id: 'test-cluster/node1'})
        SET n1.name = 'node1', n1.lastupdated = $update_tag
        MERGE (n2:ProxmoxNode {id: 'test-cluster/node2'})
        SET n2.name = 'node2', n2.lastupdated = $update_tag
        """,
        update_tag=TEST_UPDATE_TAG,
    )

    # Create guests for the guest rule relationships: a QEMU VM and an LXC container
    neo4j_session.run(
        """
        MERGE (vm:ProxmoxVM {id: 'test-cluster/node1/qemu/100'})
        SET vm.vmid = 100, vm.type = 'qemu', vm.cluster_id = $cluster_id
        MERGE (ct:ProxmoxVM {id: 'test-cluster/node2/lxc/200'})
        SET ct.vmid = 200, ct.type = 'lxc', ct.cluster_id = $cluster_id
        """,
        cluster_id=TEST_CLUSTER_ID,
    )

    # Mock proxmox_client.nodes.get()
    mock_proxmox_client = Mock()
    mock_proxmox_client.nodes.get.return_value = [
        {"node": "node1"},
        {"node": "node2"},
    ]

    # Act
    cartography.intel.proxmox.firewall.sync(
        neo4j_session,
        mock_proxmox_client,
        TEST_CLUSTER_ID,
        TEST_UPDATE_TAG,
        common_job_parameters,
    )

    # Assert - Firewall rules exist (3 cluster + 2 node + 1 VM + 2 container)
    result = neo4j_session.run(
        """
        MATCH (rule:ProxmoxFirewallRule)
        RETURN count(rule) as count
        """
    )
    assert result.single()["count"] == 8

    # Assert - Cluster-scoped rules exist
    result = neo4j_session.run(
        """
        MATCH (rule:ProxmoxFirewallRule {scope: 'cluster'})
        RETURN rule.pos as pos, rule.action as action
        ORDER BY pos
        """
    )
    cluster_rules = [(r["pos"], r["action"]) for r in result]
    assert cluster_rules == [(0, "ACCEPT"), (1, "ACCEPT"), (2, "DROP")]

    # Assert - Node-scoped rules exist
    result = neo4j_session.run(
        """
        MATCH (rule:ProxmoxFirewallRule {scope: 'node', scope_id: 'node1'})
        RETURN rule.dport as dport, rule.comment as comment
        """
    )
    node1_rules = [(r["dport"], r["comment"]) for r in result]
    assert node1_rules == [("8006", "Proxmox web UI")]

    # Assert - IP sets exist
    expected_ipsets = {
        ("test-cluster/cluster:management-ips", "management-ips"),
        ("test-cluster/cluster:backup-servers", "backup-servers"),
    }
    assert (
        check_nodes(neo4j_session, "ProxmoxFirewallIPSet", ["id", "name"])
        == expected_ipsets
    )

    # Assert - IP set CIDR entries
    result = neo4j_session.run(
        """
        MATCH (ipset:ProxmoxFirewallIPSet {name: 'management-ips'})
        RETURN ipset.cidrs as cidrs
        """
    )
    cidrs = result.single()["cidrs"]
    assert set(cidrs) == {"10.0.1.0/24", "10.0.2.0/24"}

    # Assert - Firewall rule to cluster relationships
    result = neo4j_session.run(
        """
        MATCH (c:ProxmoxCluster)-[:RESOURCE]->(rule:ProxmoxFirewallRule)
        RETURN count(rule) as count
        """
    )
    assert result.single()["count"] == 8

    # Assert - Guest rules of the QEMU VM and of the LXC container
    assert check_nodes(
        neo4j_session,
        "ProxmoxFirewallRule",
        ["id", "scope", "scope_id", "dport"],
    ) >= {
        ("test-cluster/vm:100:0", "vm", "100", "443"),
        ("test-cluster/vm:200:0", "vm", "200", "5432"),
        ("test-cluster/vm:200:1", "vm", "200", None),
    }
    assert check_rels(
        neo4j_session,
        "ProxmoxFirewallRule",
        "id",
        "ProxmoxVM",
        "id",
        "APPLIES_TO_VM",
        rel_direction_right=True,
    ) == {
        ("test-cluster/vm:100:0", "test-cluster/node1/qemu/100"),
        ("test-cluster/vm:200:0", "test-cluster/node2/lxc/200"),
        ("test-cluster/vm:200:1", "test-cluster/node2/lxc/200"),
    }

    # Assert - Firewall rule to node relationships
    result = neo4j_session.run(
        """
        MATCH (rule:ProxmoxFirewallRule)-[:APPLIES_TO_NODE]->(n:ProxmoxNode)
        RETURN rule.scope_id as node_name, count(rule) as rule_count
        ORDER BY node_name
        """
    )
    node_rules = [(r["node_name"], r["rule_count"]) for r in result]
    assert node_rules == [("node1", 1), ("node2", 1)]

    # Assert - Rule properties
    result = neo4j_session.run(
        """
        MATCH (rule:ProxmoxFirewallRule {scope: 'cluster', pos: 0})
        RETURN rule.proto as proto, rule.dport as dport, rule.source as source, rule.enable as enable
        """
    )
    rule_props = result.single()
    assert rule_props["proto"] == "tcp"
    assert rule_props["dport"] == "22"
    assert rule_props["source"] == "10.0.0.0/8"
    assert rule_props["enable"] is True
