"""
Mock Proxmox VE Ceph API responses.

Shapes follow the Proxmox VE 9 API schema; node1 and node2 run Ceph, node3
has no Ceph packages.
"""

from proxmoxer.core import ResourceException

MOCK_CEPH_FSID = "8d3b2c4e-1f2a-4b5c-9d6e-7f8a9b0c1d2e"

MOCK_CEPH_STATUS = {
    "fsid": MOCK_CEPH_FSID,
    "health": {
        "status": "HEALTH_WARN",
        "checks": {
            "OSD_DOWN": {
                "severity": "HEALTH_WARN",
                "summary": {"message": "1 osd down"},
            },
            "POOL_NO_REDUNDANCY": {
                "severity": "HEALTH_WARN",
                "summary": {"message": "1 pool(s) have no replicas configured"},
            },
        },
        "mutes": [],
    },
    "quorum_names": ["node1", "node2"],
}

MOCK_CEPH_METADATA = {
    "mon": {
        "node1@node1": {
            "name": "node1",
            "hostname": "node1",
            "ceph_version_short": "19.2.1",
        },
        "node2@node2": {
            "name": "node2",
            "hostname": "node2",
            "ceph_version_short": "19.2.1",
        },
    },
    "mgr": {
        "node1@node1": {
            "name": "node1",
            "hostname": "node1",
            "ceph_version_short": "19.2.1",
        },
    },
    "mds": {
        "node2@node2": {
            "name": "node2",
            "hostname": "node2",
            "ceph_version_short": "19.2.0",
        },
    },
    "osd": [
        {"id": 0, "hostname": "node1", "ceph_version_short": "19.2.1"},
        {"id": 1, "hostname": "node2", "ceph_version_short": "19.2.1"},
    ],
    "node": {
        "node1": {"version": {"str": "19.2.1", "parts": ["19", "2", "1"]}},
        "node2": {"version": {"str": "19.2.1", "parts": ["19", "2", "1"]}},
    },
}

MOCK_CEPH_FLAGS = [
    {
        "name": "noout",
        "description": "OSDs will not automatically be marked out.",
        "value": 1,
    },
    {"name": "noscrub", "description": "Scrubbing is disabled.", "value": 0},
    {"name": "pause", "description": "Pauses read and writes.", "value": 0},
]

MOCK_CEPH_HEALTH_MUTES = [
    {
        "code": "POOL_NO_REDUNDANCY",
        "sticky": 0,
        "summary": "1 pool(s) have no replicas configured",
    },
]

MOCK_CEPH_MONITORS = [
    {
        "name": "node1",
        "host": "node1",
        "addr": "10.0.0.11:6789/0",
        "rank": 0,
        "quorum": 1,
        "state": "running",
        "service": 1,
        "direxists": 1,
        "ceph_version_short": "19.2.1",
    },
    {
        "name": "node2",
        "host": "node2",
        "addr": "10.0.0.12:6789/0",
        "rank": 1,
        "quorum": 1,
        "state": "running",
        "ceph_version_short": "19.2.1",
    },
]

MOCK_CEPH_MANAGERS = [
    {
        "name": "node1",
        "host": "node1",
        "addr": "10.0.0.11:6801/1234",
        "state": "active",
        "ceph_version_short": "19.2.1",
    },
    {"name": "node2", "host": "node2", "state": "standby"},
]

MOCK_CEPH_METADATA_SERVERS = [
    {
        "name": "node2",
        "host": "node2",
        "addr": "10.0.0.12:6800/5678",
        "state": "up:active",
        "rank": 0,
        "standby_replay": 0,
        "fs_name": "cephfs",
        "ceph_version_short": "19.2.0",
    },
]

MOCK_CEPH_OSD_TREE = {
    "flags": "noout",
    "root": {
        "leaf": 0,
        "children": [
            {
                "id": -1,
                "name": "default",
                "type": "root",
                "children": [
                    {
                        "id": -3,
                        "name": "node1",
                        "type": "host",
                        "children": [
                            {
                                "id": 0,
                                "name": "osd.0",
                                "type": "osd",
                                "host": "node1",
                                "status": "up",
                                "in": 1,
                                "crush_weight": 0.9,
                                "device_class": "ssd",
                                "leaf": 1,
                            },
                        ],
                    },
                    {
                        "id": -5,
                        "name": "node2",
                        "type": "host",
                        "children": [
                            {
                                "id": 1,
                                "name": "osd.1",
                                "type": "osd",
                                "host": "node2",
                                "status": "down",
                                "in": 0,
                                "crush_weight": 0.9,
                                "device_class": "hdd",
                                "leaf": 1,
                            },
                        ],
                    },
                ],
            },
        ],
    },
}

MOCK_CEPH_OSD_METADATA = {
    0: {
        "osd": {
            "id": 0,
            "hostname": "node1",
            "osd_objectstore": "bluestore",
            "encrypted": 1,
            "version": "ceph version 19.2.1 squid (stable)",
            "front_addr": "10.0.0.11:6802/1111",
            "back_addr": "10.10.0.11:6803/1111",
        },
        "devices": [
            {
                "device": "block",
                "physical_device": "sdb",
                "type": "ssd",
                "size": 960197124096,
            },
            {
                "device": "db",
                "physical_device": "nvme0n1",
                "type": "ssd",
                "size": 64424509440,
            },
        ],
    },
    1: {
        "osd": {
            "id": 1,
            "hostname": "node2",
            "osd_objectstore": "bluestore",
            "encrypted": 0,
            "version": "ceph version 19.2.1 squid (stable)",
        },
        "devices": [
            {
                "device": "block",
                "physical_device": "sdc",
                "type": "hdd",
                "size": 960197124096,
            },
        ],
    },
}

MOCK_CEPH_OSD_LV_INFO = {
    0: {
        "lv_name": "osd-block-1a2b",
        "lv_path": "/dev/ceph-1a2b/osd-block-1a2b",
        "lv_size": 960193052672,
        "lv_uuid": "abcd-1234",
        "vg_name": "ceph-1a2b",
        "creation_time": "2025-01-10 10:00:00 +0100",
    },
}

# osd.1 has no LVM volume (created outside ceph-volume lvm)
MOCK_CEPH_OSD_LV_INFO_ERROR = ResourceException(
    500,
    "Internal Server Error",
    "OSD '1' not found in 'ceph-volume lvm list' on node 'node2'.",
)

MOCK_CEPH_RULES = [
    {"name": "replicated_rule"},
    {"name": "ssd_only"},
]

# /nodes/{node}/ceph/crush: the CRUSH map as `crushtool -d` writes it on
# Ceph Squid, with a rack level between the root and the hosts, shadow class
# IDs, a device-class rule, and a choose_args section.
MOCK_CEPH_CRUSH_MAP = """# begin crush map
tunable choose_local_tries 0
tunable choose_local_fallback_tries 0
tunable choose_total_tries 50
tunable chooseleaf_descend_once 1
tunable chooseleaf_vary_r 1
tunable chooseleaf_stable 1
tunable straw_calc_version 1
tunable allowed_bucket_algs 54

# devices
device 0 osd.0 class ssd
device 1 osd.1 class hdd

# types
type 0 osd
type 1 host
type 2 chassis
type 3 rack
type 4 row
type 5 pdu
type 6 pod
type 7 room
type 8 datacenter
type 9 zone
type 10 region
type 11 root

# buckets
host node1 {
\tid -3\t\t# do not change unnecessarily
\tid -4 class ssd\t\t# do not change unnecessarily
\tid -7 class hdd\t\t# do not change unnecessarily
\t# weight 0.90000
\talg straw2
\thash 0\t# rjenkins1
\titem osd.0 weight 0.90000
}
host node2 {
\tid -5\t\t# do not change unnecessarily
\tid -6 class ssd\t\t# do not change unnecessarily
\tid -8 class hdd\t\t# do not change unnecessarily
\t# weight 0.90000
\talg straw2
\thash 0\t# rjenkins1
\titem osd.1 weight 0.90000
}
rack rack1 {
\tid -9\t\t# do not change unnecessarily
\tid -10 class ssd\t\t# do not change unnecessarily
\tid -11 class hdd\t\t# do not change unnecessarily
\t# weight 1.80000
\talg straw2
\thash 0\t# rjenkins1
\titem node1 weight 0.90000
\titem node2 weight 0.90000
}
root default {
\tid -1\t\t# do not change unnecessarily
\tid -2 class ssd\t\t# do not change unnecessarily
\tid -12 class hdd\t\t# do not change unnecessarily
\t# weight 1.80000
\talg straw2
\thash 0\t# rjenkins1
\titem rack1 weight 1.80000
}

# rules
rule replicated_rule {
\tid 0
\ttype replicated
\tstep take default
\tstep chooseleaf firstn 0 type host
\tstep emit
}
rule ssd_only {
\tid 1
\ttype replicated
\tstep take default class ssd
\tstep chooseleaf firstn 0 type rack
\tstep emit
}

# choose_args
choose_args 18446744073709551615 {
  {
    bucket_id -1
    weight_set [
      [ 1.800 ]
    ]
  }
}

# end crush map
"""

MOCK_CEPH_POOLS = [
    {
        "pool": 1,
        "pool_name": ".mgr",
        "type": "replicated",
        "size": 3,
        "min_size": 2,
        "pg_num": 1,
        "crush_rule": 0,
        "crush_rule_name": "replicated_rule",
        "application_metadata": {"mgr": {}},
    },
    {
        "pool": 2,
        "pool_name": "vm-pool",
        "type": "replicated",
        "size": 3,
        "min_size": 2,
        "pg_num": 128,
        "pg_autoscale_mode": "on",
        "crush_rule": 1,
        "crush_rule_name": "ssd_only",
        "application_metadata": {"rbd": {}},
        "bytes_used": 1073741824,
        "percent_used": 0.05,
    },
    {
        "pool": 3,
        "pool_name": "cephfs_data",
        "type": "replicated",
        "size": 1,
        "min_size": 1,
        "pg_num": 32,
        "crush_rule": 0,
        "crush_rule_name": "replicated_rule",
        "application_metadata": {"cephfs": {"data": "cephfs"}},
    },
    {
        "pool": 4,
        "pool_name": "cephfs_metadata",
        "type": "replicated",
        "size": 3,
        "min_size": 2,
        "pg_num": 16,
        "crush_rule": 0,
        "crush_rule_name": "replicated_rule",
        "application_metadata": {"cephfs": {"metadata": "cephfs"}},
    },
]

MOCK_CEPH_POOL_STATUS = {
    "vm-pool": {
        "name": "vm-pool",
        "id": 2,
        "nodelete": 1,
        "nosizechange": 0,
        "nopgchange": 0,
        "noscrub": 0,
        "nodeep-scrub": 0,
        "application_list": ["rbd"],
    },
}

MOCK_CEPH_FILESYSTEMS = [
    {
        "name": "cephfs",
        "metadata_pool": "cephfs_metadata",
        "metadata_pool_id": 4,
        "data_pool": "cephfs_data",
        "data_pools": ["cephfs_data"],
        "data_pool_ids": [3],
    },
]

MOCK_CEPH_NODES = [
    {"node": "node1", "status": "online"},
    {"node": "node2", "status": "online"},
    {"node": "node3", "status": "online"},
]

# Storage definitions from /storage: two hyper-converged Ceph storages, one
# external RBD storage that must not link to the local pools, and a local dir.
MOCK_CEPH_STORAGE = [
    {"storage": "ceph-vm", "type": "rbd", "pool": "vm-pool", "content": "images"},
    {"storage": "cephfs", "type": "cephfs", "content": "backup,iso"},
    {
        "storage": "external-rbd",
        "type": "rbd",
        "pool": "vm-pool",
        "monhost": "10.1.1.20 10.1.1.21",
    },
    {"storage": "local", "type": "dir", "path": "/var/lib/vz"},
]

MOCK_CEPH_NOT_INSTALLED_ERROR = ResourceException(
    500,
    "Internal Server Error",
    "binary not installed: /usr/bin/ceph-mon",
)

MOCK_CEPH_NOT_INITIALIZED_ERROR = ResourceException(
    500,
    "Internal Server Error",
    "pveceph configuration not initialized - missing '/etc/pve/ceph.conf'",
)

# A node that went offline answers 595 through the API proxy.
MOCK_CEPH_UNREACHABLE_ERROR = ResourceException(
    595,
    "Connection refused",
    "",
)
