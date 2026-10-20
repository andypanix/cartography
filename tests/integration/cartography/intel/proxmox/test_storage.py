"""
Integration tests for Proxmox storage module.
"""

from unittest.mock import MagicMock
from unittest.mock import patch

import cartography.intel.proxmox.storage
from cartography.intel.proxmox.storage import sync as storage_sync
from tests.data.proxmox.compute import MOCK_STORAGE_DATA
from tests.integration.util import check_nodes
from tests.integration.util import check_rels

TEST_UPDATE_TAG = 123456789
TEST_CLUSTER_ID = "test-cluster"


@patch.object(
    cartography.intel.proxmox.storage, "get_storage", return_value=MOCK_STORAGE_DATA
)
def test_sync_storage(mock_get_storage, neo4j_session):
    """
    Test that storage backends sync correctly.
    """
    # Arrange - Create cluster node first (required for relationships)
    neo4j_session.run(
        """
        MERGE (c:ProxmoxCluster {id: $cluster_id})
        SET c.name = $cluster_id
        """,
        cluster_id=TEST_CLUSTER_ID,
    )

    proxmox = MagicMock()
    common_job_parameters = {
        "UPDATE_TAG": TEST_UPDATE_TAG,
        "CLUSTER_ID": TEST_CLUSTER_ID,
    }

    # Act
    storage_sync(
        neo4j_session,
        proxmox,
        TEST_CLUSTER_ID,
        TEST_UPDATE_TAG,
        common_job_parameters,
    )

    # Assert - Check storage nodes
    expected_storage_nodes = {
        (f"{TEST_CLUSTER_ID}/local", "local", "dir", False),
        (f"{TEST_CLUSTER_ID}/local-lvm", "local-lvm", "lvmthin", False),
        (f"{TEST_CLUSTER_ID}/nfs-backup", "nfs-backup", "nfs", True),
    }
    assert (
        check_nodes(neo4j_session, "ProxmoxStorage", ["id", "name", "type", "shared"])
        == expected_storage_nodes
    )

    # Assert - Check storage->cluster relationships
    expected_rels = {
        (f"{TEST_CLUSTER_ID}/local", TEST_CLUSTER_ID),
        (f"{TEST_CLUSTER_ID}/local-lvm", TEST_CLUSTER_ID),
        (f"{TEST_CLUSTER_ID}/nfs-backup", TEST_CLUSTER_ID),
    }
    assert (
        check_rels(
            neo4j_session,
            "ProxmoxStorage",
            "id",
            "ProxmoxCluster",
            "id",
            "RESOURCE",
            rel_direction_right=False,
        )
        == expected_rels
    )


@patch.object(
    cartography.intel.proxmox.storage, "get_storage", return_value=MOCK_STORAGE_DATA
)
def test_storage_properties(mock_get_storage, neo4j_session):
    """
    Test that storage properties are correctly stored.
    """
    # Arrange - Create cluster node first (required for relationships)
    neo4j_session.run(
        """
        MERGE (c:ProxmoxCluster {id: $cluster_id})
        SET c.name = $cluster_id
        """,
        cluster_id=TEST_CLUSTER_ID,
    )

    proxmox = MagicMock()
    common_job_parameters = {
        "UPDATE_TAG": TEST_UPDATE_TAG,
        "CLUSTER_ID": TEST_CLUSTER_ID,
    }

    # Act
    storage_sync(
        neo4j_session,
        proxmox,
        TEST_CLUSTER_ID,
        TEST_UPDATE_TAG,
        common_job_parameters,
    )

    # Assert - Check local storage properties
    result = neo4j_session.run(
        """
        MATCH (s:ProxmoxStorage {id: 'test-cluster/local'})
        RETURN s.name, s.type, s.content_types, s.shared, s.enabled
        """
    )
    data = result.single()
    assert data is not None
    assert data["s.name"] == "local"
    assert data["s.type"] == "dir"
    # content_types is stored as a list, not a string
    assert "backup" in data["s.content_types"]
    assert "iso" in data["s.content_types"]
    assert data["s.shared"] is False
    assert data["s.enabled"] is True
    # Note: available/total/used require storage status from nodes, not tested here

    # Assert - Check NFS storage properties
    result = neo4j_session.run(
        """
        MATCH (s:ProxmoxStorage {id: 'test-cluster/nfs-backup'})
        RETURN s.name, s.type, s.shared
        """
    )
    data = result.single()
    assert data is not None
    assert data["s.name"] == "nfs-backup"
    assert data["s.type"] == "nfs"
    assert data["s.shared"] is True
    # Note: NFS-specific fields like server/export are not currently captured in the model


@patch.object(
    cartography.intel.proxmox.storage, "get_storage", return_value=MOCK_STORAGE_DATA
)
def test_storage_node_relationships(mock_get_storage, neo4j_session):
    """
    Test that storage to node AVAILABLE_ON relationships are created.
    """
    # First, create some mock nodes so we have something to relate to
    neo4j_session.run(
        """
        MERGE (n1:ProxmoxNode {id: 'test-cluster/node1', name: 'node1'})
        MERGE (n2:ProxmoxNode {id: 'test-cluster/node2', name: 'node2'})
        MERGE (c:ProxmoxCluster {id: $cluster_id})
        """,
        cluster_id=TEST_CLUSTER_ID,
    )

    # Arrange
    proxmox = MagicMock()
    common_job_parameters = {
        "UPDATE_TAG": TEST_UPDATE_TAG,
        "CLUSTER_ID": TEST_CLUSTER_ID,
    }

    # Act
    storage_sync(
        neo4j_session,
        proxmox,
        TEST_CLUSTER_ID,
        TEST_UPDATE_TAG,
        common_job_parameters,
    )

    # Assert - Each storage is available on the nodes it lists
    assert check_rels(
        neo4j_session,
        "ProxmoxStorage",
        "id",
        "ProxmoxNode",
        "id",
        "AVAILABLE_ON",
        rel_direction_right=True,
    ) == {
        (f"{TEST_CLUSTER_ID}/{storage}", f"{TEST_CLUSTER_ID}/{node}")
        for storage in ("local", "local-lvm", "nfs-backup")
        for node in ("node1", "node2")
    }


def test_storage_status_detail_fills_gaps_and_skips_errors(neo4j_session, caplog):
    """
    The per-storage status of each active storage fills only what the per-node
    list leaves unset, and a storage whose status fails keeps its list values.
    """
    # Arrange
    neo4j_session.run("MATCH (n) DETACH DELETE n")
    neo4j_session.run("MERGE (:ProxmoxCluster {id: $id})", id=TEST_CLUSTER_ID)
    proxmox = MagicMock()
    proxmox.nodes.get.return_value = [{"node": "node1"}]
    node_list = [
        # The list lacks the sizes of local
        {"storage": "local", "type": "dir", "active": 1},
        {"storage": "local-lvm", "type": "lvmthin", "active": 1, "total": 500},
        {"storage": "nfs-backup", "type": "nfs", "active": 0},
    ]

    def detail(_client, node, name):
        if name == "local-lvm":
            raise cartography.intel.proxmox.storage.ResourceException(
                500, "Internal Server Error", "timeout"
            )
        return {"type": "dir", "active": 1, "total": 100, "used": 40, "avail": 60}

    # Act
    with (
        patch.object(
            cartography.intel.proxmox.storage,
            "get_storage",
            return_value=MOCK_STORAGE_DATA,
        ),
        patch.object(
            cartography.intel.proxmox.storage,
            "get_storage_status",
            return_value=node_list,
        ),
        patch.object(
            cartography.intel.proxmox.storage,
            "get_storage_status_detail",
            side_effect=detail,
        ) as detail_mock,
        patch.object(
            cartography.intel.proxmox.storage,
            "get_shared_storage_identities",
            return_value={},
        ),
    ):
        status_map = storage_sync(
            neo4j_session,
            proxmox,
            TEST_CLUSTER_ID,
            TEST_UPDATE_TAG,
            {"UPDATE_TAG": TEST_UPDATE_TAG, "CLUSTER_ID": TEST_CLUSTER_ID},
        )

    # Assert - inactive storage is not read; every storage is still loaded
    assert [c.args[1:] for c in detail_mock.call_args_list] == [
        ("node1", "local"),
        ("node1", "local-lvm"),
    ]
    assert check_nodes(
        neo4j_session, "ProxmoxStorage", ["name", "total", "used", "available"]
    ) == {
        ("local", 100, 40, 60),
        ("local-lvm", 500, 0, 0),
        ("nfs-backup", 0, 0, 0),
    }
    assert status_map["node1"][0]["type"] == "dir"
    assert "Could not read the status of storage local-lvm on node node1" in (
        caplog.text
    )
