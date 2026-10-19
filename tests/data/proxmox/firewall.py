"""
Mock data for Proxmox firewall tests.
"""

MOCK_CLUSTER_FIREWALL_RULES = [
    {
        "pos": 0,
        "type": "in",
        "action": "ACCEPT",
        "enable": 1,
        "proto": "tcp",
        "dport": "22",
        "source": "10.0.0.0/8",
        "comment": "Allow SSH from internal network",
    },
    {
        "pos": 1,
        "type": "in",
        "action": "ACCEPT",
        "enable": 1,
        "proto": "tcp",
        "dport": "443",
        "comment": "Allow HTTPS",
    },
    {
        "pos": 2,
        "type": "in",
        "action": "DROP",
        "enable": 1,
        "comment": "Drop all other incoming",
    },
]

MOCK_NODE_FIREWALL_RULES = {
    "node1": [
        {
            "pos": 0,
            "type": "in",
            "action": "ACCEPT",
            "enable": 1,
            "proto": "tcp",
            "dport": "8006",
            "comment": "Proxmox web UI",
        },
    ],
    "node2": [
        {
            "pos": 0,
            "type": "in",
            "action": "ACCEPT",
            "enable": 1,
            "proto": "tcp",
            "dport": "3128",
            "comment": "Proxy service",
        },
    ],
}

# Keyed by vmid. 100 is a QEMU VM on node1, 200 an LXC container on node2.
MOCK_VM_FIREWALL_RULES = {
    100: [
        {
            "pos": 0,
            "type": "in",
            "action": "ACCEPT",
            "enable": 1,
            "proto": "tcp",
            "dport": "443",
            "comment": "Web server",
        },
    ],
}

MOCK_CONTAINER_FIREWALL_RULES = {
    200: [
        {
            "pos": 0,
            "type": "in",
            "action": "ACCEPT",
            "enable": 1,
            "proto": "tcp",
            "dport": "5432",
            "source": "10.0.0.0/24",
            "comment": "PostgreSQL from app network",
        },
        {
            "pos": 1,
            "type": "in",
            "action": "DROP",
            "enable": 1,
            "comment": "Drop everything else",
        },
    ],
}

MOCK_CLUSTER_IPSETS = [
    {
        "name": "management-ips",
        "comment": "Management network IPs",
    },
    {
        "name": "backup-servers",
        "comment": "Backup server addresses",
    },
]

MOCK_IPSET_CIDRS = {
    "management-ips": [
        {"cidr": "10.0.1.0/24"},
        {"cidr": "10.0.2.0/24"},
    ],
    "backup-servers": [
        {"cidr": "192.168.10.5/32"},
        {"cidr": "192.168.10.6/32"},
    ],
}
