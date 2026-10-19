"""
Mock data for Proxmox replication tests.
"""

# /cluster/replication
MOCK_REPLICATION_JOBS = [
    {
        "id": "100-0",
        "type": "local",
        "guest": 100,
        "jobnum": 0,
        "target": "node2",
        "schedule": "*/5",
        "rate": 50,
        "comment": "web to node2",
        "source": "node1",
    },
    {
        "id": "200-0",
        "type": "local",
        "guest": 200,
        "jobnum": 0,
        "target": "node1",
        "disable": 1,
    },
]

# /nodes/{node}/replication, keyed by node
MOCK_NODE_REPLICATION = {
    "node1": [
        {
            "id": "100-0",
            "guest": 100,
            "target": "node2",
            "last_sync": 1790820000,
            "last_try": 1790820300,
            "next_sync": 1790820600,
            "duration": 4.2,
            "fail_count": 2,
            "error": "storage 'local-zfs' is not available on node 'node2'",
        },
    ],
    # Only the ID: the per-job status endpoint is called for this one
    "node2": [{"id": "200-0"}],
}

# /nodes/{node}/replication/{id}/status, keyed by (node, job ID)
MOCK_REPLICATION_STATUS = {
    ("node2", "200-0"): {
        "id": "200-0",
        "guest": 200,
        "last_sync": 1790800000,
        "fail_count": 0,
    },
}
