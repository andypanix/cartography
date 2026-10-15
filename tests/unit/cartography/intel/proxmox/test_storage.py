"""
Tests for Proxmox storage module.
"""

from cartography.intel.proxmox.storage import transform_storage_data


def test_transform_storage_data():
    """Test storage data transformation."""
    raw_storage = [
        {
            "storage": "local",
            "type": "dir",
            "content": "iso,vztmpl,backup",
            "shared": 0,
            "disable": 0,
        },
        {
            "storage": "local-lvm",
            "type": "lvmthin",
            "content": "images,rootdir",
            "shared": 0,
            "disable": 0,
        },
        {
            "storage": "nfs-share",
            "type": "nfs",
            "content": "images,backup",
            "shared": 1,
            "disable": 0,
            "nodes": "node1,node2",
        },
    ]

    storage_status_map = {
        "node1": [
            {
                "storage": "local",
                "total": 1099511627776,
                "used": 274877906944,
                "avail": 824633720832,
            },
            {
                "storage": "local-lvm",
                "total": 549755813888,
                "used": 137438953472,
                "avail": 412316860416,
            },
        ],
        "node2": [],
    }

    cluster_id = "test-cluster"

    result = transform_storage_data(raw_storage, storage_status_map, cluster_id)

    assert len(result) == 3

    # Test local storage
    local = next(s for s in result if s["name"] == "local")
    assert local["id"] == "test-cluster/local"
    assert local["type"] == "dir"
    assert local["content_types"] == ["iso", "vztmpl", "backup"]
    assert local["shared"] is False
    assert local["enabled"] is True
    assert local["total"] == 1099511627776
    assert set(local["node_ids"]) == {"test-cluster/node1", "test-cluster/node2"}

    # Test LVM-thin storage
    lvm = next(s for s in result if s["name"] == "local-lvm")
    assert lvm["type"] == "lvmthin"
    assert lvm["content_types"] == ["images", "rootdir"]

    # Test NFS storage with explicit nodes
    nfs = next(s for s in result if s["name"] == "nfs-share")
    assert nfs["type"] == "nfs"
    assert nfs["shared"] is True
    assert set(nfs["node_ids"]) == {"test-cluster/node1", "test-cluster/node2"}
