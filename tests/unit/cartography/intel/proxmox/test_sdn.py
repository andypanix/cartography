"""
Unit tests for Proxmox SDN transforms.
"""

from unittest.mock import MagicMock

from proxmoxer.core import ResourceException

from cartography.intel.proxmox import sdn
from cartography.intel.proxmox.firewall import transform_firewall_rule_data
from tests.data.proxmox import sdn as data

C = "prod"


def test_transform_zones_builds_scoped_relationship_targets():
    # Act
    zones = {z["name"]: z for z in sdn.transform_zones(data.MOCK_ZONES, C)}

    # Assert
    evpn = zones["evpn1"]
    assert evpn["id"] == "prod/evpn1"
    assert evpn["controller_ids"] == ["prod/evpnctl"]
    assert evpn["ipam_id"] == "prod/pve"
    # Forward and reverse DNS use the same plugin: one relationship.
    assert evpn["dns_ids"] == ["prod/pdns"]
    assert evpn["advertise_subnets"] is True
    assert evpn["rt_import"] == ["65000:100", "65000:200"]
    vlan = zones["vlan1"]
    assert vlan["nodes"] == ["pve1", "pve2"]
    assert vlan["controller_ids"] == []
    assert vlan["fabric_id"] is None


def test_transform_zones_includes_secondary_controllers():
    # Act
    zones = sdn.transform_zones(
        [
            {
                "zone": "z",
                "type": "evpn",
                "controller": "a",
                "secondary-controllers": ["b", "c"],
            },
        ],
        C,
    )

    # Assert
    assert zones[0]["controller_ids"] == ["prod/a", "prod/b", "prod/c"]


def test_subnet_cidr_prefers_api_field_then_derives_from_id():
    # Act and assert
    assert sdn.subnet_cidr({"subnet": "z-10.0.0.0-24", "cidr": "10.0.0.0/24"}, "z") == (
        "10.0.0.0/24"
    )
    assert sdn.subnet_cidr({"subnet": "z-10.0.0.0-24"}, "z") == "10.0.0.0/24"
    # IPv6 networks keep their colons; only the last dash separates the prefix.
    assert sdn.subnet_cidr({"subnet": "my-zone-fd00::-64"}, "my-zone") == "fd00::/64"
    assert sdn.subnet_cidr({"subnet": "unexpected"}, "z") is None


def test_transform_vnets_merges_firewall_options():
    # Act
    vnets = {
        v["name"]: v
        for v in sdn.transform_vnets(
            data.MOCK_VNETS,
            data.MOCK_VNET_FIREWALL_OPTIONS,
            C,
        )
    }

    # Assert
    assert vnets["vnet1"]["zone_id"] == "prod/evpn1"
    assert vnets["vnet1"]["firewall_enable"] is True
    assert vnets["vnet1"]["firewall_policy_forward"] == "DROP"
    assert vnets["vlan10"]["firewall_enable"] is None
    assert vnets["vlan10"]["vlanaware"] is False


def test_transform_subnets_formats_dhcp_ranges():
    # Act
    subnets = sdn.transform_subnets(
        data.MOCK_SUBNETS,
        {"vnet1": "evpn1", "vlan10": "vlan1"},
        C,
    )

    # Assert
    by_id = {s["id"]: s for s in subnets}
    assert by_id["prod/evpn1-10.10.0.0-24"]["dhcp_ranges"] == [
        "10.10.0.100-10.10.0.200",
    ]
    assert by_id["prod/evpn1-10.10.0.0-24"]["snat"] is True
    assert by_id["prod/vlan1-192.168.10.0-24"]["zone"] == "vlan1"
    assert by_id["prod/vlan1-192.168.10.0-24"]["vnet_id"] == "prod/vlan10"


def test_transform_controllers_links_nodes_fabric_and_route_maps():
    # Act
    controllers = {
        c["name"]: c for c in sdn.transform_controllers(data.MOCK_CONTROLLERS, C)
    }

    # Assert
    assert controllers["evpnctl"]["fabric_id"] == "prod/fab1"
    assert controllers["evpnctl"]["route_map_ids"] == ["prod/bgp-out"]
    assert controllers["evpnctl"]["node_ids"] == []
    assert controllers["bgp-pve1"]["node_ids"] == ["prod/pve1"]
    assert controllers["bgp-pve1"]["peers"] == ["192.0.2.254"]


def test_transform_plugins_never_keep_credentials():
    # Arrange
    ipams = [{"ipam": "nb", "type": "netbox", "url": "u", "token": "secret"}]
    dns = [{"dns": "pdns", "type": "powerdns", "url": "u", "key": "secret"}]

    # Act
    transformed = sdn.transform_ipams(ipams, C) + sdn.transform_dns(dns, C)

    # Assert
    assert all("secret" not in item.values() for item in transformed)


def test_transform_ipam_entries_skips_entries_without_ip():
    # Act
    entries = sdn.transform_ipam_entries(
        {"pve": [*data.MOCK_IPAM_STATUS["pve"], {"zone": "evpn1"}]},
        C,
    )

    # Assert
    assert {e["id"] for e in entries} == {
        "prod/pve:evpn1:10.10.0.0/24:10.10.0.1",
        "prod/pve:evpn1:10.10.0.0/24:10.10.0.100",
    }
    assert {e["ip"]: e["vmid"] for e in entries} == {
        "10.10.0.1": None,
        "10.10.0.100": 100,
    }


def test_transform_prefix_lists_orders_entries_by_sequence():
    # Act
    prefix_lists = sdn.transform_prefix_lists(
        [
            *data.MOCK_PREFIX_LISTS,
            {
                "id": "parsed",
                "entries": [{"action": "permit", "prefix": "0.0.0.0/0", "seq": 5}],
            },
        ],
        C,
    )

    # Assert
    assert {p["id"]: p["entries"] for p in prefix_lists} == {
        "prod/internal": [
            "seq 10 permit 10.0.0.0/8 ge 16 le 24",
            "seq 20 deny 10.0.0.0/8 le 32",
        ],
        "prod/parsed": ["seq 5 permit 0.0.0.0/0"],
    }


def test_transform_route_maps_adds_maps_known_only_from_entries():
    # Arrange
    entries = [
        *data.MOCK_ROUTE_MAP_ENTRIES,
        {
            "route-map-id": "other",
            "order": 1,
            "action": "permit",
            "call": "bgp-out",
            "exit-action": "key=on-match-goto,value=20",
            "match": [{"key": "ip6-next-hop-prefix-list", "value": "v6"}],
        },
    ]

    # Act
    route_maps, transformed = sdn.transform_route_maps(
        data.MOCK_ROUTE_MAPS,
        entries,
        C,
    )

    # Assert
    assert [m["id"] for m in route_maps] == ["prod/bgp-out", "prod/other"]
    by_id = {e["id"]: e for e in transformed}
    assert by_id["prod/bgp-out:10"]["prefix_list_ids"] == ["prod/internal"]
    assert by_id["prod/other:1"]["call_id"] == "prod/bgp-out"
    assert by_id["prod/other:1"]["exit_action"] == "on-match-goto 20"
    assert by_id["prod/other:1"]["prefix_list_ids"] == ["prod/v6"]


def test_transform_fabrics_records_redistribution_route_maps():
    # Act
    fabrics = sdn.transform_fabrics(
        [
            {
                "id": "ospf1",
                "protocol": "ospf",
                "area": "0",
                "redistribute": ["source=connected", "source=bgp,route-map=bgp-out"],
            },
        ],
        C,
    )

    # Assert
    assert fabrics[0]["redistribute"] == ["connected", "bgp:bgp-out"]
    assert fabrics[0]["route_map_ids"] == ["prod/bgp-out"]
    assert fabrics[0]["route_filter_id"] is None


def test_transform_fabric_nodes_does_not_link_external_peers_to_nodes():
    # Act
    nodes = sdn.transform_fabric_nodes(
        [
            *data.MOCK_FABRICS["nodes"],
            {
                "fabric_id": "wg1",
                "node_id": "office",
                "protocol": "wireguard",
                "role": "external",
                "endpoint": "203.0.113.1:51820",
                "allowed_ips": ["198.51.100.0/24"],
            },
        ],
        C,
    )

    # Assert
    by_id = {n["id"]: n for n in nodes}
    assert by_id["prod/fab1:pve1"]["proxmox_node_id"] == "prod/pve1"
    assert by_id["prod/fab1:pve1"]["interfaces"] == ["ens19"]
    assert by_id["prod/fab1:pve2"]["interfaces"] == ["ens19"]
    assert by_id["prod/wg1:office"]["proxmox_node_id"] is None
    assert by_id["prod/wg1:office"]["allowed_ips"] == ["198.51.100.0/24"]


def test_resolve_fabric_neighbors_by_name_and_address():
    # Arrange
    index = sdn.fabric_peer_index(data.MOCK_FABRICS["nodes"], C)["fab1"]

    # Act
    links = sdn.resolve_fabric_neighbors(
        "prod/fab1:pve2",
        [
            {"neighbor": "198.51.100.1", "status": "Up"},
            {"neighbor": "pve1", "status": "Up"},
            {"neighbor": "203.0.113.9", "status": "Up"},
            {"neighbor": "192.0.2.2", "status": "Up"},
        ],
        index,
    )

    # Assert - unknown peers and the node itself are not linked
    assert [link["neighbor_id"] for link in links] == [
        "prod/fab1:pve1",
        "prod/fab1:pve1",
    ]


def test_transform_bridges_links_guest_ports_by_vmid_and_net_id():
    # Act
    bridges, ports = sdn.transform_bridges(
        data.MOCK_NODE_ZONE_BRIDGES[("pve1", "evpn1")],
        "pve1",
        "evpn1",
        C,
    )

    # Assert
    assert bridges[0]["id"] == "prod/pve1:vnet1"
    assert bridges[0]["vnet_id"] == "prod/vnet1"
    assert bridges[0]["vlan_filtering"] is False
    assert {(p["name"], p["vmid"], p["net_id"]) for p in ports} == {
        ("tap100i0", 100, "net0"),
        ("vxlan_vnet1", None, None),
    }


def test_transform_fabric_interfaces_merges_config_and_state():
    # Act
    links = sdn.transform_fabric_interfaces(
        data.MOCK_FABRICS["nodes"][0],
        "prod/fab1:pve1",
        [
            {"name": "ens19", "state": "up", "type": "Point-To-Point"},
            {"name": "dummy_fab1", "state": "up", "type": "Loopback"},
        ],
        C,
    )

    # Assert
    assert {(link["interface_id"], link["ip"], link["state"]) for link in links} == {
        ("prod/pve1:ens19", "198.51.100.1/31", "up"),
        ("prod/pve1:dummy_fab1", None, "up"),
    }


def test_format_routing_tables():
    # Act and assert
    assert sdn.format_ip_vrf(data.MOCK_NODE_ZONE_IP_VRF[("pve1", "evpn1")]) == [
        "0.0.0.0/0 via 192.0.2.254 proto bgp metric 20",
    ]
    assert sdn.format_mac_vrf(data.MOCK_NODE_VNET_MAC_VRF[("pve1", "vnet1")]) == [
        "BC:24:11:AA:BB:CC 10.10.0.100 via 192.0.2.1",
    ]
    assert sdn.format_fabric_routes(
        [{"route": "10.0.0.0/24", "via": ["192.0.2.1", "192.0.2.2"]}],
    ) == ["10.0.0.0/24 via 192.0.2.1,192.0.2.2"]


def test_vnet_firewall_rules_target_the_vnet():
    # Act
    rules = transform_firewall_rule_data(
        data.MOCK_VNET_FIREWALL_RULES["vnet1"],
        C,
        "vnet",
        "vnet1",
    )

    # Assert
    assert rules[0]["id"] == "prod/vnet:vnet1:0"
    assert rules[0]["target_vnet_id"] == "prod/vnet1"
    assert rules[0]["target_node_id"] is None
    assert rules[0]["target_vmid"] is None


def test_getters_read_the_running_configuration():
    # Arrange
    client = MagicMock()

    # Act
    sdn.get_zones(client)
    sdn.get_vnets(client)
    sdn.get_controllers(client)
    sdn.get_fabrics(client)

    # Assert
    client.cluster.sdn.zones.get.assert_called_once_with(running=1)
    client.cluster.sdn.vnets.get.assert_called_once_with(running=1)
    client.cluster.sdn.controllers.get.assert_called_once_with(running=1)
    client.cluster.sdn.fabrics.all.get.assert_called_once_with(running=1)


def test_version_9_getters_return_empty_on_proxmox_8():
    # Arrange
    client = MagicMock()
    client.cluster.sdn.fabrics.all.get.side_effect = ResourceException(
        501,
        "Not Implemented",
        "Method 'GET /cluster/sdn/fabrics/all' not implemented",
    )
    client.nodes.return_value.sdn.zones.return_value.bridges.get.side_effect = (
        ResourceException(501, "Not Implemented", "not implemented")
    )

    # Act and assert
    assert sdn.get_fabrics(client) == {}
    assert sdn.get_node_zone_bridges(client, "pve1", "zone1") == []
