"""
Tests for the Proxmox resource mapping module.
"""

from cartography.intel.proxmox.mapping import extract_guest_mapping_refs
from cartography.intel.proxmox.mapping import parse_property_string
from cartography.intel.proxmox.mapping import transform_mapping_data
from tests.data.proxmox.mapping import MOCK_GUEST_CONFIGS
from tests.data.proxmox.mapping import MOCK_PCI_MAPPINGS


def test_parse_property_string_uses_default_key_for_bare_value():
    assert parse_property_string("shared,cache=auto", "dirid") == {
        "dirid": "shared",
        "cache": "auto",
    }
    assert parse_property_string("mapping=gpu, pcie=1", "host") == {
        "mapping": "gpu",
        "pcie": "1",
    }


def test_extract_guest_mapping_refs_reads_hostpci_usb_and_virtiofs():
    """Only mapping references count; host devices and other keys do not."""
    config = {
        **MOCK_GUEST_CONFIGS["node1/qemu/100"],
        "usb1": "host=1-2",
        "hostpci1": "0000:03:00.0",
        "net0": "virtio=BC:24:11:00:00:01,bridge=vmbr0",
        "usbhub": "mapping=not-a-device-key",
    }

    refs = extract_guest_mapping_refs(config, "c/node1/qemu/100")

    assert sorted((r["mapping_type"], r["mapping_id"]) for r in refs) == [
        ("dir", "shared"),
        ("pci", "gpu"),
        ("usb", "token"),
    ]
    assert {r["guest_id"] for r in refs} == {"c/node1/qemu/100"}


def test_extract_guest_mapping_refs_reads_explicit_dirid():
    refs = extract_guest_mapping_refs(
        MOCK_GUEST_CONFIGS["node2/qemu/101"],
        "c/node2/qemu/101",
    )

    assert [(r["mapping_type"], r["mapping_id"]) for r in refs] == [
        ("dir", "shared"),
    ]


def test_transform_mapping_data_links_nodes_and_guests_of_same_type():
    refs = [
        {"guest_id": "c/node1/qemu/100", "mapping_type": "pci", "mapping_id": "gpu"},
        # Same mapping ID under another type must not match the PCI mapping.
        {"guest_id": "c/node1/qemu/102", "mapping_type": "usb", "mapping_id": "gpu"},
    ]

    result = transform_mapping_data(MOCK_PCI_MAPPINGS, "pci", "c", refs)

    assert len(result) == 1
    mapping = result[0]
    assert mapping["id"] == "c/pci/gpu"
    assert mapping["mapping_id"] == "gpu"
    assert mapping["type"] == "pci"
    assert mapping["nodes"] == ["node1", "node2"]
    assert mapping["node_ids"] == ["c/node1", "c/node2"]
    assert mapping["guest_ids"] == ["c/node1/qemu/100"]
    assert mapping["map"] == MOCK_PCI_MAPPINGS[0]["map"]


def test_transform_mapping_data_handles_missing_map():
    result = transform_mapping_data([{"id": "empty"}], "usb", "c", [])

    assert result[0]["nodes"] == []
    assert result[0]["map"] == []
    assert result[0]["guest_ids"] == []
