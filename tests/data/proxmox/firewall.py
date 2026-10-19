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
        "source": "+management-ips",
        "comment": "Allow HTTPS",
    },
    {
        "pos": 2,
        "type": "in",
        "action": "DROP",
        "enable": 1,
        # Built-in alias that the aliases endpoint does not list.
        "dest": "local_network",
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
            "source": "office",
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
            # Both names exist in the guest and in the cluster: the guest wins.
            "source": "office",
            "dest": "+backup-servers",
            "comment": "Web server",
        },
        {
            "pos": 1,
            "type": "group",
            "action": "webserver",
            "enable": 1,
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
            "dest": "+dc/backup-servers",
            "comment": "PostgreSQL from app network",
        },
        {
            "pos": 1,
            "type": "in",
            "action": "DROP",
            "enable": 1,
            # The container has no IP set of this name.
            "source": "+guest/backup-servers",
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
        {"cidr": "10.0.2.13", "nomatch": 1},
    ],
    "backup-servers": [
        {"cidr": "192.168.10.5/32"},
        {"cidr": "192.168.10.6/32"},
    ],
}

MOCK_CLUSTER_FIREWALL_OPTIONS = {
    "enable": 1,
    "policy_in": "DROP",
    "policy_out": "ACCEPT",
    "log_ratelimit": "enable=1,burst=5,rate=1/second",
    "digest": "0123456789abcdef",
}

MOCK_NODE_FIREWALL_OPTIONS = {
    "node1": {"log_level_in": "info", "nftables": 1, "nf_conntrack_max": 524288},
    "node2": {"enable": 0},
}

# Keyed by vmid. The container sets no option, so every value is the default.
MOCK_GUEST_FIREWALL_OPTIONS = {
    100: {"enable": 1, "policy_in": "DROP", "ipfilter": 1, "macfilter": 0},
    200: {},
}

MOCK_SECURITY_GROUPS = [
    {"group": "webserver", "comment": "HTTP and HTTPS", "digest": "abc"},
]

MOCK_SECURITY_GROUP_RULES = {
    "webserver": [
        {
            "pos": 0,
            "type": "in",
            "action": "ACCEPT",
            "enable": 1,
            "proto": "tcp",
            "dport": "80",
            "source": "+dc/management-ips",
        },
        {
            "pos": 1,
            "type": "in",
            "action": "ACCEPT",
            "enable": 1,
            "proto": "tcp",
            "dport": "443",
        },
    ],
}

MOCK_CLUSTER_ALIASES = [
    {"name": "office", "cidr": "203.0.113.0/24", "comment": "Office network"},
]

MOCK_GUEST_ALIASES = {
    100: [{"name": "office", "cidr": "198.51.100.10", "comment": "VM-local office"}],
    200: [],
}

MOCK_GUEST_IPSETS = {
    100: [{"name": "backup-servers", "comment": "VM-local backup servers"}],
    200: [],
}

MOCK_GUEST_IPSET_CIDRS = {
    (100, "backup-servers"): [
        {"cidr": "10.9.0.0/24"},
        {"cidr": "10.9.0.2", "nomatch": 1},
    ],
}
