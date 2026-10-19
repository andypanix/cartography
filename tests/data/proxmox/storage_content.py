"""
Mock data for Proxmox storage content tests.
"""

# /nodes/{node}/storage, keyed by node
MOCK_NODE_STORAGE_STATUS = {
    "node1": [
        {
            "storage": "local",
            "type": "dir",
            "content": "iso,vztmpl,backup",
            "active": 1,
            "enabled": 1,
            "shared": 0,
        },
        {
            "storage": "local-lvm",
            "type": "lvmthin",
            "content": "images,rootdir",
            "active": 1,
            "enabled": 1,
            "shared": 0,
        },
        {
            "storage": "pbs",
            "type": "pbs",
            "content": "backup",
            "active": 1,
            "enabled": 1,
            "shared": 1,
        },
        {
            "storage": "nfs-old",
            "type": "nfs",
            "content": "backup",
            "active": 0,
            "enabled": 1,
            "shared": 1,
        },
    ],
    "node2": [
        {
            "storage": "local",
            "type": "dir",
            "content": "iso,vztmpl,backup",
            "active": 1,
            "enabled": 1,
            "shared": 0,
        },
        {
            "storage": "pbs",
            "type": "pbs",
            "content": "backup",
            "active": 1,
            "enabled": 1,
            "shared": 1,
        },
    ],
}

# /nodes/{node}/storage/{storage}/content, keyed by (node, storage)
MOCK_STORAGE_CONTENT = {
    ("node1", "local"): [
        {
            "volid": "local:backup/vzdump-qemu-100-2026_10_01-02_00_00.vma.zst",
            "content": "backup",
            "format": "vma.zst",
            "size": 1073741824,
            "ctime": 1790820000,
            "vmid": 100,
            "notes": "web nightly",
            "protected": 1,
        },
        {
            "volid": "local:iso/debian-13.iso",
            "content": "iso",
            "format": "iso",
            "size": 700000000,
            "ctime": 1780000000,
        },
        {
            "volid": "local:vztmpl/debian-13-standard_13.0-1_amd64.tar.zst",
            "content": "vztmpl",
            "format": "tzst",
            "size": 120000000,
            "ctime": 1780000001,
        },
    ],
    ("node2", "local"): [
        # Same file name as on node1, on a different node's local storage
        {
            "volid": "local:backup/vzdump-qemu-100-2026_10_01-02_00_00.vma.zst",
            "format": "vma.zst",
            "size": 1073741000,
            "ctime": 1790820001,
            "vmid": 100,
        },
        # Guest volume, already modeled as a ProxmoxDisk
        {
            "volid": "local:200/vm-200-disk-0.raw",
            "content": "rootdir",
            "format": "raw",
            "size": 8589934592,
            "vmid": 200,
        },
    ],
    ("node1", "pbs"): [
        {
            "volid": "pbs:backup/ct/200/2026-10-01T03:00:00Z",
            "content": "backup",
            "format": "pbs-ct",
            "size": 2147483648,
            "ctime": 1790823600,
            "vmid": 200,
            "encrypted": "aa:bb:cc",
            "verification": {"state": "ok", "upid": "UPID:pbs:..."},
        },
        {
            "volid": "pbs:backup/vm/100/2026-10-01T02:00:00Z",
            "content": "backup",
            "format": "pbs-vm",
            "approximate-size": 4294967296,
            "ctime": 1790820000,
            "vmid": 100,
            "encrypted": "1",
            "verification": {"state": "failed", "upid": "UPID:pbs:..."},
        },
    ],
}
