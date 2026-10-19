"""
Integration tests for Proxmox HA sync.
"""

from typing import Any
from unittest.mock import patch

from proxmoxer.core import ResourceException

import cartography.intel.proxmox.ha
from tests.data.proxmox.ha import MOCK_HA_GROUP_DATA
from tests.data.proxmox.ha import MOCK_HA_MANAGER_STATUS_DATA
from tests.data.proxmox.ha import MOCK_HA_RESOURCE_DATA
from tests.data.proxmox.ha import MOCK_HA_RESOURCE_DATA_PVE9
from tests.data.proxmox.ha import MOCK_HA_RULE_DATA
from tests.data.proxmox.ha import MOCK_HA_STATUS_DATA
from tests.integration.util import check_nodes
from tests.integration.util import check_rels

TEST_UPDATE_TAG = 123456789
TEST_CLUSTER_ID = "test-cluster"


@patch.object(cartography.intel.proxmox.ha, "get_ha_manager_status", return_value={})
@patch.object(cartography.intel.proxmox.ha, "get_ha_status", return_value=[])
@patch.object(cartography.intel.proxmox.ha, "get_ha_rules", return_value=[])
@patch.object(
    cartography.intel.proxmox.ha, "get_ha_groups", return_value=MOCK_HA_GROUP_DATA
)
@patch.object(
    cartography.intel.proxmox.ha, "get_ha_resources", return_value=MOCK_HA_RESOURCE_DATA
)
def test_sync_ha(
    mock_get_resources,
    mock_get_groups,
    mock_get_rules,
    mock_get_status,
    mock_get_manager_status,
    neo4j_session,
):
    """
    Test that HA groups and resources of Proxmox VE 8.4 sync correctly.
    """
    # Arrange
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

    # Create VMs for relationship tests
    neo4j_session.run(
        """
        MERGE (v1:ProxmoxVM {id: 'test-cluster/node1/qemu/100'})
        SET v1.vmid = 100, v1.cluster_id = 'test-cluster', v1.name = 'test-vm-1', v1.lastupdated = $update_tag
        MERGE (v2:ProxmoxVM {id: 'test-cluster/node1/qemu/101'})
        SET v2.vmid = 101, v2.cluster_id = 'test-cluster', v2.name = 'test-vm-2', v2.lastupdated = $update_tag
        MERGE (v3:ProxmoxVM {id: 'test-cluster/node2/lxc/200'})
        SET v3.vmid = 200, v3.cluster_id = 'test-cluster', v3.name = 'test-container-1', v3.lastupdated = $update_tag
        """,
        update_tag=TEST_UPDATE_TAG,
    )

    # Act
    cartography.intel.proxmox.ha.sync(
        neo4j_session,
        None,  # proxmox_client mocked
        TEST_CLUSTER_ID,
        TEST_UPDATE_TAG,
        common_job_parameters,
    )

    # Assert - HA groups exist
    expected_groups = {
        ("test-cluster/ha-group-1", "node1,node2"),
        ("test-cluster/ha-group-2", "node2"),
    }
    assert (
        check_nodes(neo4j_session, "ProxmoxHAGroup", ["id", "nodes"]) == expected_groups
    )

    # Assert - HA resources exist
    expected_resources = {
        ("test-cluster/vm:100", "started"),
        ("test-cluster/ct:200", "started"),
        ("test-cluster/vm:101", "stopped"),
    }
    assert (
        check_nodes(neo4j_session, "ProxmoxHAResource", ["id", "state"])
        == expected_resources
    )

    # Assert - HA group to cluster relationships
    expected_group_rels = {
        ("test-cluster/ha-group-1", TEST_CLUSTER_ID),
        ("test-cluster/ha-group-2", TEST_CLUSTER_ID),
    }
    assert (
        check_rels(
            neo4j_session,
            "ProxmoxHAGroup",
            "id",
            "ProxmoxCluster",
            "id",
            "RESOURCE",
            rel_direction_right=False,
        )
        == expected_group_rels
    )

    # Assert - HA resource to cluster relationships
    expected_resource_rels = {
        ("test-cluster/vm:100", TEST_CLUSTER_ID),
        ("test-cluster/ct:200", TEST_CLUSTER_ID),
        ("test-cluster/vm:101", TEST_CLUSTER_ID),
    }
    assert (
        check_rels(
            neo4j_session,
            "ProxmoxHAResource",
            "id",
            "ProxmoxCluster",
            "id",
            "RESOURCE",
            rel_direction_right=False,
        )
        == expected_resource_rels
    )

    # Assert - HA resource to HA group relationships
    expected_ha_group_rels = {
        ("test-cluster/vm:100", "test-cluster/ha-group-1"),
        ("test-cluster/ct:200", "test-cluster/ha-group-1"),
        ("test-cluster/vm:101", "test-cluster/ha-group-2"),
    }
    assert (
        check_rels(
            neo4j_session,
            "ProxmoxHAResource",
            "id",
            "ProxmoxHAGroup",
            "id",
            "MEMBER_OF_HA_GROUP",
            rel_direction_right=True,
        )
        == expected_ha_group_rels
    )

    # Assert - HA resource to VM relationships
    expected_vm_rels = {
        ("test-cluster/vm:100", "test-cluster/node1/qemu/100"),
        ("test-cluster/ct:200", "test-cluster/node2/lxc/200"),
        ("test-cluster/vm:101", "test-cluster/node1/qemu/101"),
    }
    assert (
        check_rels(
            neo4j_session,
            "ProxmoxHAResource",
            "id",
            "ProxmoxVM",
            "id",
            "PROTECTS",
            rel_direction_right=True,
        )
        == expected_vm_rels
    )

    # Assert - HA group properties (Proxmox API returns 0/1, stored as integers in Neo4j)
    result = neo4j_session.run(
        """
        MATCH (g:ProxmoxHAGroup {id: 'test-cluster/ha-group-2'})
        RETURN g.restricted as restricted, g.nofailback as nofailback
        """
    )
    record = result.single()
    assert record["restricted"] == 1  # Proxmox API returns 1 for true
    assert record["nofailback"] == 1  # Proxmox API returns 1 for true


@patch.object(
    cartography.intel.proxmox.ha,
    "get_ha_manager_status",
    return_value=MOCK_HA_MANAGER_STATUS_DATA,
)
@patch.object(
    cartography.intel.proxmox.ha, "get_ha_status", return_value=MOCK_HA_STATUS_DATA
)
@patch.object(
    cartography.intel.proxmox.ha, "get_ha_rules", return_value=MOCK_HA_RULE_DATA
)
@patch.object(
    cartography.intel.proxmox.ha,
    "get_ha_groups",
    side_effect=ResourceException(
        500,
        "cannot index groups: ha groups have been migrated to rules",
        "",
    ),
)
@patch.object(
    cartography.intel.proxmox.ha,
    "get_ha_resources",
    return_value=MOCK_HA_RESOURCE_DATA_PVE9,
)
def test_sync_ha_pve9_rules_and_status(
    mock_get_resources,
    mock_get_groups,
    mock_get_rules,
    mock_get_status,
    mock_get_manager_status,
    neo4j_session,
):
    """
    On Proxmox VE 9 with HA groups migrated to rules, the sync skips groups and
    loads HA rules, the HA manager, and one LRM per node.
    """
    # Arrange
    neo4j_session.run("MATCH (n) DETACH DELETE n")
    common_job_parameters: dict[str, Any] = {
        "UPDATE_TAG": TEST_UPDATE_TAG,
        "CLUSTER_ID": TEST_CLUSTER_ID,
    }
    neo4j_session.run(
        """
        MERGE (c:ProxmoxCluster {id: $cluster_id})
        SET c.lastupdated = $update_tag
        WITH c
        UNWIND ['node1', 'node2'] AS name
        MERGE (n:ProxmoxNode {id: $cluster_id + '/' + name})
        SET n.name = name, n.cluster_id = $cluster_id, n.lastupdated = $update_tag
        """,
        cluster_id=TEST_CLUSTER_ID,
        update_tag=TEST_UPDATE_TAG,
    )

    # Act
    cartography.intel.proxmox.ha.sync(
        neo4j_session,
        None,  # proxmox_client mocked
        TEST_CLUSTER_ID,
        TEST_UPDATE_TAG,
        common_job_parameters,
    )

    # Assert - no HA groups, resources carry failback
    assert check_nodes(neo4j_session, "ProxmoxHAGroup", ["id"]) == set()
    assert check_nodes(
        neo4j_session,
        "ProxmoxHAResource",
        ["id", "type", "failback", "auto_rebalance"],
    ) == {
        ("test-cluster/vm:100", "vm", True, None),
        ("test-cluster/ct:200", "ct", False, False),
        ("test-cluster/vm:101", "vm", None, None),
    }

    # Assert - HA rules
    assert check_nodes(
        neo4j_session,
        "ProxmoxHARule",
        ["id", "type", "affinity", "strict", "disable", "nodes"],
    ) == {
        (
            "test-cluster/ha-group-1",
            "node-affinity",
            "positive",
            False,
            False,
            "node1:2,node2",
        ),
        (
            "test-cluster/keep-apart",
            "resource-affinity",
            "negative",
            None,
            True,
            None,
        ),
    }
    assert check_rels(
        neo4j_session,
        "ProxmoxCluster",
        "id",
        "ProxmoxHARule",
        "id",
        "RESOURCE",
    ) == {
        (TEST_CLUSTER_ID, "test-cluster/ha-group-1"),
        (TEST_CLUSTER_ID, "test-cluster/keep-apart"),
    }
    assert check_rels(
        neo4j_session,
        "ProxmoxHARule",
        "id",
        "ProxmoxHAResource",
        "id",
        "APPLIES_TO_HA_RESOURCE",
    ) == {
        ("test-cluster/ha-group-1", "test-cluster/vm:100"),
        ("test-cluster/ha-group-1", "test-cluster/ct:200"),
        ("test-cluster/keep-apart", "test-cluster/vm:100"),
        ("test-cluster/keep-apart", "test-cluster/vm:101"),
    }
    assert check_rels(
        neo4j_session,
        "ProxmoxHARule",
        "id",
        "ProxmoxNode",
        "id",
        "APPLIES_TO_NODE",
    ) == {
        ("test-cluster/ha-group-1", "test-cluster/node1"),
        ("test-cluster/ha-group-1", "test-cluster/node2"),
    }

    # Assert - HA manager and its CRM master
    assert check_nodes(
        neo4j_session,
        "ProxmoxHAManager",
        ["id", "quorate", "master_node", "armed_state", "resource_mode"],
    ) == {("test-cluster/ha-manager", True, "node1", "armed", "freeze")}
    assert check_rels(
        neo4j_session,
        "ProxmoxCluster",
        "id",
        "ProxmoxHAManager",
        "id",
        "RESOURCE",
    ) == {(TEST_CLUSTER_ID, "test-cluster/ha-manager")}
    assert check_rels(
        neo4j_session,
        "ProxmoxHAManager",
        "id",
        "ProxmoxNode",
        "id",
        "CRM_MASTER",
    ) == {("test-cluster/ha-manager", "test-cluster/node1")}

    # Assert - one LRM per node
    assert check_nodes(
        neo4j_session,
        "ProxmoxHALRM",
        ["id", "status", "state", "mode", "crm_node_state"],
    ) == {
        ("test-cluster/lrm:node1", "active", "active", "active", "online"),
        (
            "test-cluster/lrm:node2",
            "maintenance mode",
            "wait_for_agent_lock",
            "maintenance",
            "maintenance",
        ),
    }
    assert check_rels(
        neo4j_session,
        "ProxmoxCluster",
        "id",
        "ProxmoxHALRM",
        "id",
        "RESOURCE",
    ) == {
        (TEST_CLUSTER_ID, "test-cluster/lrm:node1"),
        (TEST_CLUSTER_ID, "test-cluster/lrm:node2"),
    }
    assert check_rels(
        neo4j_session,
        "ProxmoxHALRM",
        "id",
        "ProxmoxNode",
        "id",
        "RUNS_ON",
    ) == {
        ("test-cluster/lrm:node1", "test-cluster/node1"),
        ("test-cluster/lrm:node2", "test-cluster/node2"),
    }
