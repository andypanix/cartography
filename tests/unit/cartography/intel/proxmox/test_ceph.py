"""
Unit tests for Proxmox Ceph transforms and error classification.
"""

from unittest.mock import MagicMock

import pytest
from proxmoxer.core import ResourceException

from cartography.intel.proxmox import ceph
from cartography.intel.proxmox import cluster
from tests.data.proxmox.ceph import MOCK_CEPH_FILESYSTEMS
from tests.data.proxmox.ceph import MOCK_CEPH_FLAGS
from tests.data.proxmox.ceph import MOCK_CEPH_FSID
from tests.data.proxmox.ceph import MOCK_CEPH_HEALTH_MUTES
from tests.data.proxmox.ceph import MOCK_CEPH_METADATA
from tests.data.proxmox.ceph import MOCK_CEPH_METADATA_SERVERS
from tests.data.proxmox.ceph import MOCK_CEPH_NOT_INITIALIZED_ERROR
from tests.data.proxmox.ceph import MOCK_CEPH_NOT_INSTALLED_ERROR
from tests.data.proxmox.ceph import MOCK_CEPH_OSD_LV_INFO
from tests.data.proxmox.ceph import MOCK_CEPH_OSD_METADATA
from tests.data.proxmox.ceph import MOCK_CEPH_OSD_TREE
from tests.data.proxmox.ceph import MOCK_CEPH_POOL_STATUS
from tests.data.proxmox.ceph import MOCK_CEPH_POOLS
from tests.data.proxmox.ceph import MOCK_CEPH_STATUS
from tests.data.proxmox.ceph import MOCK_CEPH_STORAGE

CLUSTER_ID = "prod"
CEPH_ID = f"prod/{MOCK_CEPH_FSID}"


@pytest.mark.parametrize(
    "exc",
    [
        MOCK_CEPH_NOT_INSTALLED_ERROR,
        MOCK_CEPH_NOT_INITIALIZED_ERROR,
        ResourceException(
            500,
            "Internal Server Error",
            "ceph not fully configured - missing '/etc/pve/priv/ceph.client.admin.keyring'",
        ),
    ],
)
def test_is_ceph_not_present_matches_pve_manager_messages(exc):
    # Act and assert
    assert ceph.is_ceph_not_present(exc)


@pytest.mark.parametrize(
    "exc",
    [
        ResourceException(500, "Internal Server Error", "rados_connect failed"),
        ResourceException(403, "Forbidden", "binary not installed"),
        ResourceException(503, "Service Unavailable", ""),
        ValueError("binary not installed"),
    ],
)
def test_is_ceph_not_present_ignores_other_errors(exc):
    # Act and assert
    assert not ceph.is_ceph_not_present(exc)


def test_transform_ceph_cluster():
    # Act
    result = ceph.transform_ceph_cluster(
        MOCK_CEPH_STATUS,
        MOCK_CEPH_METADATA,
        MOCK_CEPH_FLAGS,
        MOCK_CEPH_HEALTH_MUTES,
        CLUSTER_ID,
    )

    # Assert
    assert result == {
        "id": CEPH_ID,
        "fsid": MOCK_CEPH_FSID,
        "cluster_id": CLUSTER_ID,
        "health_status": "HEALTH_WARN",
        "health_checks": ["OSD_DOWN", "POOL_NO_REDUNDANCY"],
        "muted_health_checks": ["POOL_NO_REDUNDANCY"],
        "flags": ["noout"],
        "ceph_versions": ["19.2.0", "19.2.1"],
        "crush_device_classes": None,
    }


def test_extract_osds_sets_host_from_parent_bucket():
    # Arrange - a tree whose leaves carry no host field
    tree = {
        "root": {
            "children": [
                {
                    "type": "root",
                    "name": "default",
                    "children": [
                        {
                            "type": "host",
                            "name": "pve-a",
                            "children": [{"id": 7, "type": "osd", "name": "osd.7"}],
                        },
                    ],
                },
            ],
        },
    }

    # Act
    osds = ceph.extract_osds(tree)

    # Assert
    assert [(o["id"], o["host"]) for o in osds] == [(7, "pve-a")]


def test_transform_osds_merges_metadata_and_volume():
    # Arrange
    osds = ceph.extract_osds(MOCK_CEPH_OSD_TREE)

    # Act
    result = ceph.transform_osds(
        osds,
        MOCK_CEPH_OSD_METADATA,
        MOCK_CEPH_OSD_LV_INFO,
        CLUSTER_ID,
        CEPH_ID,
    )

    # Assert
    by_id = {o["osd_id"]: o for o in result}
    assert by_id[0]["id"] == "prod/osd.0"
    assert by_id[0]["node_id"] == "prod/node1"
    assert by_id[0]["is_in"] is True
    assert by_id[0]["encrypted"] is True
    assert by_id[0]["physical_devices"] == ["nvme0n1", "sdb"]
    assert by_id[0]["lv_path"] == "/dev/ceph-1a2b/osd-block-1a2b"
    assert by_id[1]["status"] == "down"
    assert by_id[1]["is_in"] is False
    assert by_id[1]["lv_path"] is None


def test_storage_mapping_skips_external_clusters():
    # Act
    pool_storage = ceph.map_storage_to_pools(MOCK_CEPH_STORAGE)
    fs_storage = ceph.map_storage_to_filesystems(MOCK_CEPH_STORAGE, ["cephfs"])

    # Assert - external-rbd has monhost and points to another Ceph cluster
    assert pool_storage == {"vm-pool": ["ceph-vm"]}
    # cephfs storage has no fs-name and the cluster has a single file system
    assert fs_storage == {"cephfs": ["cephfs"]}


def test_storage_mapping_defaults_and_data_pool():
    # Arrange
    storage_list = [
        {"storage": "plain", "type": "rbd"},
        {"storage": "ec", "type": "rbd", "pool": "ec-meta", "data-pool": "ec-data"},
        {"storage": "fs-default", "type": "cephfs"},
    ]

    # Act
    pool_storage = ceph.map_storage_to_pools(storage_list)
    fs_storage = ceph.map_storage_to_filesystems(storage_list, ["fs1", "fs2"])

    # Assert - no pool means the rbd pool; the default file system is unknown
    # when there are several
    assert pool_storage == {"rbd": ["plain"], "ec-meta": ["ec"], "ec-data": ["ec"]}
    assert fs_storage == {}


def test_transform_pools():
    # Act
    result = ceph.transform_pools(
        MOCK_CEPH_POOLS,
        MOCK_CEPH_POOL_STATUS,
        {"vm-pool": ["ceph-vm"]},
        CLUSTER_ID,
        CEPH_ID,
    )

    # Assert
    vm_pool = next(p for p in result if p["name"] == "vm-pool")
    assert vm_pool["id"] == "prod/pool:vm-pool"
    assert vm_pool["crush_rule_id"] == "prod/crush_rule:ssd_only"
    assert vm_pool["applications"] == ["rbd"]
    assert vm_pool["nodelete"] is True
    assert vm_pool["nosizechange"] is False
    assert vm_pool["storage_ids"] == ["prod/ceph-vm"]
    mgr_pool = next(p for p in result if p["name"] == ".mgr")
    assert mgr_pool["nodelete"] is None
    assert mgr_pool["storage_ids"] == []


def test_transform_filesystems_supports_pve8_shape():
    # Arrange - Proxmox VE 8 returns data_pool only
    pve8 = [{"name": "cephfs", "metadata_pool": "meta", "data_pool": "data"}]

    # Act
    result = ceph.transform_filesystems(pve8, {}, CLUSTER_ID, CEPH_ID)

    # Assert
    assert result[0]["data_pools"] == ["data"]
    assert result[0]["pool_ids"] == ["prod/pool:data", "prod/pool:meta"]


def test_transform_filesystems_and_mds():
    # Act
    filesystems = ceph.transform_filesystems(
        MOCK_CEPH_FILESYSTEMS, {"cephfs": ["cephfs"]}, CLUSTER_ID, CEPH_ID
    )
    mds = ceph.transform_metadata_servers(
        MOCK_CEPH_METADATA_SERVERS, CLUSTER_ID, CEPH_ID
    )

    # Assert
    assert filesystems[0]["id"] == "prod/fs:cephfs"
    assert filesystems[0]["storage_ids"] == ["prod/cephfs"]
    assert mds[0]["id"] == "prod/mds.node2"
    assert mds[0]["filesystem_id"] == "prod/fs:cephfs"
    assert mds[0]["standby_replay"] is False


def test_pick_query_node_prefers_nodes_with_ceph():
    # Arrange
    nodes = [
        {"node": "a", "status": "online"},
        {"node": "b", "status": "online"},
        {"node": "c", "status": "offline"},
    ]

    # Act and assert
    assert ceph._pick_query_node(nodes, {"node": {"b": {}, "c": {}}}) == "b"
    assert ceph._pick_query_node(nodes, {}) == "a"
    assert ceph._pick_query_node([{"node": "c", "status": "offline"}], {}) is None


NODES = [
    {"node": "node1", "status": "online"},
    {"node": "node2", "status": "online"},
    {"node": "node3", "status": "offline"},
]


def _patch_detection(monkeypatch, node_status: MagicMock) -> MagicMock:
    get_metadata = MagicMock()
    monkeypatch.setattr(
        ceph,
        "get_ceph_status",
        MagicMock(side_effect=MOCK_CEPH_NOT_INSTALLED_ERROR),
    )
    monkeypatch.setattr(cluster, "get_nodes", MagicMock(return_value=NODES))
    monkeypatch.setattr(ceph, "get_ceph_node_status", node_status)
    monkeypatch.setattr(ceph, "get_ceph_metadata", get_metadata)
    return get_metadata


def test_sync_skips_when_ceph_not_installed(monkeypatch):
    # Arrange - no online node has Ceph
    node_status = MagicMock(side_effect=MOCK_CEPH_NOT_INSTALLED_ERROR)
    get_metadata = _patch_detection(monkeypatch, node_status)

    # Act
    current = ceph.sync(MagicMock(), MagicMock(), CLUSTER_ID, 1, {})

    # Assert - each online node was asked once, and the cleanup may run
    assert current == ceph.CephSyncResult(current=True, crush_current=True)
    assert [c.args[1] for c in node_status.call_args_list] == ["node1", "node2"]
    get_metadata.assert_not_called()


def test_sync_keeps_data_when_ceph_cannot_be_read(monkeypatch):
    # Arrange - node1 has no Ceph, node2 is unreachable
    node_status = MagicMock(
        side_effect=[
            MOCK_CEPH_NOT_INSTALLED_ERROR,
            ResourceException(595, "Connection refused", ""),
        ],
    )
    get_metadata = _patch_detection(monkeypatch, node_status)

    # Act
    current = ceph.sync(MagicMock(), MagicMock(), CLUSTER_ID, 1, {})

    # Assert - absence is not confirmed, so the cleanup must be skipped
    assert current == ceph.CephSyncResult(current=False, crush_current=False)
    get_metadata.assert_not_called()


def test_find_ceph_status_stops_at_first_node_with_ceph(monkeypatch):
    # Arrange
    node_status = MagicMock(
        side_effect=[MOCK_CEPH_NOT_INSTALLED_ERROR, MOCK_CEPH_STATUS],
    )
    monkeypatch.setattr(ceph, "get_ceph_node_status", node_status)

    # Act
    result = ceph._find_ceph_status(MagicMock(), ["a", "b", "c"])

    # Assert
    assert result == (MOCK_CEPH_STATUS, "b", False)
    assert node_status.call_count == 2


def test_find_ceph_status_without_online_nodes_is_not_a_confirmed_absence():
    # Act and assert
    assert ceph._find_ceph_status(MagicMock(), []) == (None, None, False)


def test_sync_keeps_data_without_online_nodes(monkeypatch):
    # Arrange - Ceph answers, but no node is online to read the details from
    monkeypatch.setattr(
        ceph, "get_ceph_status", MagicMock(return_value=MOCK_CEPH_STATUS)
    )
    monkeypatch.setattr(ceph, "get_ceph_metadata", MagicMock(return_value={}))
    monkeypatch.setattr(ceph, "get_ceph_health_mutes", MagicMock(return_value=[]))
    monkeypatch.setattr(
        cluster,
        "get_nodes",
        MagicMock(return_value=[{"node": "node1", "status": "offline"}]),
    )

    # Act and assert
    assert ceph.sync(MagicMock(), MagicMock(), CLUSTER_ID, 1, {}) == (
        ceph.CephSyncResult(current=False, crush_current=False)
    )


def test_flags_from_osd_tree():
    # Act and assert
    assert ceph._flags_from_osd_tree({"flags": "noout,noscrub"}) == [
        {"name": "noout", "value": 1},
        {"name": "noscrub", "value": 1},
    ]
    assert ceph._flags_from_osd_tree({}) == []


def test_transform_ceph_cluster_with_unknown_mutes():
    # Act
    result = ceph.transform_ceph_cluster(MOCK_CEPH_STATUS, {}, [], None, CLUSTER_ID)

    # Assert
    assert result["muted_health_checks"] is None


def test_osd_details_keep_tree_data_when_metadata_fails(monkeypatch):
    # Arrange - node2 goes offline during the sync
    osds = ceph.extract_osds(MOCK_CEPH_OSD_TREE)

    def metadata(_client, node, osd_id):
        if node == "node2":
            raise ResourceException(595, "Connection refused", "")
        return MOCK_CEPH_OSD_METADATA[osd_id]

    lv_info = MagicMock(return_value={})
    monkeypatch.setattr(ceph, "get_ceph_osd_metadata", MagicMock(side_effect=metadata))
    monkeypatch.setattr(ceph, "get_ceph_osd_lv_info", lv_info)

    # Act
    details, volumes = ceph._get_osd_details(MagicMock(), osds, {"node1", "node2"})

    # Assert - only the OSD on node1 has details
    assert set(details) == {0}
    assert set(volumes) == {0}


def test_sync_raises_unrelated_errors(monkeypatch):
    # Arrange
    error = ResourceException(403, "Forbidden", "Permission check failed")
    monkeypatch.setattr(ceph, "get_ceph_status", MagicMock(side_effect=error))

    # Act and assert
    with pytest.raises(ResourceException):
        ceph.sync(MagicMock(), MagicMock(), CLUSTER_ID, 1, {})


def test_osd_details_skip_offline_nodes_and_missing_lvm(monkeypatch):
    # Arrange
    osds = ceph.extract_osds(MOCK_CEPH_OSD_TREE)
    monkeypatch.setattr(
        ceph,
        "get_ceph_osd_metadata",
        MagicMock(side_effect=lambda _c, _n, osd_id: MOCK_CEPH_OSD_METADATA[osd_id]),
    )
    monkeypatch.setattr(
        ceph,
        "get_ceph_osd_lv_info",
        MagicMock(
            side_effect=ResourceException(
                500,
                "Internal Server Error",
                "OSD '0' not found in 'ceph-volume lvm list'",
            ),
        ),
    )

    # Act - node2 is offline
    details, volumes = ceph._get_osd_details(MagicMock(), osds, {"node1"})

    # Assert
    assert set(details) == {0}
    assert volumes == {}


def test_osd_details_raise_unrelated_lv_info_errors(monkeypatch):
    # Arrange
    osds = ceph.extract_osds(MOCK_CEPH_OSD_TREE)
    monkeypatch.setattr(ceph, "get_ceph_osd_metadata", MagicMock(return_value={}))
    monkeypatch.setattr(
        ceph,
        "get_ceph_osd_lv_info",
        MagicMock(side_effect=ResourceException(500, "Internal Server Error", "boom")),
    )

    # Act and assert
    with pytest.raises(ResourceException):
        ceph._get_osd_details(MagicMock(), osds, {"node1", "node2"})
