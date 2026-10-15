"""
Tests for Proxmox HA module.
"""

from cartography.intel.proxmox.ha import transform_ha_resource_data


def test_transform_ha_resource_data_parses_guest_vmid():
    """Guest service IDs yield the numeric VM ID used to match the protected guest."""
    resources = [
        {"sid": "vm:100", "state": "started"},
        {"sid": "ct:200", "state": "started"},
        {"sid": "vm:abc", "state": "started"},
        {"sid": "other:1", "state": "started"},
    ]

    result = transform_ha_resource_data(resources, "test-cluster")

    assert [(r["id"], r["vmid"]) for r in result] == [
        ("test-cluster/vm:100", 100),
        ("test-cluster/ct:200", 200),
        ("test-cluster/vm:abc", None),
        ("test-cluster/other:1", None),
    ]
