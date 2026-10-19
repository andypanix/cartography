"""
Mock Proxmox VE SDN API responses.

One EVPN zone with a VNet attached to guest 100, one VLAN zone over vmbr0, an
EVPN controller on a fabric, the built-in IPAM, a PowerDNS plugin, an
OpenFabric fabric of two nodes, a prefix list and a route map.
"""

MOCK_ZONES = [
    {
        "zone": "evpn1",
        "type": "evpn",
        "controller": "evpnctl",
        "vrf-vxlan": 10000,
        "mac": "BC:24:11:00:00:01",
        "exitnodes": "pve1",
        "advertise-subnets": 1,
        "ipam": "pve",
        "dns": "pdns",
        "reversedns": "pdns",
        "dnszone": "example.internal",
        "mtu": 1450,
        "rt-import": "65000:100,65000:200",
    },
    {
        "zone": "vlan1",
        "type": "vlan",
        "bridge": "vmbr0",
        "nodes": "pve1,pve2",
        "ipam": "pve",
    },
]

MOCK_VNETS = [
    {"vnet": "vnet1", "zone": "evpn1", "tag": 11000, "alias": "web", "type": "vnet"},
    {"vnet": "vlan10", "zone": "vlan1", "tag": 10, "vlanaware": 0, "type": "vnet"},
]

MOCK_SUBNETS = {
    "vnet1": [
        {
            "subnet": "evpn1-10.10.0.0-24",
            "cidr": "10.10.0.0/24",
            "type": "subnet",
            "vnet": "vnet1",
            "zone": "evpn1",
            "gateway": "10.10.0.1",
            "snat": 1,
            "dhcp-range": ["start-address=10.10.0.100,end-address=10.10.0.200"],
        },
    ],
    # No cidr field: the CIDR is derived from the subnet ID.
    "vlan10": [
        {"subnet": "vlan1-192.168.10.0-24", "type": "subnet", "vnet": "vlan10"},
    ],
}

MOCK_VNET_FIREWALL_OPTIONS = {
    "vnet1": {"enable": 1, "policy_forward": "DROP", "log_level_forward": "info"},
    "vlan10": {},
}

MOCK_VNET_FIREWALL_RULES = {
    "vnet1": [
        {
            "pos": 0,
            "type": "forward",
            "action": "ACCEPT",
            "enable": 1,
            "source": "10.10.0.0/24",
            "proto": "tcp",
            "dport": "443",
        },
    ],
    "vlan10": [],
}

MOCK_CONTROLLERS = [
    {
        "controller": "evpnctl",
        "type": "evpn",
        "asn": 65000,
        "fabric": "fab1",
        "route-map-out": "bgp-out",
    },
    {
        "controller": "bgp-pve1",
        "type": "bgp",
        "asn": 65001,
        "node": "pve1",
        "peers": "192.0.2.254",
        "ebgp": 1,
    },
]

MOCK_IPAMS = [
    {"ipam": "pve", "type": "pve"},
    {"ipam": "netbox", "type": "netbox", "url": "https://netbox.example/api"},
]

MOCK_IPAM_STATUS = {
    "pve": [
        {
            "zone": "evpn1",
            "subnet": "10.10.0.0/24",
            "vnet": "vnet1",
            "ip": "10.10.0.1",
            "gateway": 1,
        },
        {
            "zone": "evpn1",
            "subnet": "10.10.0.0/24",
            "vnet": "vnet1",
            "ip": "10.10.0.100",
            "mac": "BC:24:11:AA:BB:CC",
            "hostname": "web01",
            "vmid": 100,
        },
    ],
}

MOCK_DNS = [
    {"dns": "pdns", "type": "powerdns", "url": "https://pdns.example/api/v1"},
]

MOCK_FABRICS = {
    "fabrics": [
        {
            "id": "fab1",
            "protocol": "openfabric",
            "ip_prefix": "192.0.2.0/24",
            "hello_interval": 3,
            "route_filter": "internal",
        },
    ],
    "nodes": [
        {
            "fabric_id": "fab1",
            "node_id": "pve1",
            "protocol": "openfabric",
            "ip": "192.0.2.1",
            "interfaces": ["name=ens19,ip=198.51.100.1/31"],
        },
        {
            "fabric_id": "fab1",
            "node_id": "pve2",
            "protocol": "openfabric",
            "ip": "192.0.2.2",
            "interfaces": [{"name": "ens19", "ip": "198.51.100.2/31"}],
        },
    ],
}

MOCK_PREFIX_LISTS = [
    {
        "id": "internal",
        "entries": [
            "action=deny,prefix=10.0.0.0/8,le=32,seq=20",
            "action=permit,prefix=10.0.0.0/8,ge=16,le=24,seq=10",
        ],
    },
]

MOCK_ROUTE_MAPS = [{"id": "bgp-out"}]

MOCK_ROUTE_MAP_ENTRIES = [
    {
        "route-map-id": "bgp-out",
        "order": 10,
        "action": "permit",
        "match": ["key=ip-address-prefix-list,value=internal"],
        "set": ["key=local-preference,value=50"],
    },
    {"route-map-id": "bgp-out", "order": 20, "action": "permit"},
]

MOCK_NODES = [
    {"node": "pve1", "status": "online"},
    {"node": "pve2", "status": "online"},
    {"node": "pve3", "status": "offline"},
]

MOCK_NODE_ZONES = {
    "pve1": [
        {"zone": "evpn1", "status": "available"},
        {"zone": "vlan1", "status": "available"},
    ],
    "pve2": [{"zone": "vlan1", "status": "error"}],
}

MOCK_NODE_ZONE_CONTENT = {
    ("pve1", "evpn1"): [{"vnet": "vnet1", "status": "available"}],
    ("pve1", "vlan1"): [{"vnet": "vlan10", "status": "available"}],
    ("pve2", "vlan1"): [
        {"vnet": "vlan10", "status": "error", "statusmsg": "missing bridge"},
    ],
}

MOCK_NODE_ZONE_BRIDGES = {
    ("pve1", "evpn1"): [
        {
            "name": "vnet1",
            "vlan_filtering": "0",
            "ports": [
                {"name": "tap100i0", "vmid": 100, "index": "0"},
                {"name": "vxlan_vnet1"},
            ],
        },
    ],
}

MOCK_NODE_ZONE_IP_VRF = {
    ("pve1", "evpn1"): [
        {
            "ip": "0.0.0.0/0",
            "nexthops": ["192.0.2.254"],
            "protocol": "bgp",
            "metric": 20,
        },
    ],
}

MOCK_NODE_VNET_MAC_VRF = {
    ("pve1", "vnet1"): [
        {"ip": "10.10.0.100", "mac": "BC:24:11:AA:BB:CC", "nexthop": "192.0.2.1"},
    ],
}

MOCK_NODE_FABRIC_INTERFACES = {
    ("pve1", "fab1"): [{"name": "ens19", "state": "up", "type": "Point-To-Point"}],
    ("pve2", "fab1"): [{"name": "ens19", "state": "up", "type": "Point-To-Point"}],
}

MOCK_NODE_FABRIC_NEIGHBORS = {
    ("pve1", "fab1"): [{"neighbor": "pve2", "status": "Up", "uptime": "1h2m3s"}],
    # FRR may report the neighbor by address instead of hostname.
    ("pve2", "fab1"): [
        {"neighbor": "198.51.100.1", "status": "Up", "uptime": "1h2m3s"},
        {"neighbor": "203.0.113.9", "status": "Initializing", "uptime": "1s"},
    ],
}

MOCK_NODE_FABRIC_ROUTES = {
    ("pve1", "fab1"): [{"route": "192.0.2.2/32", "via": ["198.51.100.2"]}],
    ("pve2", "fab1"): [{"route": "192.0.2.1/32", "via": ["198.51.100.1"]}],
}
