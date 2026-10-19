"""
Integration tests for Proxmox SDN sync.
"""

from contextlib import ExitStack
from typing import Any
from unittest.mock import patch

import cartography.intel.proxmox.sdn as sdn
from tests.data.proxmox import sdn as data
from tests.integration.util import check_nodes
from tests.integration.util import check_rels

TEST_UPDATE_TAG = 123456789
TEST_CLUSTER_ID = "test-cluster"
C = TEST_CLUSTER_ID


def _getters(**overrides: Any) -> dict[str, Any]:
    """Mocked SDN getters as name -> side effect, with optional overrides."""
    getters: dict[str, Any] = {
        "get_zones": lambda client: data.MOCK_ZONES,
        "get_vnets": lambda client: data.MOCK_VNETS,
        "get_subnets": lambda client, vnet: data.MOCK_SUBNETS[vnet],
        "get_vnet_firewall_options": lambda client, vnet: data.MOCK_VNET_FIREWALL_OPTIONS[
            vnet
        ],
        "get_vnet_firewall_rules": lambda client, vnet: data.MOCK_VNET_FIREWALL_RULES[
            vnet
        ],
        "get_controllers": lambda client: data.MOCK_CONTROLLERS,
        "get_ipams": lambda client: data.MOCK_IPAMS,
        "get_ipam_status": lambda client, ipam: data.MOCK_IPAM_STATUS[ipam],
        "get_dns": lambda client: data.MOCK_DNS,
        "get_fabrics": lambda client: data.MOCK_FABRICS,
        "get_prefix_lists": lambda client: data.MOCK_PREFIX_LISTS,
        "get_route_maps": lambda client: data.MOCK_ROUTE_MAPS,
        "get_route_map_entries": lambda client: data.MOCK_ROUTE_MAP_ENTRIES,
        "get_nodes": lambda client: data.MOCK_NODES,
        "get_node_zones": lambda client, node: data.MOCK_NODE_ZONES.get(node, []),
        "get_node_zone_content": lambda client, node, zone: data.MOCK_NODE_ZONE_CONTENT.get(
            (node, zone), []
        ),
        "get_node_zone_bridges": lambda client, node, zone: data.MOCK_NODE_ZONE_BRIDGES.get(
            (node, zone), []
        ),
        "get_node_zone_ip_vrf": lambda client, node, zone: data.MOCK_NODE_ZONE_IP_VRF.get(
            (node, zone), []
        ),
        "get_node_vnet_mac_vrf": lambda client, node, vnet: data.MOCK_NODE_VNET_MAC_VRF.get(
            (node, vnet), []
        ),
        "get_node_fabric_interfaces": lambda client, node, fabric: data.MOCK_NODE_FABRIC_INTERFACES.get(
            (node, fabric), []
        ),
        "get_node_fabric_neighbors": lambda client, node, fabric: data.MOCK_NODE_FABRIC_NEIGHBORS.get(
            (node, fabric), []
        ),
        "get_node_fabric_routes": lambda client, node, fabric: data.MOCK_NODE_FABRIC_ROUTES.get(
            (node, fabric), []
        ),
    }
    getters.update(overrides)
    return getters


def _empty_getters() -> dict[str, Any]:
    """Getters of a cluster without SDN configured, on Proxmox VE 8.4."""
    return _getters(
        get_zones=lambda client: [],
        get_vnets=lambda client: [],
        get_controllers=lambda client: [],
        get_ipams=lambda client: [],
        get_dns=lambda client: [],
        get_fabrics=lambda client: {},
        get_prefix_lists=lambda client: [],
        get_route_maps=lambda client: [],
        get_route_map_entries=lambda client: [],
        get_node_zones=lambda client, node: [],
    )


def _seed(neo4j_session: Any, cluster_id: str) -> None:
    """Create the cluster, nodes, node interfaces, guest and guest interface."""
    neo4j_session.run(
        """
        MERGE (c:ProxmoxCluster {id: $cluster_id})
        SET c.lastupdated = $update_tag
        WITH c
        UNWIND ['pve1', 'pve2'] AS node_name
        MERGE (n:ProxmoxNode {id: $cluster_id + '/' + node_name})
        SET n.name = node_name, n.cluster_id = $cluster_id
        WITH n, node_name
        UNWIND ['vmbr0', 'ens19'] AS iface
        MERGE (i:ProxmoxNodeNetworkInterface {id: $cluster_id + '/' + node_name + ':' + iface})
        SET i.name = iface, i.node_name = node_name, i.cluster_id = $cluster_id
        """,
        cluster_id=cluster_id,
        update_tag=TEST_UPDATE_TAG,
    )
    neo4j_session.run(
        """
        MERGE (v:ProxmoxVM {id: $cluster_id + '/pve1/qemu/100'})
        SET v.vmid = 100, v.cluster_id = $cluster_id
        MERGE (i:ProxmoxNetworkInterface {id: $cluster_id + '/pve1/qemu/100:net0'})
        SET i.vmid = 100, i.net_id = 'net0', i.bridge = 'vnet1', i.cluster_id = $cluster_id
        MERGE (v)-[:HAS_NETWORK_INTERFACE]->(i)
        """,
        cluster_id=cluster_id,
    )


def _run_sync(
    neo4j_session: Any,
    getters: dict[str, Any],
    cluster_id: str = TEST_CLUSTER_ID,
    update_tag: int = TEST_UPDATE_TAG,
) -> None:
    common_job_parameters = {"UPDATE_TAG": update_tag, "CLUSTER_ID": cluster_id}
    with ExitStack() as stack:
        for name, side_effect in getters.items():
            stack.enter_context(patch.object(sdn, name, side_effect=side_effect))
        sdn.sync(neo4j_session, None, cluster_id, update_tag, common_job_parameters)
        sdn.cleanup(neo4j_session, common_job_parameters)


def _node_props(neo4j_session: Any, label: str, attrs: list[str]) -> set[tuple]:
    """Like check_nodes, with list properties returned as tuples."""
    result = neo4j_session.run(
        f"MATCH (n:{label}) RETURN " + ", ".join(f"n.{a} AS {a}" for a in attrs),
    )
    return {
        tuple(tuple(v) if isinstance(v, list) else v for v in row.values())
        for row in result
    }


def _reset(neo4j_session: Any) -> None:
    neo4j_session.run("MATCH (n) DETACH DELETE n")


def test_sync_sdn_configuration(neo4j_session):
    # Arrange
    _reset(neo4j_session)
    _seed(neo4j_session, C)

    # Act
    _run_sync(neo4j_session, _getters())

    # Assert - configuration nodes
    assert check_nodes(neo4j_session, "ProxmoxSDNZone", ["id", "type"]) == {
        (f"{C}/evpn1", "evpn"),
        (f"{C}/vlan1", "vlan"),
    }
    assert check_nodes(
        neo4j_session,
        "ProxmoxSDNVNet",
        ["id", "tag", "firewall_enable", "firewall_policy_forward"],
    ) == {
        (f"{C}/vnet1", 11000, True, "DROP"),
        (f"{C}/vlan10", 10, None, None),
    }
    assert check_nodes(neo4j_session, "ProxmoxSDNSubnet", ["id", "cidr"]) == {
        (f"{C}/evpn1-10.10.0.0-24", "10.10.0.0/24"),
        (f"{C}/vlan1-192.168.10.0-24", "192.168.10.0/24"),
    }
    assert check_nodes(neo4j_session, "ProxmoxSDNIPAM", ["id", "type"]) == {
        (f"{C}/pve", "pve"),
        (f"{C}/netbox", "netbox"),
    }
    assert check_nodes(neo4j_session, "ProxmoxSDNIPAMEntry", ["ip", "gateway"]) == {
        ("10.10.0.1", True),
        ("10.10.0.100", False),
    }
    assert _node_props(neo4j_session, "ProxmoxSDNPrefixList", ["id", "entries"]) == {
        (
            f"{C}/internal",
            (
                "seq 10 permit 10.0.0.0/8 ge 16 le 24",
                "seq 20 deny 10.0.0.0/8 le 32",
            ),
        ),
    }
    assert _node_props(
        neo4j_session, "ProxmoxSDNRouteMapEntry", ["id", "match", "set"]
    ) == {
        (
            f"{C}/bgp-out:10",
            ("ip-address-prefix-list=internal",),
            ("local-preference=50",),
        ),
        (f"{C}/bgp-out:20", (), ()),
    }

    # Assert - zone topology
    assert check_rels(
        neo4j_session, "ProxmoxSDNZone", "id", "ProxmoxSDNVNet", "id", "HAS_VNET"
    ) == {(f"{C}/evpn1", f"{C}/vnet1"), (f"{C}/vlan1", f"{C}/vlan10")}
    assert check_rels(
        neo4j_session, "ProxmoxSDNVNet", "id", "ProxmoxSDNSubnet", "id", "HAS_SUBNET"
    ) == {
        (f"{C}/vnet1", f"{C}/evpn1-10.10.0.0-24"),
        (f"{C}/vlan10", f"{C}/vlan1-192.168.10.0-24"),
    }
    assert check_rels(
        neo4j_session,
        "ProxmoxSDNZone",
        "id",
        "ProxmoxSDNController",
        "id",
        "USES_CONTROLLER",
    ) == {(f"{C}/evpn1", f"{C}/evpnctl")}
    assert check_rels(
        neo4j_session, "ProxmoxSDNZone", "id", "ProxmoxSDNIPAM", "id", "USES_IPAM"
    ) == {(f"{C}/evpn1", f"{C}/pve"), (f"{C}/vlan1", f"{C}/pve")}
    assert check_rels(
        neo4j_session, "ProxmoxSDNZone", "id", "ProxmoxSDNDNS", "id", "USES_DNS"
    ) == {(f"{C}/evpn1", f"{C}/pdns")}
    assert check_rels(
        neo4j_session,
        "ProxmoxSDNZone",
        "id",
        "ProxmoxNodeNetworkInterface",
        "id",
        "USES_BRIDGE",
    ) == {(f"{C}/vlan1", f"{C}/pve1:vmbr0"), (f"{C}/vlan1", f"{C}/pve2:vmbr0")}

    # Assert - guests, IPAM and firewall
    assert check_rels(
        neo4j_session,
        "ProxmoxNetworkInterface",
        "id",
        "ProxmoxSDNVNet",
        "id",
        "CONNECTED_TO",
    ) == {(f"{C}/pve1/qemu/100:net0", f"{C}/vnet1")}
    assert check_rels(
        neo4j_session,
        "ProxmoxSDNSubnet",
        "id",
        "ProxmoxSDNIPAMEntry",
        "ip",
        "HAS_IPAM_ENTRY",
    ) == {
        (f"{C}/evpn1-10.10.0.0-24", "10.10.0.1"),
        (f"{C}/evpn1-10.10.0.0-24", "10.10.0.100"),
    }
    assert check_rels(
        neo4j_session, "ProxmoxSDNIPAMEntry", "ip", "ProxmoxVM", "id", "ALLOCATED_TO"
    ) == {("10.10.0.100", f"{C}/pve1/qemu/100")}
    assert check_rels(
        neo4j_session,
        "ProxmoxFirewallRule",
        "id",
        "ProxmoxSDNVNet",
        "id",
        "APPLIES_TO_VNET",
    ) == {(f"{C}/vnet:vnet1:0", f"{C}/vnet1")}

    # Assert - routing policy and fabric
    assert check_rels(
        neo4j_session,
        "ProxmoxSDNController",
        "id",
        "ProxmoxSDNFabric",
        "id",
        "USES_FABRIC",
    ) == {(f"{C}/evpnctl", f"{C}/fab1")}
    assert check_rels(
        neo4j_session,
        "ProxmoxSDNController",
        "id",
        "ProxmoxSDNRouteMap",
        "id",
        "USES_ROUTE_MAP",
    ) == {(f"{C}/evpnctl", f"{C}/bgp-out")}
    assert check_rels(
        neo4j_session, "ProxmoxSDNController", "id", "ProxmoxNode", "id", "RUNS_ON"
    ) == {(f"{C}/bgp-pve1", f"{C}/pve1")}
    assert check_rels(
        neo4j_session,
        "ProxmoxSDNRouteMapEntry",
        "id",
        "ProxmoxSDNPrefixList",
        "id",
        "MATCHES_PREFIX_LIST",
    ) == {(f"{C}/bgp-out:10", f"{C}/internal")}
    assert check_rels(
        neo4j_session,
        "ProxmoxSDNFabric",
        "id",
        "ProxmoxSDNPrefixList",
        "id",
        "USES_PREFIX_LIST",
    ) == {(f"{C}/fab1", f"{C}/internal")}
    assert check_rels(
        neo4j_session,
        "ProxmoxSDNFabric",
        "id",
        "ProxmoxSDNFabricNode",
        "id",
        "HAS_NODE",
    ) == {(f"{C}/fab1", f"{C}/fab1:pve1"), (f"{C}/fab1", f"{C}/fab1:pve2")}
    assert check_rels(
        neo4j_session, "ProxmoxSDNFabricNode", "id", "ProxmoxNode", "id", "RUNS_ON"
    ) == {(f"{C}/fab1:pve1", f"{C}/pve1"), (f"{C}/fab1:pve2", f"{C}/pve2")}

    # Assert - every SDN node belongs to the cluster
    result = neo4j_session.run(
        """
        MATCH (n) WHERE any(l IN labels(n) WHERE l STARTS WITH 'ProxmoxSDN')
        OPTIONAL MATCH (c:ProxmoxCluster {id: $cluster_id})-[:RESOURCE]->(n)
        RETURN count(n) AS total, count(c) AS owned
        """,
        cluster_id=C,
    ).single()
    assert result["total"] == result["owned"]


def test_sync_sdn_node_state(neo4j_session):
    # Arrange
    _reset(neo4j_session)
    _seed(neo4j_session, C)

    # Act
    _run_sync(neo4j_session, _getters())

    # Assert - zone and VNet status per node, with the VRF tables
    zone_links = neo4j_session.run(
        """
        MATCH (z:ProxmoxSDNZone)-[r:DEPLOYED_ON]->(n:ProxmoxNode)
        RETURN z.id AS zone, n.id AS node, r.status AS status, r.ip_vrf AS ip_vrf
        """,
    ).data()
    assert {
        (r["zone"], r["node"], r["status"], tuple(r["ip_vrf"])) for r in zone_links
    } == {
        (
            f"{C}/evpn1",
            f"{C}/pve1",
            "available",
            ("0.0.0.0/0 via 192.0.2.254 proto bgp metric 20",),
        ),
        (f"{C}/vlan1", f"{C}/pve1", "available", ()),
        (f"{C}/vlan1", f"{C}/pve2", "error", ()),
    }
    vnet_links = neo4j_session.run(
        """
        MATCH (v:ProxmoxSDNVNet)-[r:DEPLOYED_ON]->(n:ProxmoxNode)
        RETURN v.id AS vnet, n.id AS node, r.statusmsg AS msg, r.mac_vrf AS mac_vrf
        """,
    ).data()
    assert {
        (r["vnet"], r["node"], r["msg"], tuple(r["mac_vrf"])) for r in vnet_links
    } == {
        (
            f"{C}/vnet1",
            f"{C}/pve1",
            None,
            ("BC:24:11:AA:BB:CC 10.10.0.100 via 192.0.2.1",),
        ),
        (f"{C}/vlan10", f"{C}/pve1", None, ()),
        (f"{C}/vlan10", f"{C}/pve2", "missing bridge", ()),
    }

    # Assert - bridge and ports on the node
    assert check_rels(
        neo4j_session, "ProxmoxNode", "id", "ProxmoxSDNBridge", "id", "HAS_SDN_BRIDGE"
    ) == {(f"{C}/pve1", f"{C}/pve1:vnet1")}
    assert check_rels(
        neo4j_session, "ProxmoxSDNBridge", "id", "ProxmoxSDNVNet", "id", "IMPLEMENTS"
    ) == {(f"{C}/pve1:vnet1", f"{C}/vnet1")}
    assert check_rels(
        neo4j_session,
        "ProxmoxSDNBridge",
        "id",
        "ProxmoxSDNBridgePort",
        "id",
        "HAS_PORT",
    ) == {
        (f"{C}/pve1:vnet1", f"{C}/pve1:vnet1:tap100i0"),
        (f"{C}/pve1:vnet1", f"{C}/pve1:vnet1:vxlan_vnet1"),
    }
    assert check_rels(
        neo4j_session,
        "ProxmoxNetworkInterface",
        "id",
        "ProxmoxSDNBridgePort",
        "id",
        "PLUGGED_INTO",
    ) == {(f"{C}/pve1/qemu/100:net0", f"{C}/pve1:vnet1:tap100i0")}

    # Assert - fabric neighbors, resolved by hostname and by interface address
    neighbors = neo4j_session.run(
        """
        MATCH (a:ProxmoxSDNFabricNode)-[r:FABRIC_NEIGHBOR]->(b:ProxmoxSDNFabricNode)
        RETURN a.id AS a, b.id AS b, r.status AS status
        """,
    ).data()
    assert {(r["a"], r["b"], r["status"]) for r in neighbors} == {
        (f"{C}/fab1:pve1", f"{C}/fab1:pve2", "Up"),
        (f"{C}/fab1:pve2", f"{C}/fab1:pve1", "Up"),
    }
    assert _node_props(
        neo4j_session, "ProxmoxSDNFabricNode", ["id", "neighbors", "routes"]
    ) == {
        (f"{C}/fab1:pve1", ("pve2",), ("192.0.2.2/32 via 198.51.100.2",)),
        (
            f"{C}/fab1:pve2",
            ("198.51.100.1", "203.0.113.9"),
            ("192.0.2.1/32 via 198.51.100.1",),
        ),
    }
    interfaces = neo4j_session.run(
        """
        MATCH (f:ProxmoxSDNFabricNode)-[r:USES_INTERFACE]->(i:ProxmoxNodeNetworkInterface)
        RETURN f.id AS f, i.id AS i, r.ip AS ip, r.state AS state
        """,
    ).data()
    assert {(r["f"], r["i"], r["ip"], r["state"]) for r in interfaces} == {
        (f"{C}/fab1:pve1", f"{C}/pve1:ens19", "198.51.100.1/31", "up"),
        (f"{C}/fab1:pve2", f"{C}/pve2:ens19", "198.51.100.2/31", "up"),
    }


def test_sync_sdn_not_configured(neo4j_session):
    # Arrange
    _reset(neo4j_session)
    _seed(neo4j_session, C)

    # Act
    _run_sync(neo4j_session, _empty_getters())

    # Assert
    result = neo4j_session.run(
        """
        MATCH (n) WHERE any(l IN labels(n) WHERE l STARTS WITH 'ProxmoxSDN')
        RETURN count(n) AS total
        """,
    ).single()
    assert result["total"] == 0


def test_sync_sdn_removes_stale_data(neo4j_session):
    # Arrange
    _reset(neo4j_session)
    _seed(neo4j_session, C)

    # Act
    _run_sync(neo4j_session, _getters())

    # Assert
    assert len(check_nodes(neo4j_session, "ProxmoxSDNZone", ["id"])) == 2

    # Act - SDN removed from the cluster
    _run_sync(neo4j_session, _empty_getters(), update_tag=TEST_UPDATE_TAG + 1)

    # Assert
    result = neo4j_session.run(
        """
        MATCH (n) WHERE any(l IN labels(n) WHERE l STARTS WITH 'ProxmoxSDN')
        RETURN count(n) AS total
        """,
    ).single()
    assert result["total"] == 0
    assert (
        neo4j_session.run(
            "MATCH (:ProxmoxNode)<-[r:DEPLOYED_ON]-() RETURN count(r) AS c",
        ).single()["c"]
        == 0
    )


def test_sync_sdn_keeps_clusters_apart(neo4j_session):
    # Arrange
    _reset(neo4j_session)
    for cluster_id in ("cluster-a", "cluster-b"):
        _seed(neo4j_session, cluster_id)

    # Act
    for cluster_id in ("cluster-a", "cluster-b"):
        _run_sync(neo4j_session, _getters(), cluster_id=cluster_id)

    # Assert - same names, separate nodes, each linked only inside its cluster
    assert check_nodes(neo4j_session, "ProxmoxSDNVNet", ["id"]) == {
        ("cluster-a/vnet1",),
        ("cluster-a/vlan10",),
        ("cluster-b/vnet1",),
        ("cluster-b/vlan10",),
    }
    assert check_rels(
        neo4j_session,
        "ProxmoxNetworkInterface",
        "id",
        "ProxmoxSDNVNet",
        "id",
        "CONNECTED_TO",
    ) == {
        ("cluster-a/pve1/qemu/100:net0", "cluster-a/vnet1"),
        ("cluster-b/pve1/qemu/100:net0", "cluster-b/vnet1"),
    }
    cross = neo4j_session.run(
        """
        MATCH (a)-[r]-(b)
        WHERE a.cluster_id IS NOT NULL AND b.cluster_id IS NOT NULL
          AND a.cluster_id <> b.cluster_id
        RETURN count(r) AS c
        """,
    ).single()
    assert cross["c"] == 0

    # Act - cluster-b loses its SDN configuration
    _run_sync(
        neo4j_session,
        _empty_getters(),
        cluster_id="cluster-b",
        update_tag=TEST_UPDATE_TAG + 1,
    )

    # Assert - cluster-a keeps its SDN nodes
    assert check_nodes(neo4j_session, "ProxmoxSDNVNet", ["id"]) == {
        ("cluster-a/vnet1",),
        ("cluster-a/vlan10",),
    }
