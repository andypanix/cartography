"""
Mock API responses for Proxmox node hardware, software and system details.
"""

MOCK_NODES = [
    {"node": "node1", "status": "online"},
    {"node": "node2", "status": "offline"},
]

MOCK_DISKS = [
    {
        "devpath": "/dev/sda",
        "model": "Samsung SSD 870 EVO 1TB",
        "vendor": "ATA",
        "serial": "S6PTNM0R123456",
        "wwn": "0x5002538f4210abcd",
        "size": 1000204886016,
        "type": "ssd",
        "health": "PASSED",
        "used": "ZFS",
        "gpt": 1,
        "mounted": 0,
        "osdid": -1,
        "osdid-list": None,
    },
    {
        "devpath": "/dev/sdb",
        "model": "Samsung SSD 870 EVO 1TB",
        "vendor": "ATA",
        "serial": "S6PTNM0R654321",
        "wwn": "0x5002538f4210dcba",
        "size": 1000204886016,
        "type": "ssd",
        "health": "PASSED",
        "used": "ZFS",
        "gpt": 1,
        "mounted": 0,
        "osdid": -1,
        "osdid-list": None,
    },
    {
        "devpath": "/dev/nvme0n1",
        "model": "Samsung SSD 970 EVO Plus 1TB",
        "serial": "S4EWNX0R111111",
        "wwn": "eui.0025385791b0abcd",
        "size": 1000204886016,
        "type": "nvme",
        "health": "PASSED",
        "used": "LVM",
        "gpt": 1,
        "mounted": 0,
        "osdid": -1,
        "osdid-list": None,
    },
    {
        "devpath": "/dev/sdc",
        "model": "ST4000NM0035",
        "vendor": "ATA",
        "serial": "ZC1XYZ00",
        "wwn": "0x5000c500a1b2c3d4",
        "size": 4000787030016,
        "type": "hdd",
        "health": "PASSED",
        "used": "ext4",
        "gpt": 1,
        "mounted": 1,
        "osdid": -1,
        "osdid-list": None,
    },
]

MOCK_SMART = {
    "/dev/sda": {
        "health": "PASSED",
        "type": "ata",
        "attributes": [
            {
                "id": "  5",
                "name": "Reallocated_Sector_Ct",
                "normalized": 100,
                "value": 100,
                "worst": 100,
                "threshold": 10,
                "raw": "0",
                "flags": "PO--CK",
                "fail": "-",
            },
            {
                "id": "  9",
                "name": "Power_On_Hours",
                "normalized": 97,
                "value": 97,
                "worst": 97,
                "threshold": 0,
                "raw": "12045",
                "flags": "-O--CK",
                "fail": "-",
            },
            {
                "id": "177",
                "name": "Wear_Leveling_Count",
                "normalized": 98,
                "value": 98,
                "worst": 98,
                "threshold": 0,
                "raw": "11",
                "flags": "PO--C-",
                "fail": "-",
            },
            {
                "id": "190",
                "name": "Airflow_Temperature_Cel",
                "normalized": 66,
                "value": 66,
                "worst": 52,
                "threshold": 0,
                "raw": "34",
                "flags": "-O--CK",
                "fail": "-",
            },
        ],
    },
    "/dev/sdb": {
        "health": "PASSED",
        "type": "ata",
        "attributes": [
            {
                "id": "  5",
                "name": "Reallocated_Sector_Ct",
                "normalized": 100,
                "raw": "8",
            },
            {"id": "  9", "name": "Power_On_Hours", "normalized": 97, "raw": "12001"},
            {"id": "177", "name": "Wear_Leveling_Count", "normalized": 95, "raw": "30"},
            {
                "id": "194",
                "name": "Temperature_Celsius",
                "normalized": 64,
                "raw": "36 (Min/Max 20/45)",
            },
        ],
    },
    "/dev/nvme0n1": {
        "health": "PASSED",
        "type": "text",
        "text": (
            "\nSMART/Health Information (NVMe Log 0x02)\n"
            "Critical Warning:                   0x00\n"
            "Temperature:                        41 Celsius\n"
            "Available Spare:                    100%\n"
            "Available Spare Threshold:          10%\n"
            "Percentage Used:                    3%\n"
            "Data Units Read:                    12,345,678 [6.32 TB]\n"
            "Power On Hours:                     8,760\n"
            "Media and Data Integrity Errors:    0\n"
        ),
    },
    "/dev/sdc": {"health": "PASSED", "type": "ata", "attributes": []},
}

MOCK_ZFS_POOLS = [
    {
        "name": "rpool",
        "size": 996432412672,
        "alloc": 214748364800,
        "free": 781684047872,
        "frag": 7,
        "dedup": 1.0,
        "health": "DEGRADED",
    },
]

MOCK_ZFS_POOL_DETAILS = {
    "rpool": {
        "name": "rpool",
        "state": "DEGRADED",
        "status": "One or more devices has experienced an unrecoverable error.",
        "action": "Determine if the device needs to be replaced.",
        "scan": "scrub repaired 0B in 00:10:12 with 0 errors on Sun Oct 12 00:34:13 2026",
        "errors": "No known data errors",
        "children": [
            {
                "name": "rpool",
                "state": "DEGRADED",
                "read": 0,
                "write": 0,
                "cksum": 0,
                "msg": "",
                "children": [
                    {
                        "name": "mirror-0",
                        "state": "DEGRADED",
                        "read": 0,
                        "write": 0,
                        "cksum": 0,
                        "msg": "",
                        "children": [
                            {
                                "name": "ata-Samsung_SSD_870_EVO_1TB_S6PTNM0R123456-part3",
                                "state": "ONLINE",
                                "read": 0,
                                "write": 0,
                                "cksum": 0,
                                "msg": "",
                            },
                            {
                                "name": "wwn-0x5002538f4210dcba-part3",
                                "state": "FAULTED",
                                "read": 3,
                                "write": 0,
                                "cksum": 12,
                                "msg": "too many errors",
                            },
                        ],
                    },
                ],
            },
            {"name": "spares", "msg": ""},
        ],
    },
}

MOCK_LVM = {
    "leaf": 0,
    "children": [
        {
            "name": "pve",
            "size": 999653638144,
            "free": 16106127360,
            "leaf": 0,
            "children": [
                {
                    "name": "/dev/nvme0n1p3",
                    "size": 999653638144,
                    "free": 16106127360,
                    "leaf": 1,
                },
            ],
        },
    ],
}

MOCK_LVM_THIN = [
    {
        "lv": "data",
        "vg": "pve",
        "lv_size": 869730877440,
        "used": 123456789012,
        "metadata_size": 8875147264,
        "metadata_used": 123456789,
    },
]

MOCK_DIRECTORIES = [
    {
        "path": "/mnt/pve/backup",
        "device": "/dev/sdc1",
        "type": "ext4",
        "options": "defaults",
        "unitfile": "/etc/systemd/system/mnt-pve-backup.mount",
    },
]

MOCK_PACKAGE_VERSIONS = [
    {
        "Package": "proxmox-ve",
        "Version": "9.0.0",
        "CurrentState": "Installed",
        "Origin": "Proxmox",
        "Arch": "all",
        "Section": "admin",
        "Priority": "optional",
        "Title": "Proxmox Virtual Environment",
        "Description": "The Proxmox Virtual Environment",
        "RunningKernel": "6.14.8-2-pve",
    },
    {
        "Package": "pve-manager",
        "Version": "9.0.10",
        "CurrentState": "Installed",
        "Origin": "Proxmox",
        "Arch": "amd64",
        "Section": "admin",
        "Priority": "optional",
        "Title": "Proxmox Virtual Environment management tools",
        "Description": "",
        "ManagerVersion": "9.0.10",
    },
    {
        "Package": "qemu-server",
        "Version": "9.0.22",
        "OldVersion": "9.0.21",
        "CurrentState": "Installed",
        "Origin": "Proxmox",
        "Arch": "amd64",
        "Section": "admin",
        "Priority": "optional",
        "Title": "Qemu Server Tools",
        "Description": "",
    },
]

MOCK_APT_REPOSITORIES = {
    "digest": "abc123",
    "errors": [
        {"path": "/etc/apt/sources.list.d/broken.list", "error": "malformed entry"},
    ],
    "infos": [],
    "files": [
        {
            "path": "/etc/apt/sources.list.d/pve-enterprise.sources",
            "file-type": "sources",
            "digest": [1, 2, 3],
            "repositories": [
                {
                    "Types": ["deb"],
                    "URIs": ["https://enterprise.proxmox.com/debian/pve"],
                    "Suites": ["trixie"],
                    "Components": ["pve-enterprise"],
                    "Enabled": False,
                    "FileType": "sources",
                },
            ],
        },
        {
            "path": "/etc/apt/sources.list",
            "file-type": "list",
            "digest": [4, 5, 6],
            "repositories": [
                {
                    "Types": ["deb"],
                    "URIs": ["http://deb.debian.org/debian"],
                    "Suites": ["trixie"],
                    "Components": ["main", "contrib"],
                    "Enabled": True,
                    "FileType": "list",
                },
                {
                    "Types": ["deb"],
                    "URIs": ["http://download.proxmox.com/debian/pve"],
                    "Suites": ["trixie"],
                    "Components": ["pve-no-subscription"],
                    "Enabled": True,
                    "FileType": "list",
                    "Comment": "no-subscription repo",
                },
            ],
        },
    ],
    "standard-repos": [
        {"handle": "enterprise", "name": "Enterprise", "status": False},
        {"handle": "no-subscription", "name": "No-Subscription", "status": True},
        {"handle": "test", "name": "Test"},
        {
            "handle": "ceph-squid-no-subscription",
            "name": "Ceph Squid No-Subscription",
            "status": True,
        },
    ],
}

MOCK_APT_REPOSITORIES_WITH_CREDENTIALS = {
    "errors": [
        {
            "path": "/etc/apt/sources.list.d/private.list",
            "error": "bad line: deb https://ci:s3cr3t@repo.example.com/debian",
        },
    ],
    "files": [
        {
            "path": "/etc/apt/sources.list.d/private.list",
            "file-type": "list",
            "repositories": [
                {
                    "Types": ["deb"],
                    "URIs": [
                        "https://ci:s3cr3t@repo.example.com/debian",
                        "https://mirror.example.com/x?access_token=s3cr3t&dist=1",
                    ],
                    "Suites": ["trixie"],
                    "Components": ["main"],
                    "Enabled": True,
                    "FileType": "list",
                    "Comment": "mirror https://ci:s3cr3t@repo.example.com/debian",
                },
            ],
        },
    ],
    "standard-repos": [],
}

MOCK_SUBSCRIPTION = {
    "status": "active",
    "level": "c",
    "productname": "Proxmox VE Community Subscription 1 CPU/year",
    "regdate": "2026-01-01 00:00:00",
    "nextduedate": "2027-01-01",
    "checktime": 1760000000,
    "sockets": 1,
    "message": "",
    "key": "pve1c-0123456789ab",
    "serverid": "0123456789ABCDEF0123456789ABCDEF",
    "signature": "SIGNATURE-DO-NOT-STORE",
    "url": "https://www.proxmox.com/en/proxmox-virtual-environment/pricing",
}

MOCK_NODE_CONFIG = {
    "description": "Rack 3, unit 12",
    "wakeonlan": "aa:bb:cc:dd:ee:ff,bind-interface=eno1",
    "ballooning-target": 75,
    "startall-onboot-delay": 10,
    "acme": "account=prod,domains=node1.example.com",
    "acmedomain0": "node1-alt.example.com,plugin=cloudflare",
    "digest": "deadbeef",
}

MOCK_NODE_DNS = {"dns1": "10.0.0.53", "dns2": "1.1.1.1", "search": "example.com"}

MOCK_NODE_TIME = {
    "timezone": "Europe/Rome",
    "time": 1760000000,
    "localtime": 1760007200,
}

MOCK_SERVICES = [
    {
        "service": "pveproxy",
        "name": "pveproxy",
        "desc": "PVE API Proxy Server",
        "state": "running",
        "active-state": "active",
        "unit-state": "enabled",
    },
    {
        "service": "corosync",
        "name": "corosync",
        "desc": "Corosync Cluster Engine",
        "state": "dead",
        "active-state": "inactive",
        "unit-state": "disabled",
    },
]

# /nodes/{node}/services/{service}/state, read after the list: corosync was
# started in between, so the state endpoint has the newer values.
MOCK_SERVICE_STATES = {
    "pveproxy": {
        "service": "pveproxy",
        "name": "pveproxy",
        "desc": "PVE API Proxy Server",
        "state": "running",
        "active-state": "active",
        "unit-state": "enabled",
    },
    "corosync": {
        "service": "corosync",
        "name": "corosync",
        "desc": "Corosync Cluster Engine",
        "state": "running",
        "active-state": "active",
        "unit-state": "enabled",
    },
}

MOCK_PCI_DEVICES = [
    {
        "id": "0000:01:00.0",
        "class": "0x030000",
        "vendor": "0x10de",
        "vendor_name": "NVIDIA Corporation",
        "device": "0x1eb8",
        "device_name": "TU104GL [Tesla T4]",
        "subsystem_vendor": "0x10de",
        "subsystem_vendor_name": "NVIDIA Corporation",
        "subsystem_device": "0x12a2",
        "subsystem_device_name": "",
        "iommugroup": 14,
        "mdev": 1,
    },
    {
        "id": "0000:02:00.0",
        "class": "0x020000",
        "vendor": "0x8086",
        "vendor_name": "Intel Corporation",
        "device": "0x1533",
        "device_name": "I210 Gigabit Network Connection",
        "iommugroup": 15,
    },
]

MOCK_PCI_MDEV_TYPES = {
    "0000:01:00.0": [
        {
            "type": "nvidia-222",
            "name": "GRID T4-1B",
            "description": "",
            "available": 16,
        },
        {"type": "nvidia-223", "name": "GRID T4-2B", "description": "", "available": 8},
    ],
}
