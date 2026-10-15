"""
Tests for Proxmox pool module.
"""

from cartography.intel.proxmox.pool import transform_pool_data
from tests.data.proxmox.pool import MOCK_POOL_DATA
from tests.data.proxmox.pool import MOCK_POOL_DETAILS


def test_transform_pool_data_lists_member_ids():
    """Guest members map to full ProxmoxVM IDs and storage members to storage IDs."""
    result = transform_pool_data(MOCK_POOL_DATA, "test-cluster", MOCK_POOL_DETAILS)

    members = {r["id"]: (r["vm_ids"], r["storage_ids"]) for r in result}
    assert members == {
        "production": (["node1/qemu/100", "node2/lxc/200"], []),
        "development": (["node1/qemu/101"], []),
        "backup-storage": ([], ["nfs-backup"]),
    }


def test_transform_pool_data_without_details():
    """Pools without member details have no member IDs."""
    result = transform_pool_data(MOCK_POOL_DATA[:1], "test-cluster")

    assert result[0]["vm_ids"] == []
    assert result[0]["storage_ids"] == []
