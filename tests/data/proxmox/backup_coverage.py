"""
Mock data for Proxmox backup coverage tests.
"""

# /cluster/backup
MOCK_COVERAGE_BACKUP_JOBS = [
    {"id": "backup-all", "vmid": "all", "storage": "pbs", "enabled": 1},
    {"id": "backup-web", "vmid": "100", "storage": "local", "enabled": 1},
]

# /cluster/backup/{id}/included_volumes, keyed by job ID
MOCK_INCLUDED_VOLUMES = {
    "backup-all": {
        "children": [
            {
                "id": 100,
                "name": "web",
                "type": "qemu",
                "children": [
                    {
                        "id": "scsi0",
                        "name": "local-lvm:vm-100-disk-0",
                        "included": True,
                        "reason": "default backup",
                    },
                    {
                        "id": "scsi1",
                        "name": "local-lvm:vm-100-disk-1",
                        "included": False,
                        "reason": "disabled",
                    },
                ],
            },
            {
                "id": 200,
                "name": "ct",
                "type": "lxc",
                "children": [
                    {
                        "id": "rootfs",
                        "name": "local-lvm:vm-200-disk-0",
                        "included": True,
                        "reason": "rootfs",
                    },
                ],
            },
            # Removed but not purged guest
            {"id": 999, "type": "unknown"},
        ],
    },
    "backup-web": {
        "children": [
            {
                "id": 100,
                "name": "web",
                "type": "qemu",
                "children": [
                    {
                        "id": "scsi0",
                        "name": "local-lvm:vm-100-disk-0",
                        "included": True,
                        "reason": "default backup",
                    },
                ],
            },
        ],
    },
}

# /cluster/backup-info/not-backed-up
MOCK_NOT_BACKED_UP = [
    {"vmid": 101, "type": "qemu", "name": "scratch"},
]

# /nodes/{node}/vzdump/defaults, keyed by node
MOCK_VZDUMP_DEFAULTS = {
    "node1": {
        "storage": "pbs",
        "mode": "snapshot",
        "compress": "zstd",
        "bwlimit": 0,
        "ionice": 7,
        "protected": 0,
        "remove": 1,
        "notification-mode": "notification-system",
        "notes-template": "{{guestname}}",
        "prune-backups": "keep-daily=7,keep-last=3",
        "exclude-path": ["/tmp/?*", "/var/tmp/?*"],
        "stdexcludes": 1,
        "fleecing": "enabled=1,storage=local-lvm",
        "performance": "max-workers=16",
        "pbs-change-detection-mode": "metadata",
        "lockwait": 180,
        "stopwait": 10,
    },
    "node2": {
        "mode": "stop",
        "prune-backups": {"keep-all": "1"},
    },
}
