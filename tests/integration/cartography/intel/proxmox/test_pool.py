"""
Integration tests for Proxmox pool sync.
"""

from typing import Any
from unittest.mock import patch

import cartography.intel.proxmox.pool
from tests.data.proxmox.pool import MOCK_NESTED_POOL_DATA
from tests.data.proxmox.pool import MOCK_POOL_DATA
from tests.data.proxmox.pool import MOCK_POOL_DETAILS
from tests.integration.util import check_nodes
from tests.integration.util import check_rels

TEST_UPDATE_TAG = 123456789
TEST_CLUSTER_ID = "test-cluster"


@patch.object(cartography.intel.proxmox.pool, "get_pools", return_value=MOCK_POOL_DATA)
@patch.object(cartography.intel.proxmox.pool, "get_pool_details")
def test_sync_pools(mock_get_pool_details, mock_get_pools, neo4j_session):
    """
    Test that pools sync correctly and create proper nodes and relationships.
    """

    # Arrange
    def get_details_side_effect(proxmox_client, poolid):
        return MOCK_POOL_DETAILS.get(poolid, {})

    mock_get_pool_details.side_effect = get_details_side_effect

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

    # Create VMs and storage for relationship tests
    neo4j_session.run(
        """
        MERGE (v1:ProxmoxVM {id: 'test-cluster/node1/qemu/100'})
        SET v1.vmid = 100, v1.cluster_id = 'test-cluster', v1.name = 'test-vm-1', v1.lastupdated = $update_tag
        MERGE (v2:ProxmoxVM {id: 'test-cluster/node1/qemu/101'})
        SET v2.vmid = 101, v2.cluster_id = 'test-cluster', v2.name = 'test-vm-2', v2.lastupdated = $update_tag
        MERGE (v3:ProxmoxVM {id: 'test-cluster/node2/lxc/200'})
        SET v3.vmid = 200, v3.cluster_id = 'test-cluster', v3.name = 'test-container-1', v3.lastupdated = $update_tag
        MERGE (s:ProxmoxStorage {id: 'test-cluster/nfs-backup'})
        SET s.name = 'nfs-backup', s.lastupdated = $update_tag
        """,
        update_tag=TEST_UPDATE_TAG,
    )

    # Act
    cartography.intel.proxmox.pool.sync(
        neo4j_session,
        None,  # proxmox_client mocked
        TEST_CLUSTER_ID,
        TEST_UPDATE_TAG,
        common_job_parameters,
    )

    # Assert - Pools exist
    expected_pools = {
        ("test-cluster/production", "Production VMs and containers"),
        ("test-cluster/development", "Development environment"),
        ("test-cluster/backup-storage", "Backup storage resources"),
    }
    assert (
        check_nodes(neo4j_session, "ProxmoxPool", ["id", "comment"]) == expected_pools
    )

    # Assert - Pool to cluster relationships
    expected_rels = {
        ("test-cluster/production", TEST_CLUSTER_ID),
        ("test-cluster/development", TEST_CLUSTER_ID),
        ("test-cluster/backup-storage", TEST_CLUSTER_ID),
    }
    assert (
        check_rels(
            neo4j_session,
            "ProxmoxPool",
            "id",
            "ProxmoxCluster",
            "id",
            "RESOURCE",
            rel_direction_right=False,
        )
        == expected_rels
    )

    # Assert - Pool to VM relationships
    expected_vm_rels = {
        ("test-cluster/development", "test-cluster/node1/qemu/101"),
        ("test-cluster/production", "test-cluster/node1/qemu/100"),
        ("test-cluster/production", "test-cluster/node2/lxc/200"),
    }
    assert (
        check_rels(
            neo4j_session,
            "ProxmoxPool",
            "id",
            "ProxmoxVM",
            "id",
            "CONTAINS_VM",
            rel_direction_right=True,
        )
        == expected_vm_rels
    )

    # Assert - Pool to storage relationships
    assert check_rels(
        neo4j_session,
        "ProxmoxPool",
        "id",
        "ProxmoxStorage",
        "id",
        "CONTAINS_STORAGE",
        rel_direction_right=True,
    ) == {("test-cluster/backup-storage", "test-cluster/nfs-backup")}


@patch.object(
    cartography.intel.proxmox.pool, "get_pools", return_value=MOCK_NESTED_POOL_DATA
)
@patch.object(cartography.intel.proxmox.pool, "get_pool_details", return_value={})
def test_sync_nested_pools(mock_get_pool_details, mock_get_pools, neo4j_session):
    """
    Nested pools are linked to their direct parent pool.
    """
    # Arrange
    neo4j_session.run("MATCH (n) DETACH DELETE n")
    neo4j_session.run(
        "MERGE (c:ProxmoxCluster {id: $cluster_id}) SET c.lastupdated = $update_tag",
        cluster_id=TEST_CLUSTER_ID,
        update_tag=TEST_UPDATE_TAG,
    )

    # Act
    cartography.intel.proxmox.pool.sync(
        neo4j_session,
        None,  # proxmox_client mocked
        TEST_CLUSTER_ID,
        TEST_UPDATE_TAG,
        {"UPDATE_TAG": TEST_UPDATE_TAG, "CLUSTER_ID": TEST_CLUSTER_ID},
    )

    # Assert
    assert check_nodes(neo4j_session, "ProxmoxPool", ["id", "parent_poolid"]) == {
        ("test-cluster/development", None),
        ("test-cluster/development/team1", "development"),
        ("test-cluster/development/team1/frontend", "development/team1"),
    }
    assert check_rels(
        neo4j_session,
        "ProxmoxPool",
        "id",
        "ProxmoxPool",
        "id",
        "CONTAINS_POOL",
        rel_direction_right=True,
    ) == {
        ("test-cluster/development", "test-cluster/development/team1"),
        ("test-cluster/development/team1", "test-cluster/development/team1/frontend"),
    }
