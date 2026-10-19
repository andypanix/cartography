"""
Tests for Proxmox pool module.
"""

from unittest.mock import MagicMock

from cartography.intel.proxmox.pool import get_pool_details
from cartography.intel.proxmox.pool import transform_pool_data
from tests.data.proxmox.pool import MOCK_NESTED_POOL_DATA
from tests.data.proxmox.pool import MOCK_POOL_DATA
from tests.data.proxmox.pool import MOCK_POOL_DETAILS


def test_transform_pool_data_lists_member_ids():
    """Guest and storage members map to cluster-prefixed ProxmoxVM and storage IDs."""
    result = transform_pool_data(MOCK_POOL_DATA, "test-cluster", MOCK_POOL_DETAILS)

    members = {r["id"]: (r["vm_ids"], r["storage_ids"]) for r in result}
    assert members == {
        "test-cluster/production": (
            ["test-cluster/node1/qemu/100", "test-cluster/node2/lxc/200"],
            [],
        ),
        "test-cluster/development": (["test-cluster/node1/qemu/101"], []),
        "test-cluster/backup-storage": ([], ["test-cluster/nfs-backup"]),
    }


def test_transform_pool_data_without_details():
    """Pools without member details have no member IDs."""
    result = transform_pool_data(MOCK_POOL_DATA[:1], "test-cluster")

    assert result[0]["vm_ids"] == []
    assert result[0]["storage_ids"] == []
    assert result[0]["parent_poolid"] is None
    assert result[0]["parent_pool_id"] is None


def test_transform_pool_data_nested_pools():
    """Nested pools point to their direct parent, and parents come first."""
    result = transform_pool_data(MOCK_NESTED_POOL_DATA, "c")

    assert [(r["id"], r["parent_poolid"], r["parent_pool_id"]) for r in result] == [
        ("c/development", None, None),
        ("c/development/team1", "development", "c/development"),
        (
            "c/development/team1/frontend",
            "development/team1",
            "c/development/team1",
        ),
    ]


def test_get_pool_details_uses_pools_query():
    """Pool details come from GET /pools?poolid=<id>, not the deprecated /pools/{poolid}."""
    client = MagicMock()
    client.pools.get.return_value = [MOCK_POOL_DETAILS["production"]]

    assert get_pool_details(client, "production") == MOCK_POOL_DETAILS["production"]
    client.pools.get.assert_called_once_with(poolid="production")
    client.pools.assert_not_called()


def test_get_pool_details_without_entry():
    """An empty answer yields empty details."""
    client = MagicMock()
    client.pools.get.return_value = []

    assert get_pool_details(client, "gone") == {}
