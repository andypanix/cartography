"""
Mock data for Proxmox pool tests.
"""

MOCK_POOL_DATA = [
    {
        "poolid": "production",
        "comment": "Production VMs and containers",
    },
    {
        "poolid": "development",
        "comment": "Development environment",
    },
    {
        "poolid": "backup-storage",
        "comment": "Backup storage resources",
    },
]

# Nested pools, listed child first to check that parents load first.
MOCK_NESTED_POOL_DATA = [
    {"poolid": "development/team1/frontend", "comment": "Frontend team"},
    {"poolid": "development/team1", "comment": "Team 1"},
    {"poolid": "development", "comment": "Development environment"},
]

MOCK_POOL_DETAILS = {
    "production": {
        "poolid": "production",
        "comment": "Production VMs and containers",
        "members": [
            {
                "type": "qemu",
                "vmid": 100,
                "node": "node1",
                "id": "qemu/100",
            },
            {
                "type": "lxc",
                "vmid": 200,
                "node": "node2",
                "id": "lxc/200",
            },
        ],
    },
    "development": {
        "poolid": "development",
        "comment": "Development environment",
        "members": [
            {
                "type": "qemu",
                "vmid": 101,
                "node": "node1",
                "id": "qemu/101",
            },
        ],
    },
    "backup-storage": {
        "poolid": "backup-storage",
        "comment": "Backup storage resources",
        "members": [
            {
                "type": "storage",
                "storage": "nfs-backup",
                "id": "storage/nfs-backup",
            },
        ],
    },
}
