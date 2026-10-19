"""
Mock data for Proxmox HA tests.
"""

MOCK_HA_GROUP_DATA = [
    {
        "group": "ha-group-1",
        "nodes": "node1,node2",
        "restricted": 0,
        "nofailback": 0,
        "comment": "Primary HA group",
    },
    {
        "group": "ha-group-2",
        "nodes": "node2",
        "restricted": 1,
        "nofailback": 1,
        "comment": "Secondary HA group with restrictions",
    },
]

MOCK_HA_RESOURCE_DATA = [
    {
        "sid": "vm:100",
        "state": "started",
        "group": "ha-group-1",
        "max_restart": 3,
        "max_relocate": 2,
        "comment": "Production VM with HA",
    },
    {
        "sid": "ct:200",
        "state": "started",
        "group": "ha-group-1",
        "max_restart": 2,
        "max_relocate": 1,
        "comment": "Production container with HA",
    },
    {
        "sid": "vm:101",
        "state": "stopped",
        "group": "ha-group-2",
        "max_restart": 1,
        "max_relocate": 0,
    },
]

# Proxmox VE 9 after the HA groups were migrated to HA rules: resources have
# no group and carry failback.
MOCK_HA_RESOURCE_DATA_PVE9 = [
    {
        "sid": "vm:100",
        "type": "vm",
        "state": "started",
        "failback": 1,
        "max_restart": 3,
        "max_relocate": 2,
        "comment": "Production VM with HA",
    },
    {
        "sid": "ct:200",
        "type": "ct",
        "state": "started",
        "failback": 0,
        "auto-rebalance": 0,
    },
    {
        "sid": "vm:101",
        "type": "vm",
        "state": "stopped",
    },
]

MOCK_HA_RULE_DATA = [
    {
        "rule": "ha-group-1",
        "type": "node-affinity",
        "resources": "vm:100,ct:200",
        "nodes": "node1:2,node2",
        "strict": 0,
        "comment": "Migrated from HA group ha-group-1",
    },
    {
        "rule": "keep-apart",
        "type": "resource-affinity",
        "resources": "vm:100,vm:101",
        "affinity": "negative",
        "disable": 1,
    },
]

MOCK_HA_STATUS_DATA = [
    {"id": "quorum", "type": "quorum", "node": "node1", "quorate": 1, "status": "OK"},
    {
        "id": "master",
        "type": "master",
        "node": "node1",
        "status": "node1 (active, Mon Oct 19 10:00:00 2026)",
        "timestamp": 1792404000,
    },
    {
        "id": "fencing",
        "type": "fencing",
        "node": "",
        "armed-state": "armed",
        "resource_mode": "freeze",
        "status": "armed",
    },
    {
        "id": "lrm:node1",
        "type": "lrm",
        "node": "node1",
        "status": "active",
        "timestamp": 1792404000,
    },
    {
        "id": "lrm:node2",
        "type": "lrm",
        "node": "node2",
        "status": "maintenance mode",
        "timestamp": 1792404000,
    },
    {
        "id": "service:vm:100",
        "type": "service",
        "sid": "vm:100",
        "node": "node1",
        "crm_state": "started",
        "state": "started",
        "request_state": "started",
        "status": "vm:100 (node1, started)",
    },
]

MOCK_HA_MANAGER_STATUS_DATA = {
    "manager_status": {
        "master_node": "node1",
        "node_status": {"node1": "online", "node2": "maintenance"},
        "service_status": {},
        "timestamp": 1792404000,
    },
    "lrm_status": {
        "node1": {"mode": "active", "state": "active", "timestamp": 1792404000},
        "node2": {
            "mode": "maintenance",
            "state": "wait_for_agent_lock",
            "timestamp": 1792404000,
        },
    },
    "quorum": {"node": "node1", "quorate": "1"},
}
