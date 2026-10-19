"""
Tests for Proxmox HA module.
"""

from unittest.mock import MagicMock
from unittest.mock import patch

import pytest
from proxmoxer.core import ResourceException

import cartography.intel.proxmox.ha
from cartography.intel.proxmox.ha import is_ha_groups_migrated_error
from cartography.intel.proxmox.ha import transform_ha_resource_data
from cartography.intel.proxmox.ha import transform_ha_rule_data
from cartography.intel.proxmox.ha import transform_ha_status_data
from tests.data.proxmox.ha import MOCK_HA_MANAGER_STATUS_DATA
from tests.data.proxmox.ha import MOCK_HA_RESOURCE_DATA_PVE9
from tests.data.proxmox.ha import MOCK_HA_RULE_DATA
from tests.data.proxmox.ha import MOCK_HA_STATUS_DATA

MIGRATED_ERROR = ResourceException(
    500,
    "Internal Server Error",
    "cannot index groups: ha groups have been migrated to rules",
)


def test_transform_ha_resource_data_parses_guest_vmid():
    """Guest service IDs yield the numeric VM ID used to match the protected guest."""
    resources = [
        {"sid": "vm:100", "state": "started"},
        {"sid": "ct:200", "state": "started"},
        {"sid": "vm:abc", "state": "started"},
        {"sid": "other:1", "state": "started"},
    ]

    result = transform_ha_resource_data(resources, "test-cluster")

    assert [(r["id"], r["vmid"]) for r in result] == [
        ("test-cluster/vm:100", 100),
        ("test-cluster/ct:200", 200),
        ("test-cluster/vm:abc", None),
        ("test-cluster/other:1", None),
    ]


def test_transform_ha_resource_data_reads_pve9_fields():
    """failback and auto-rebalance become booleans, and stay None when unset."""
    result = transform_ha_resource_data(MOCK_HA_RESOURCE_DATA_PVE9, "test-cluster")

    assert [
        (r["sid"], r["type"], r["failback"], r["auto_rebalance"], r["group_id"])
        for r in result
    ] == [
        ("vm:100", "vm", True, None, None),
        ("ct:200", "ct", False, False, None),
        ("vm:101", "vm", None, None, None),
    ]


def test_transform_ha_rule_data():
    """Rules list the cluster-prefixed IDs of their resources and nodes."""
    result = transform_ha_rule_data(MOCK_HA_RULE_DATA, "test-cluster")

    assert result[0] == {
        "id": "test-cluster/ha-group-1",
        "rule": "ha-group-1",
        "cluster_id": "test-cluster",
        "type": "node-affinity",
        "resources": ["vm:100", "ct:200"],
        "nodes": "node1:2,node2",
        "affinity": "positive",
        "strict": False,
        "disable": False,
        "comment": "Migrated from HA group ha-group-1",
        "resource_ids": ["test-cluster/vm:100", "test-cluster/ct:200"],
        "node_ids": ["test-cluster/node1", "test-cluster/node2"],
    }
    assert result[1]["affinity"] == "negative"
    assert result[1]["strict"] is None
    assert result[1]["disable"] is True
    assert result[1]["nodes"] is None
    assert result[1]["node_ids"] == []
    assert result[1]["resource_ids"] == ["test-cluster/vm:100", "test-cluster/vm:101"]


def test_transform_ha_rule_data_accepts_decoded_lists():
    """Resources and nodes given as dicts keyed by item produce the same result."""
    rules = [
        {
            "rule": "r1",
            "type": "node-affinity",
            "resources": {"vm:100": 1},
            "nodes": {"node1": {"priority": 2}, "node2": {}},
        },
    ]

    result = transform_ha_rule_data(rules, "c")

    assert result[0]["nodes"] == "node1:2,node2"
    assert result[0]["node_ids"] == ["c/node1", "c/node2"]
    assert result[0]["resource_ids"] == ["c/vm:100"]


def test_transform_ha_status_data():
    """The status entries yield one HA manager and one LRM per node."""
    managers, lrms = transform_ha_status_data(
        MOCK_HA_STATUS_DATA,
        MOCK_HA_MANAGER_STATUS_DATA,
        "test-cluster",
    )

    assert managers == [
        {
            "id": "test-cluster/ha-manager",
            "cluster_id": "test-cluster",
            "quorate": True,
            "master_node": "node1",
            "master_node_id": "test-cluster/node1",
            "master_status": "node1 (active, Mon Oct 19 10:00:00 2026)",
            "armed_state": "armed",
            "resource_mode": "freeze",
        },
    ]
    assert [
        (lrm["id"], lrm["node_id"], lrm["status"], lrm["state"], lrm["mode"])
        for lrm in lrms
    ] == [
        ("test-cluster/lrm:node1", "test-cluster/node1", "active", "active", "active"),
        (
            "test-cluster/lrm:node2",
            "test-cluster/node2",
            "maintenance mode",
            "wait_for_agent_lock",
            "maintenance",
        ),
    ]
    assert [lrm["crm_node_state"] for lrm in lrms] == ["online", "maintenance"]


def test_transform_ha_status_data_pve84():
    """Proxmox VE 8.4 has no fencing entry; an idle HA stack has no master."""
    status = [
        {"id": "quorum", "type": "quorum", "node": "pve", "quorate": 1},
        {"id": "lrm:pve", "type": "lrm", "node": "pve", "status": "idle"},
    ]

    managers, lrms = transform_ha_status_data(status, {}, "c")

    assert managers[0]["master_node"] is None
    assert managers[0]["master_node_id"] is None
    assert managers[0]["armed_state"] is None
    assert lrms[0]["state"] is None
    assert transform_ha_status_data([], {}, "c") == ([], [])


def test_is_ha_groups_migrated_error():
    """Only the HTTP 500 for migrated groups counts as the migration error."""
    assert is_ha_groups_migrated_error(MIGRATED_ERROR)
    assert not is_ha_groups_migrated_error(
        ResourceException(500, "Internal Server Error", "boom"),
    )
    assert not is_ha_groups_migrated_error(
        ResourceException(403, "Permission check failed", ""),
    )


def test_get_ha_rules_returns_empty_list_on_pve84():
    """Proxmox VE 8.4 answers 501 for the HA rules endpoint."""
    client = MagicMock()
    client.cluster.ha.rules.get.side_effect = ResourceException(
        501,
        "Method 'GET /cluster/ha/rules' not implemented",
        "",
    )

    assert cartography.intel.proxmox.ha.get_ha_rules(client) == []


@patch.object(cartography.intel.proxmox.ha, "load_ha_status")
@patch.object(cartography.intel.proxmox.ha, "load_ha_rules")
@patch.object(cartography.intel.proxmox.ha, "get_ha_manager_status", return_value={})
@patch.object(cartography.intel.proxmox.ha, "get_ha_status", return_value=[])
@patch.object(cartography.intel.proxmox.ha, "get_ha_rules", return_value=[])
@patch.object(cartography.intel.proxmox.ha, "get_ha_resources", return_value=[])
@patch.object(cartography.intel.proxmox.ha, "get_ha_groups")
def test_sync_propagates_other_ha_group_errors(mock_get_groups, *_mocks):
    """A HA groups error other than the migration stops the sync."""
    mock_get_groups.side_effect = ResourceException(500, "Internal Server Error", "")

    with pytest.raises(ResourceException):
        cartography.intel.proxmox.ha.sync(MagicMock(), None, "c", 1, {})


def test_transform_ha_status_data_ignores_fields_of_unexpected_type():
    """An odd field of the untyped manager status does not stop the HA sync."""
    status = [
        {"id": "quorum", "type": "quorum", "node": "pve", "quorate": ""},
        {"id": "lrm:pve", "type": "lrm", "node": "pve", "status": "active"},
    ]
    manager_status = {
        "manager_status": {"master_node": "pve", "node_status": "online"},
        "lrm_status": {"pve": "active"},
    }

    managers, lrms = transform_ha_status_data(status, manager_status, "c")

    assert managers[0]["quorate"] is None
    assert managers[0]["master_node"] == "pve"
    assert lrms[0]["state"] is None
    assert lrms[0]["crm_node_state"] is None
