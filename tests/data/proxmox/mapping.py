"""
Mock data for Proxmox resource mapping tests.
"""

MOCK_PCI_MAPPINGS = [
    {
        "id": "gpu",
        "description": "NVIDIA GPU for ML guests",
        "map": [
            "node=node1,path=0000:01:00.0,id=10de:2204,iommugroup=12",
            "node=node2,path=0000:02:00.0,id=10de:2204,iommugroup=14",
        ],
    },
]

MOCK_USB_MAPPINGS = [
    {
        "id": "token",
        "description": "Hardware security key",
        "map": ["node=node1,id=1050:0407"],
    },
]

MOCK_DIR_MAPPINGS = [
    {
        "id": "shared",
        "description": "Shared datasets",
        "map": ["node=node1,path=/srv/shared", "node=node2,path=/srv/shared"],
    },
]

# VM configurations, keyed by VM graph ID inside the cluster (node/type/vmid).
MOCK_GUEST_CONFIGS = {
    "node1/qemu/100": {
        "hostpci0": "mapping=gpu,pcie=1",
        "usb0": "mapping=token,usb3=1",
        "virtiofs0": "shared,cache=auto",
    },
    "node2/qemu/101": {
        "hostpci0": "0000:03:00.0,pcie=1",
        "usb0": "host=1-2",
        "virtiofs1": "dirid=shared",
    },
}
