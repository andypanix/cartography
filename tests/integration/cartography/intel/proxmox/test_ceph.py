"""
Integration tests for Proxmox Ceph sync.
"""

from contextlib import ExitStack
from typing import Any
from unittest.mock import MagicMock
from unittest.mock import patch

import cartography.intel.proxmox.ceph as ceph
import cartography.intel.proxmox.cluster
import cartography.intel.proxmox.storage
from tests.data.proxmox.ceph import MOCK_CEPH_FILESYSTEMS
from tests.data.proxmox.ceph import MOCK_CEPH_FLAGS
from tests.data.proxmox.ceph import MOCK_CEPH_FSID
from tests.data.proxmox.ceph import MOCK_CEPH_HEALTH_MUTES
from tests.data.proxmox.ceph import MOCK_CEPH_MANAGERS
from tests.data.proxmox.ceph import MOCK_CEPH_METADATA
from tests.data.proxmox.ceph import MOCK_CEPH_METADATA_SERVERS
from tests.data.proxmox.ceph import MOCK_CEPH_MONITORS
from tests.data.proxmox.ceph import MOCK_CEPH_NODES
from tests.data.proxmox.ceph import MOCK_CEPH_NOT_INSTALLED_ERROR
from tests.data.proxmox.ceph import MOCK_CEPH_OSD_LV_INFO
from tests.data.proxmox.ceph import MOCK_CEPH_OSD_LV_INFO_ERROR
from tests.data.proxmox.ceph import MOCK_CEPH_OSD_METADATA
from tests.data.proxmox.ceph import MOCK_CEPH_OSD_TREE
from tests.data.proxmox.ceph import MOCK_CEPH_POOL_STATUS
from tests.data.proxmox.ceph import MOCK_CEPH_POOLS
from tests.data.proxmox.ceph import MOCK_CEPH_RULES
from tests.data.proxmox.ceph import MOCK_CEPH_STATUS
from tests.data.proxmox.ceph import MOCK_CEPH_STORAGE
from tests.data.proxmox.ceph import MOCK_CEPH_UNREACHABLE_ERROR
from tests.integration.util import check_nodes
from tests.integration.util import check_rels

TEST_UPDATE_TAG = 123456789
TEST_CLUSTER_ID = "test-cluster"
CEPH_ID = f"{TEST_CLUSTER_ID}/{MOCK_CEPH_FSID}"


def _lv_info(_client: Any, _node: str, osd_id: int) -> dict[str, Any]:
    if osd_id not in MOCK_CEPH_OSD_LV_INFO:
        raise MOCK_CEPH_OSD_LV_INFO_ERROR
    return MOCK_CEPH_OSD_LV_INFO[osd_id]


def _seed(neo4j_session) -> None:
    neo4j_session.run("MATCH (n) DETACH DELETE n")
    neo4j_session.run(
        """
        MERGE (c:ProxmoxCluster {id: $cluster_id})
        SET c.lastupdated = $tag
        WITH c
        UNWIND ['node1', 'node2', 'node3'] AS name
        MERGE (n:ProxmoxNode {id: $cluster_id + '/' + name})
        SET n.name = name, n.cluster_id = $cluster_id, n.lastupdated = $tag
        WITH c
        UNWIND ['ceph-vm', 'cephfs', 'external-rbd', 'local'] AS name
        MERGE (s:ProxmoxStorage {id: $cluster_id + '/' + name})
        SET s.name = name, s.cluster_id = $cluster_id, s.lastupdated = $tag
        """,
        cluster_id=TEST_CLUSTER_ID,
        tag=TEST_UPDATE_TAG,
    )


def _ceph_patches() -> list[Any]:
    return [
        patch.object(ceph, "get_ceph_status", return_value=MOCK_CEPH_STATUS),
        patch.object(ceph, "get_ceph_metadata", return_value=MOCK_CEPH_METADATA),
        patch.object(ceph, "get_ceph_flags", return_value=MOCK_CEPH_FLAGS),
        patch.object(
            ceph, "get_ceph_health_mutes", return_value=MOCK_CEPH_HEALTH_MUTES
        ),
        patch.object(
            cartography.intel.proxmox.cluster,
            "get_nodes",
            return_value=MOCK_CEPH_NODES,
        ),
        patch.object(ceph, "get_ceph_monitors", return_value=MOCK_CEPH_MONITORS),
        patch.object(ceph, "get_ceph_managers", return_value=MOCK_CEPH_MANAGERS),
        patch.object(
            ceph,
            "get_ceph_metadata_servers",
            return_value=MOCK_CEPH_METADATA_SERVERS,
        ),
        patch.object(ceph, "get_ceph_osd_tree", return_value=MOCK_CEPH_OSD_TREE),
        patch.object(
            ceph,
            "get_ceph_osd_metadata",
            side_effect=lambda _c, _n, osd_id: MOCK_CEPH_OSD_METADATA[osd_id],
        ),
        patch.object(ceph, "get_ceph_osd_lv_info", side_effect=_lv_info),
        patch.object(ceph, "get_ceph_rules", return_value=MOCK_CEPH_RULES),
        patch.object(ceph, "get_ceph_pools", return_value=MOCK_CEPH_POOLS),
        patch.object(
            ceph,
            "get_ceph_pool_status",
            side_effect=lambda _c, _n, name: MOCK_CEPH_POOL_STATUS.get(name, {}),
        ),
        patch.object(ceph, "get_ceph_filesystems", return_value=MOCK_CEPH_FILESYSTEMS),
        patch.object(
            cartography.intel.proxmox.storage,
            "get_storage",
            return_value=MOCK_CEPH_STORAGE,
        ),
    ]


def _rels(neo4j_session, source: str, rel: str, target: str) -> set[tuple[str, str]]:
    return check_rels(
        neo4j_session, source, "id", target, "id", rel, rel_direction_right=True
    )


def test_sync_ceph(neo4j_session):
    # Arrange
    _seed(neo4j_session)
    common_job_parameters: dict[str, Any] = {
        "UPDATE_TAG": TEST_UPDATE_TAG,
        "CLUSTER_ID": TEST_CLUSTER_ID,
    }

    # Act
    with ExitStack() as stack:
        mocks = [stack.enter_context(p) for p in _ceph_patches()]
        ceph.sync(
            neo4j_session,
            MagicMock(),
            TEST_CLUSTER_ID,
            TEST_UPDATE_TAG,
            common_job_parameters,
        )
    monitors_mock = mocks[5]

    # Assert - cluster-wide data is read from one node with Ceph installed
    monitors_mock.assert_called_once()
    assert monitors_mock.call_args.args[1] == "node1"

    # Assert - Ceph cluster
    record = neo4j_session.run(
        """
        MATCH (c:ProxmoxCephCluster)
        RETURN c.id AS id, c.fsid AS fsid, c.health_status AS health,
               c.flags AS flags, c.muted_health_checks AS mutes
        """,
    ).single()
    assert dict(record) == {
        "id": CEPH_ID,
        "fsid": MOCK_CEPH_FSID,
        "health": "HEALTH_WARN",
        "flags": ["noout"],
        "mutes": ["POOL_NO_REDUNDANCY"],
    }

    # Assert - every Ceph node hangs off the Proxmox cluster and the Ceph cluster
    expected = {
        "ProxmoxCephMonitor": {"test-cluster/mon.node1", "test-cluster/mon.node2"},
        "ProxmoxCephManager": {"test-cluster/mgr.node1", "test-cluster/mgr.node2"},
        "ProxmoxCephMetadataServer": {"test-cluster/mds.node2"},
        "ProxmoxCephOSD": {"test-cluster/osd.0", "test-cluster/osd.1"},
        "ProxmoxCephPool": {
            "test-cluster/pool:.mgr",
            "test-cluster/pool:vm-pool",
            "test-cluster/pool:cephfs_data",
            "test-cluster/pool:cephfs_metadata",
        },
        "ProxmoxCephCrushRule": {
            "test-cluster/crush_rule:replicated_rule",
            "test-cluster/crush_rule:ssd_only",
        },
        "ProxmoxCephFilesystem": {"test-cluster/fs:cephfs"},
    }
    for label, ids in expected.items():
        assert check_rels(
            neo4j_session,
            "ProxmoxCluster",
            "id",
            label,
            "id",
            "RESOURCE",
            rel_direction_right=True,
        ) == {(TEST_CLUSTER_ID, i) for i in ids}, label
        assert _rels(
            neo4j_session, label, "MEMBER_OF_CEPH_CLUSTER", "ProxmoxCephCluster"
        ) == {(i, CEPH_ID) for i in ids}, label

    # Assert - daemons and OSDs run on their nodes
    assert _rels(neo4j_session, "ProxmoxCephMonitor", "RUNS_ON", "ProxmoxNode") == {
        ("test-cluster/mon.node1", "test-cluster/node1"),
        ("test-cluster/mon.node2", "test-cluster/node2"),
    }
    assert _rels(neo4j_session, "ProxmoxCephOSD", "RUNS_ON", "ProxmoxNode") == {
        ("test-cluster/osd.0", "test-cluster/node1"),
        ("test-cluster/osd.1", "test-cluster/node2"),
    }
    assert _rels(
        neo4j_session, "ProxmoxCephMetadataServer", "RUNS_ON", "ProxmoxNode"
    ) == {("test-cluster/mds.node2", "test-cluster/node2")}

    # Assert - OSD details, with osd.1 lacking an LVM volume
    osds = neo4j_session.run(
        """
        MATCH (o:ProxmoxCephOSD)
        RETURN o.id AS id, o.status AS status, o.objectstore AS objectstore,
               o.physical_devices AS devices, o.lv_path AS lv_path
        """,
    ).data()
    assert sorted(osds, key=lambda o: o["id"]) == [
        {
            "id": "test-cluster/osd.0",
            "status": "up",
            "objectstore": "bluestore",
            "devices": ["nvme0n1", "sdb"],
            "lv_path": "/dev/ceph-1a2b/osd-block-1a2b",
        },
        {
            "id": "test-cluster/osd.1",
            "status": "down",
            "objectstore": "bluestore",
            "devices": ["sdc"],
            "lv_path": None,
        },
    ]

    # Assert - pools, rules, file systems, and storage
    assert _rels(
        neo4j_session, "ProxmoxCephPool", "USES_CRUSH_RULE", "ProxmoxCephCrushRule"
    ) == {
        ("test-cluster/pool:.mgr", "test-cluster/crush_rule:replicated_rule"),
        ("test-cluster/pool:vm-pool", "test-cluster/crush_rule:ssd_only"),
        ("test-cluster/pool:cephfs_data", "test-cluster/crush_rule:replicated_rule"),
        (
            "test-cluster/pool:cephfs_metadata",
            "test-cluster/crush_rule:replicated_rule",
        ),
    }
    assert _rels(
        neo4j_session, "ProxmoxCephFilesystem", "USES_POOL", "ProxmoxCephPool"
    ) == {
        ("test-cluster/fs:cephfs", "test-cluster/pool:cephfs_data"),
        ("test-cluster/fs:cephfs", "test-cluster/pool:cephfs_metadata"),
    }
    assert _rels(
        neo4j_session,
        "ProxmoxCephMetadataServer",
        "SERVES",
        "ProxmoxCephFilesystem",
    ) == {("test-cluster/mds.node2", "test-cluster/fs:cephfs")}
    # external-rbd uses a pool with the same name on another Ceph cluster
    assert _rels(
        neo4j_session, "ProxmoxStorage", "USES_CEPH_POOL", "ProxmoxCephPool"
    ) == {
        ("test-cluster/ceph-vm", "test-cluster/pool:vm-pool"),
    }
    assert _rels(
        neo4j_session,
        "ProxmoxStorage",
        "USES_CEPH_FILESYSTEM",
        "ProxmoxCephFilesystem",
    ) == {("test-cluster/cephfs", "test-cluster/fs:cephfs")}
    assert check_nodes(neo4j_session, "ProxmoxCephPool", ["name", "nodelete"]) >= {
        ("vm-pool", True)
    }


def _first_sync(neo4j_session) -> None:
    _seed(neo4j_session)
    with ExitStack() as stack:
        for p in _ceph_patches():
            stack.enter_context(p)
        ceph.sync(
            neo4j_session,
            MagicMock(),
            TEST_CLUSTER_ID,
            TEST_UPDATE_TAG,
            {"UPDATE_TAG": TEST_UPDATE_TAG, "CLUSTER_ID": TEST_CLUSTER_ID},
        )


def _metadata_without_local_ceph(_client: Any, scope: str = "all") -> dict[str, Any]:
    # The API node has no Ceph: only the per-node versions can be read
    if scope != "versions":
        raise MOCK_CEPH_NOT_INSTALLED_ERROR
    return {"node": MOCK_CEPH_METADATA["node"]}


def _ceph_ids(neo4j_session) -> set[str]:
    ids: set[str] = set()
    for schema in ceph.CEPH_SCHEMAS:
        ids |= {
            i for (i,) in check_nodes(neo4j_session, schema().label, ["id"]) or set()
        }
    return ids


def test_sync_ceph_through_another_node(neo4j_session):
    # Arrange - the API node (node1) has no Ceph, node2 runs Ceph
    _seed(neo4j_session)
    params = {"UPDATE_TAG": TEST_UPDATE_TAG, "CLUSTER_ID": TEST_CLUSTER_ID}

    def node_status(_client: Any, node: str) -> dict[str, Any]:
        if node == "node1":
            raise MOCK_CEPH_NOT_INSTALLED_ERROR
        return MOCK_CEPH_STATUS

    # Act
    with ExitStack() as stack:
        mocks = [stack.enter_context(p) for p in _ceph_patches()]
        for name, kwargs in (
            ("get_ceph_status", {"side_effect": MOCK_CEPH_NOT_INSTALLED_ERROR}),
            ("get_ceph_metadata", {"side_effect": _metadata_without_local_ceph}),
            ("get_ceph_flags", {"side_effect": MOCK_CEPH_NOT_INSTALLED_ERROR}),
            ("get_ceph_health_mutes", {"side_effect": MOCK_CEPH_NOT_INSTALLED_ERROR}),
            ("get_ceph_node_status", {"side_effect": node_status}),
        ):
            stack.enter_context(patch.object(ceph, name, **kwargs))
        current = ceph.sync(
            neo4j_session, MagicMock(), TEST_CLUSTER_ID, TEST_UPDATE_TAG, params
        )
    monitors_mock = mocks[5]

    # Assert - per-node data is read from the node that answered the status
    assert current is True
    assert monitors_mock.call_args.args[1] == "node2"
    record = neo4j_session.run(
        """
        MATCH (:ProxmoxCluster {id: $cluster_id})-[:RESOURCE]->(c:ProxmoxCephCluster)
        RETURN c.id AS id, c.flags AS flags, c.muted_health_checks AS mutes
        """,
        cluster_id=TEST_CLUSTER_ID,
    ).single()
    assert dict(record) == {"id": CEPH_ID, "flags": ["noout"], "mutes": None}
    assert {"test-cluster/osd.0", "test-cluster/osd.1"} <= _ceph_ids(neo4j_session)


def test_ceph_unreadable_keeps_data(neo4j_session):
    # Arrange - a first sync with Ceph
    _first_sync(neo4j_session)
    before = _ceph_ids(neo4j_session)
    new_tag = TEST_UPDATE_TAG + 1
    params = {"UPDATE_TAG": new_tag, "CLUSTER_ID": TEST_CLUSTER_ID}

    # Act - the API node has no Ceph and the other nodes fail for another reason
    with (
        patch.object(
            ceph, "get_ceph_status", side_effect=MOCK_CEPH_NOT_INSTALLED_ERROR
        ),
        patch.object(
            ceph,
            "get_ceph_node_status",
            side_effect=MOCK_CEPH_UNREACHABLE_ERROR,
        ),
        patch.object(
            cartography.intel.proxmox.cluster,
            "get_nodes",
            return_value=MOCK_CEPH_NODES,
        ),
    ):
        current = ceph.sync(
            neo4j_session, MagicMock(), TEST_CLUSTER_ID, new_tag, params
        )
    if current:
        ceph.cleanup(neo4j_session, params)

    # Assert - the cleanup is skipped and the Ceph data is kept
    assert current is False
    assert before
    assert _ceph_ids(neo4j_session) == before


def test_ceph_removed_cleans_up(neo4j_session):
    # Arrange - a first sync with Ceph
    _first_sync(neo4j_session)
    new_tag = TEST_UPDATE_TAG + 1
    params = {"UPDATE_TAG": new_tag, "CLUSTER_ID": TEST_CLUSTER_ID}

    # Act - Ceph is no longer installed on any node
    with (
        patch.object(
            ceph, "get_ceph_status", side_effect=MOCK_CEPH_NOT_INSTALLED_ERROR
        ),
        patch.object(
            ceph, "get_ceph_node_status", side_effect=MOCK_CEPH_NOT_INSTALLED_ERROR
        ) as node_status,
        patch.object(
            cartography.intel.proxmox.cluster,
            "get_nodes",
            return_value=MOCK_CEPH_NODES,
        ),
    ):
        current = ceph.sync(
            neo4j_session, MagicMock(), TEST_CLUSTER_ID, new_tag, params
        )
    if current:
        ceph.cleanup(neo4j_session, params)

    # Assert - every online node was asked, and every Ceph node is gone
    assert current is True
    assert node_status.call_count == len(MOCK_CEPH_NODES)
    assert _ceph_ids(neo4j_session) == set()
