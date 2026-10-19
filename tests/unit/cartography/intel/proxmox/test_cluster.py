"""
Tests for Proxmox cluster module.
"""

from unittest.mock import MagicMock

from cartography.intel.proxmox.cluster import get_corosync_nodes
from cartography.intel.proxmox.cluster import get_corosync_totem
from cartography.intel.proxmox.cluster import get_qdevice_status
from cartography.intel.proxmox.cluster import transform_cluster_data
from cartography.intel.proxmox.cluster import transform_corosync_nodes
from cartography.intel.proxmox.cluster import transform_corosync_totem
from cartography.intel.proxmox.cluster import transform_node_data
from cartography.intel.proxmox.cluster import transform_qdevice_status
from tests.data.proxmox.cluster import MOCK_COROSYNC_NODES
from tests.data.proxmox.cluster import MOCK_COROSYNC_TOTEM
from tests.data.proxmox.cluster import MOCK_QDEVICE_STATUS


def test_transform_cluster_data_with_cluster_info():
    """Test cluster data transformation with cluster information present."""
    raw_status = [
        {
            "type": "cluster",
            "name": "test-cluster",
            "version": "8.1",
            "quorate": 1,
        },
        {
            "type": "node",
            "name": "node1",
            "online": 1,
        },
        {
            "type": "node",
            "name": "node2",
            "online": 1,
        },
    ]

    result = transform_cluster_data(raw_status, "proxmox.example.com")

    assert result["id"] == "test-cluster"
    assert result["name"] == "test-cluster"
    assert result["version"] == "8.1"
    assert result["quorate"] is True
    assert result["nodes_online"] == 2


def test_transform_cluster_data_without_cluster_info():
    """Test cluster data transformation without cluster information (synthetic cluster)."""
    raw_status = [
        {
            "type": "node",
            "name": "node1",
            "online": 1,
        },
    ]

    result = transform_cluster_data(raw_status, "proxmox.example.com")

    assert result["id"] == "proxmox-example-com"
    assert result["name"] == "proxmox-example-com"
    assert result["version"] == "unknown"
    assert result["quorate"] is True
    assert result["nodes_online"] == 1


def test_transform_node_data():
    """Test node data transformation."""
    raw_nodes = [
        {
            "node": "node1",
            "ip": "192.168.1.10",
            "status": "online",
            "uptime": 86400,
            "maxcpu": 8,
            "cpu": 0.25,
            "maxmem": 34359738368,
            "mem": 8589934592,
            "maxdisk": 1099511627776,
            "disk": 274877906944,
            "level": "",
        },
        {
            "node": "node2",
            "ip": "192.168.1.11",
            "status": "online",
        },
    ]

    cluster_id = "test-cluster"

    result = transform_node_data(raw_nodes, cluster_id)

    assert len(result) == 2
    assert result[0]["id"] == "test-cluster/node1"
    assert result[0]["cluster_id"] == "test-cluster"
    assert result[0]["cpu_count"] == 8
    assert result[0]["memory_total"] == 34359738368
    assert result[0]["ip"] == "192.168.1.10"

    # Test default values for second node
    assert result[1]["id"] == "test-cluster/node2"
    assert result[1]["cpu_count"] == 0
    assert result[1]["memory_total"] == 0
    assert result[1]["status"] == "online"


def test_transform_corosync_totem():
    """Totem values arrive as strings; numbers become ints and links a sorted list."""
    result = transform_corosync_totem(MOCK_COROSYNC_TOTEM)

    assert result == {
        "totem_cluster_name": "test-cluster",
        "totem_config_version": 3,
        "totem_ip_version": "ipv4-6",
        "totem_link_mode": "passive",
        "totem_link_numbers": [0, 1],
        "totem_secauth": "on",
        "totem_version": 2,
    }


def test_transform_corosync_totem_without_interface():
    """A totem section without interface sections has no link numbers."""
    result = transform_corosync_totem({"cluster_name": "c", "config_version": "1"})

    assert result["totem_link_numbers"] is None
    assert result["totem_config_version"] == 1


def test_transform_corosync_totem_standalone_host():
    """A standalone host answers null for the totem section."""
    assert transform_corosync_totem(None) == {}
    assert transform_corosync_totem({}) == {}


def test_transform_qdevice_status():
    """QDevice status keys are the labels of corosync-qdevice-tool."""
    assert transform_qdevice_status(MOCK_QDEVICE_STATUS) == {
        "qdevice_state": "Connected",
        "qdevice_model": "Net",
        "qdevice_qnetd_host": "192.168.1.50:5403",
        "qdevice_algorithm": "Fifty-Fifty split",
        "qdevice_tie_breaker": "Node with lowest node ID",
    }
    assert transform_qdevice_status({}) == {}


def test_transform_corosync_nodes():
    """Ring addresses are ordered by link number, ids and votes become ints."""
    entries = MOCK_COROSYNC_NODES + [
        # Entry without a name: the API keys it by ring0_addr. Links can skip numbers.
        {
            "node": "10.0.0.3",
            "nodeid": "3",
            "quorum_votes": "2",
            "ring2_addr": "10.2.0.3",
            "ring0_addr": "10.0.0.3",
        },
    ]

    result = transform_corosync_nodes(entries)

    assert result["node1"] == {
        "corosync_node_id": 1,
        "corosync_quorum_votes": 1,
        "corosync_ring_addresses": ["192.168.1.10", "10.10.10.10"],
    }
    assert result["10.0.0.3"]["corosync_ring_addresses"] == ["10.0.0.3", "10.2.0.3"]
    assert result["10.0.0.3"]["corosync_quorum_votes"] == 2
    assert transform_corosync_nodes([]) == {}


def test_transform_node_data_with_corosync_membership():
    """Corosync fields are joined to /nodes entries by node name."""
    nodes = [{"node": "node1"}, {"node": "node3"}]

    result = transform_node_data(
        nodes, "test-cluster", transform_corosync_nodes(MOCK_COROSYNC_NODES)
    )

    assert result[0]["corosync_node_id"] == 1
    assert result[0]["corosync_ring_addresses"] == ["192.168.1.10", "10.10.10.10"]
    # node3 is not in the corosync node list
    assert result[1]["corosync_node_id"] is None
    assert result[1]["corosync_ring_addresses"] is None


def test_corosync_getters_read_config_subpaths():
    """The corosync getters read the totem, nodes and qdevice subpaths, not the index."""
    # Arrange
    client = MagicMock()

    # Act
    get_corosync_totem(client)
    get_corosync_nodes(client)
    get_qdevice_status(client)

    # Assert
    client.cluster.config.totem.get.assert_called_once_with()
    client.cluster.config.nodes.get.assert_called_once_with()
    client.cluster.config.qdevice.get.assert_called_once_with()
    client.cluster.config.get.assert_not_called()
