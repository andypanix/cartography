"""
Sync Proxmox VE Software-Defined Networking (SDN).

Reads the running SDN configuration, never the pending one: zones, VNets and
their subnets and firewall, controllers, IPAM and DNS plugins, and on Proxmox
VE 9 fabrics, prefix lists and route maps. Then reads what each online node
reports for it: zone and VNet status, and on Proxmox VE 9 the VNet bridges and
their ports, fabric interfaces, neighbors and routes, and the EVPN VRF tables.

A cluster without SDN configured answers with empty lists. Hosts without the
SDN package (libpve-network-perl) answer 404 or 501, handled like a missing
endpoint.

Follows Cartography's Get → Transform → Load pattern.
"""

import logging
from typing import Any

import neo4j
import requests
from proxmoxer.core import ResourceException

from cartography.client.core.tx import load
from cartography.client.core.tx import load_matchlinks
from cartography.client.core.tx import read_list_of_dicts_tx
from cartography.graph.job import GraphJob
from cartography.intel.proxmox.cluster import get_nodes
from cartography.intel.proxmox.firewall import FirewallReferences
from cartography.intel.proxmox.firewall import load_firewall_rules
from cartography.intel.proxmox.firewall import resolve_rule_references
from cartography.intel.proxmox.firewall import transform_firewall_rule_data
from cartography.intel.proxmox.util import cluster_scoped_id
from cartography.intel.proxmox.util import proxmox_api_retry
from cartography.intel.proxmox.util import proxmox_optional_endpoint
from cartography.models.proxmox.sdn import ProxmoxSDNBridgePortSchema
from cartography.models.proxmox.sdn import ProxmoxSDNBridgeSchema
from cartography.models.proxmox.sdn import ProxmoxSDNControllerSchema
from cartography.models.proxmox.sdn import ProxmoxSDNDNSSchema
from cartography.models.proxmox.sdn import ProxmoxSDNFabricInterfaceMatchLink
from cartography.models.proxmox.sdn import ProxmoxSDNFabricNeighborMatchLink
from cartography.models.proxmox.sdn import ProxmoxSDNFabricNodeSchema
from cartography.models.proxmox.sdn import ProxmoxSDNFabricSchema
from cartography.models.proxmox.sdn import ProxmoxSDNIPAMEntrySchema
from cartography.models.proxmox.sdn import ProxmoxSDNIPAMSchema
from cartography.models.proxmox.sdn import ProxmoxSDNPrefixListSchema
from cartography.models.proxmox.sdn import ProxmoxSDNRouteMapEntrySchema
from cartography.models.proxmox.sdn import ProxmoxSDNRouteMapSchema
from cartography.models.proxmox.sdn import ProxmoxSDNSubnetSchema
from cartography.models.proxmox.sdn import ProxmoxSDNVNetDeployedOnNodeMatchLink
from cartography.models.proxmox.sdn import ProxmoxSDNVNetSchema
from cartography.models.proxmox.sdn import ProxmoxSDNZoneDeployedOnNodeMatchLink
from cartography.models.proxmox.sdn import ProxmoxSDNZoneSchema
from cartography.util import timeit

logger = logging.getLogger(__name__)

# The built-in IPAM is the only plugin whose address database Proxmox VE
# exposes through /cluster/sdn/ipams/{ipam}/status.
PVE_IPAM_TYPE = "pve"
# Zones whose nodes keep a VRF routing table (ip-vrf, mac-vrf) in FRR.
EVPN_ZONE_TYPE = "evpn"
# WireGuard fabric node role of peers outside the cluster.
EXTERNAL_FABRIC_NODE_ROLE = "external"

NODE_SCHEMAS = (
    ProxmoxSDNZoneSchema,
    ProxmoxSDNVNetSchema,
    ProxmoxSDNSubnetSchema,
    ProxmoxSDNControllerSchema,
    ProxmoxSDNIPAMSchema,
    ProxmoxSDNIPAMEntrySchema,
    ProxmoxSDNDNSSchema,
    ProxmoxSDNFabricSchema,
    ProxmoxSDNFabricNodeSchema,
    ProxmoxSDNPrefixListSchema,
    ProxmoxSDNRouteMapSchema,
    ProxmoxSDNRouteMapEntrySchema,
    ProxmoxSDNBridgeSchema,
    ProxmoxSDNBridgePortSchema,
)

MATCHLINK_SCHEMAS = (
    ProxmoxSDNZoneDeployedOnNodeMatchLink,
    ProxmoxSDNVNetDeployedOnNodeMatchLink,
    ProxmoxSDNFabricNeighborMatchLink,
    ProxmoxSDNFabricInterfaceMatchLink,
)


# ============================================================================
# GET functions - retrieve data from Proxmox API
# ============================================================================


@timeit
@proxmox_optional_endpoint(list)
@proxmox_api_retry
def get_zones(proxmox_client: Any) -> list[dict[str, Any]]:
    """
    Get the running SDN zones.

    :param proxmox_client: Proxmox API client
    :return: List of zone dicts
    """
    return proxmox_client.cluster.sdn.zones.get(running=1)


@timeit
@proxmox_optional_endpoint(list)
@proxmox_api_retry
def get_vnets(proxmox_client: Any) -> list[dict[str, Any]]:
    """
    Get the running SDN VNets.

    :param proxmox_client: Proxmox API client
    :return: List of VNet dicts
    """
    return proxmox_client.cluster.sdn.vnets.get(running=1)


@timeit
@proxmox_api_retry
def get_subnets(proxmox_client: Any, vnet: str) -> list[dict[str, Any]]:
    """
    Get the running subnets of a VNet, with their full configuration.

    :param proxmox_client: Proxmox API client
    :param vnet: VNet name
    :return: List of subnet dicts
    """
    return proxmox_client.cluster.sdn.vnets(vnet).subnets.get(running=1)


@timeit
@proxmox_api_retry
def get_vnet_firewall_options(proxmox_client: Any, vnet: str) -> dict[str, Any]:
    """
    Get the firewall options of a VNet.

    :param proxmox_client: Proxmox API client
    :param vnet: VNet name
    :return: Firewall options dict
    """
    return proxmox_client.cluster.sdn.vnets(vnet).firewall.options.get()


@timeit
@proxmox_api_retry
def get_vnet_firewall_rules(proxmox_client: Any, vnet: str) -> list[dict[str, Any]]:
    """
    Get the firewall rules of a VNet.

    :param proxmox_client: Proxmox API client
    :param vnet: VNet name
    :return: List of firewall rule dicts
    """
    return proxmox_client.cluster.sdn.vnets(vnet).firewall.rules.get()


@timeit
@proxmox_optional_endpoint(list)
@proxmox_api_retry
def get_controllers(proxmox_client: Any) -> list[dict[str, Any]]:
    """
    Get the running SDN controllers.

    :param proxmox_client: Proxmox API client
    :return: List of controller dicts
    """
    return proxmox_client.cluster.sdn.controllers.get(running=1)


@timeit
@proxmox_optional_endpoint(list)
@proxmox_api_retry
def get_ipams(proxmox_client: Any) -> list[dict[str, Any]]:
    """
    Get the SDN IPAM plugins.

    :param proxmox_client: Proxmox API client
    :return: List of IPAM dicts
    """
    return proxmox_client.cluster.sdn.ipams.get()


@timeit
@proxmox_api_retry
def get_ipam_status(proxmox_client: Any, ipam: str) -> list[dict[str, Any]]:
    """
    Get the address entries of an IPAM.

    :param proxmox_client: Proxmox API client
    :param ipam: IPAM name
    :return: List of address entry dicts
    """
    return proxmox_client.cluster.sdn.ipams(ipam).status.get()


@timeit
@proxmox_optional_endpoint(list)
@proxmox_api_retry
def get_dns(proxmox_client: Any) -> list[dict[str, Any]]:
    """
    Get the SDN DNS plugins.

    :param proxmox_client: Proxmox API client
    :return: List of DNS plugin dicts
    """
    return proxmox_client.cluster.sdn.dns.get()


@timeit
@proxmox_optional_endpoint(dict)
@proxmox_api_retry
def get_fabrics(proxmox_client: Any) -> dict[str, Any]:
    """
    Get the running SDN fabrics and their nodes. Proxmox VE 9 only.

    :param proxmox_client: Proxmox API client
    :return: Dict with the fabrics and nodes lists
    """
    return proxmox_client.cluster.sdn.fabrics.all.get(running=1)


@timeit
@proxmox_optional_endpoint(list)
@proxmox_api_retry
def get_prefix_lists(proxmox_client: Any) -> list[dict[str, Any]]:
    """
    Get the running SDN prefix lists with their entries. Proxmox VE 9 only.

    :param proxmox_client: Proxmox API client
    :return: List of prefix list dicts
    """
    return proxmox_client.cluster.sdn("prefix-lists").get(running=1, verbose=1)


@timeit
@proxmox_optional_endpoint(list)
@proxmox_api_retry
def get_route_maps(proxmox_client: Any) -> list[dict[str, Any]]:
    """
    Get the running SDN route map IDs. Proxmox VE 9 only.

    :param proxmox_client: Proxmox API client
    :return: List of route map dicts
    """
    return proxmox_client.cluster.sdn("route-maps").get(running=1)


@timeit
@proxmox_optional_endpoint(list)
@proxmox_api_retry
def get_route_map_entries(proxmox_client: Any) -> list[dict[str, Any]]:
    """
    Get the running entries of every SDN route map. Proxmox VE 9 only.

    :param proxmox_client: Proxmox API client
    :return: List of route map entry dicts
    """
    return proxmox_client.cluster.sdn("route-maps").entries.get(running=1)


@timeit
@proxmox_optional_endpoint(list)
@proxmox_api_retry
def get_node_zones(proxmox_client: Any, node_name: str) -> list[dict[str, Any]]:
    """
    Get the status of each SDN zone on a node.

    :param proxmox_client: Proxmox API client
    :param node_name: Node name
    :return: List of zone status dicts
    """
    return proxmox_client.nodes(node_name).sdn.zones.get()


@timeit
@proxmox_api_retry
def get_node_zone_content(
    proxmox_client: Any,
    node_name: str,
    zone: str,
) -> list[dict[str, Any]]:
    """
    Get the status of each VNet of a zone on a node.

    :param proxmox_client: Proxmox API client
    :param node_name: Node name
    :param zone: Zone name
    :return: List of VNet status dicts
    """
    return proxmox_client.nodes(node_name).sdn.zones(zone).content.get()


@timeit
@proxmox_optional_endpoint(list)
@proxmox_api_retry
def get_node_zone_bridges(
    proxmox_client: Any,
    node_name: str,
    zone: str,
) -> list[dict[str, Any]]:
    """
    Get the bridges of a zone on a node, with their ports. Proxmox VE 9 only.

    :param proxmox_client: Proxmox API client
    :param node_name: Node name
    :param zone: Zone name
    :return: List of bridge dicts
    """
    return proxmox_client.nodes(node_name).sdn.zones(zone).bridges.get()


@timeit
@proxmox_optional_endpoint(list)
@proxmox_api_retry
def get_node_zone_ip_vrf(
    proxmox_client: Any,
    node_name: str,
    zone: str,
) -> list[dict[str, Any]]:
    """
    Get the IP VRF routing table of an EVPN zone on a node. Proxmox VE 9 only.

    :param proxmox_client: Proxmox API client
    :param node_name: Node name
    :param zone: Zone name
    :return: List of route dicts
    """
    return proxmox_client.nodes(node_name).sdn.zones(zone)("ip-vrf").get()


@timeit
@proxmox_optional_endpoint(list)
@proxmox_api_retry
def get_node_vnet_mac_vrf(
    proxmox_client: Any,
    node_name: str,
    vnet: str,
) -> list[dict[str, Any]]:
    """
    Get the MAC VRF table of an EVPN VNet on a node. Proxmox VE 9 only.

    :param proxmox_client: Proxmox API client
    :param node_name: Node name
    :param vnet: VNet name
    :return: List of MAC VRF entry dicts
    """
    return proxmox_client.nodes(node_name).sdn.vnets(vnet)("mac-vrf").get()


@timeit
@proxmox_optional_endpoint(list)
@proxmox_api_retry
def get_node_fabric_interfaces(
    proxmox_client: Any,
    node_name: str,
    fabric: str,
) -> list[dict[str, Any]]:
    """
    Get the state of the fabric interfaces of a node. Proxmox VE 9 only.

    :param proxmox_client: Proxmox API client
    :param node_name: Node name
    :param fabric: Fabric name
    :return: List of interface dicts
    """
    return proxmox_client.nodes(node_name).sdn.fabrics(fabric).interfaces.get()


@timeit
@proxmox_optional_endpoint(list)
@proxmox_api_retry
def get_node_fabric_neighbors(
    proxmox_client: Any,
    node_name: str,
    fabric: str,
) -> list[dict[str, Any]]:
    """
    Get the fabric neighbors a node sees. Proxmox VE 9 only.

    :param proxmox_client: Proxmox API client
    :param node_name: Node name
    :param fabric: Fabric name
    :return: List of neighbor dicts
    """
    return proxmox_client.nodes(node_name).sdn.fabrics(fabric).neighbors.get()


@timeit
@proxmox_optional_endpoint(list)
@proxmox_api_retry
def get_node_fabric_routes(
    proxmox_client: Any,
    node_name: str,
    fabric: str,
) -> list[dict[str, Any]]:
    """
    Get the routes a node learned through a fabric. Proxmox VE 9 only.

    :param proxmox_client: Proxmox API client
    :param node_name: Node name
    :param fabric: Fabric name
    :return: List of route dicts
    """
    return proxmox_client.nodes(node_name).sdn.fabrics(fabric).routes.get()


# ============================================================================
# TRANSFORM helpers
# ============================================================================


def _to_bool(value: Any) -> bool | None:
    """Convert a Proxmox boolean (0/1, "0"/"1", true/false) to bool, keeping None."""
    if value is None:
        return None
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "on")
    return bool(value)


def _to_list(value: Any) -> list[str]:
    """Split a comma-separated string, or copy a list, into a list of strings."""
    if value is None or value == "":
        return []
    if isinstance(value, list):
        return [str(item) for item in value if item not in (None, "")]
    return [item.strip() for item in str(value).split(",") if item.strip()]


def _parse_property_string(value: Any) -> dict[str, Any]:
    """
    Parse a Proxmox property string such as "key=ip-address-prefix-list,value=x".

    The API returns these nested values either as strings or already parsed,
    so a dict is returned unchanged.
    """
    if isinstance(value, dict):
        return value
    result: dict[str, Any] = {}
    if not isinstance(value, str):
        return result
    for part in value.split(","):
        if "=" in part:
            key, _, item = part.partition("=")
            result[key.strip()] = item.strip()
    return result


def _key_value(value: Any) -> str:
    """Render a key/value property string as key=value."""
    parsed = _parse_property_string(value)
    if "key" not in parsed:
        return str(value)
    if parsed.get("value") in (None, ""):
        return str(parsed["key"])
    return f"{parsed['key']}={parsed['value']}"


def _scoped(cluster_id: str, natural_id: Any) -> str | None:
    """Build a cluster-scoped ID, or None when the natural ID is empty."""
    if natural_id in (None, ""):
        return None
    return cluster_scoped_id(cluster_id, natural_id)


def _to_int(value: Any) -> int | None:
    """Convert a numeric value to int, returning None when it is not numeric."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


# ============================================================================
# TRANSFORM functions - cluster configuration
# ============================================================================


def transform_zones(
    zones: list[dict[str, Any]],
    cluster_id: str,
) -> list[dict[str, Any]]:
    """
    Transform SDN zones.

    :param zones: Raw zone data from the API
    :param cluster_id: Parent cluster ID
    :return: List of zone dicts
    """
    result = []
    for zone in zones:
        name = zone["zone"]
        secondary_controllers = _to_list(zone.get("secondary-controllers"))
        controllers = [zone.get("controller"), *secondary_controllers]
        dns_plugins = [zone.get("dns"), zone.get("reversedns")]
        result.append(
            {
                "id": cluster_scoped_id(cluster_id, name),
                "cluster_id": cluster_id,
                "name": name,
                "type": zone.get("type"),
                "nodes": _to_list(zone.get("nodes")),
                "ipam": zone.get("ipam"),
                "dns": zone.get("dns"),
                "reversedns": zone.get("reversedns"),
                "dnszone": zone.get("dnszone"),
                "dhcp": zone.get("dhcp"),
                "mtu": zone.get("mtu"),
                "bridge": zone.get("bridge"),
                "bridge_disable_mac_learning": _to_bool(
                    zone.get("bridge-disable-mac-learning"),
                ),
                "tag": zone.get("tag"),
                "vlan_protocol": zone.get("vlan-protocol"),
                "peers": _to_list(zone.get("peers")),
                "vxlan_port": zone.get("vxlan-port"),
                "fabric": zone.get("fabric"),
                "controller": zone.get("controller"),
                "secondary_controllers": secondary_controllers,
                "vrf_vxlan": zone.get("vrf-vxlan"),
                "mac": zone.get("mac"),
                "exitnodes": _to_list(zone.get("exitnodes")),
                "exitnodes_primary": zone.get("exitnodes-primary"),
                "exitnodes_local_routing": _to_bool(
                    zone.get("exitnodes-local-routing"),
                ),
                "advertise_subnets": _to_bool(zone.get("advertise-subnets")),
                "disable_arp_nd_suppression": _to_bool(
                    zone.get("disable-arp-nd-suppression"),
                ),
                "rt_import": _to_list(zone.get("rt-import")),
                "controller_ids": [
                    cluster_scoped_id(cluster_id, c) for c in controllers if c
                ],
                "ipam_id": _scoped(cluster_id, zone.get("ipam")),
                "dns_ids": sorted(
                    {cluster_scoped_id(cluster_id, d) for d in dns_plugins if d},
                ),
                "fabric_id": _scoped(cluster_id, zone.get("fabric")),
            },
        )
    return result


def transform_vnets(
    vnets: list[dict[str, Any]],
    firewall_options: dict[str, dict[str, Any]],
    cluster_id: str,
) -> list[dict[str, Any]]:
    """
    Transform SDN VNets, merging their firewall options.

    :param vnets: Raw VNet data from the API
    :param firewall_options: Firewall options keyed by VNet name
    :param cluster_id: Parent cluster ID
    :return: List of VNet dicts
    """
    result = []
    for vnet in vnets:
        name = vnet["vnet"]
        options = firewall_options.get(name) or {}
        result.append(
            {
                "id": cluster_scoped_id(cluster_id, name),
                "cluster_id": cluster_id,
                "name": name,
                "zone": vnet.get("zone"),
                "zone_id": _scoped(cluster_id, vnet.get("zone")),
                "alias": vnet.get("alias"),
                "tag": vnet.get("tag"),
                "vlanaware": _to_bool(vnet.get("vlanaware")),
                "isolate_ports": _to_bool(vnet.get("isolate-ports")),
                "firewall_enable": _to_bool(options.get("enable")),
                "firewall_policy_forward": options.get("policy_forward"),
                "firewall_log_level_forward": options.get("log_level_forward"),
            },
        )
    return result


def subnet_cidr(subnet: dict[str, Any], zone: str | None) -> str | None:
    """
    Return the CIDR of an SDN subnet.

    The API identifies a subnet as zone-network-prefixlength, such as
    zone1-10.0.0.0-24, and also returns the CIDR in the cidr field.

    :param subnet: Raw subnet data from the API
    :param zone: Zone of the subnet VNet, used to strip the ID prefix
    :return: CIDR such as 10.0.0.0/24, or None if it cannot be derived
    """
    if subnet.get("cidr"):
        return subnet["cidr"]
    subnet_id = subnet.get("subnet") or ""
    if "/" in subnet_id:
        return subnet_id
    zone = subnet.get("zone") or zone
    if zone and subnet_id.startswith(f"{zone}-"):
        network, _, prefix_length = subnet_id[len(zone) + 1 :].rpartition("-")
        if network and prefix_length.isdigit():
            return f"{network}/{prefix_length}"
    return None


def _dhcp_range(value: Any) -> str:
    parsed = _parse_property_string(value)
    start = parsed.get("start-address")
    end = parsed.get("end-address")
    if start and end:
        return f"{start}-{end}"
    return str(value)


def transform_subnets(
    subnets_by_vnet: dict[str, list[dict[str, Any]]],
    vnet_zones: dict[str, str | None],
    cluster_id: str,
) -> list[dict[str, Any]]:
    """
    Transform SDN subnets.

    :param subnets_by_vnet: Raw subnet data keyed by VNet name
    :param vnet_zones: Zone name keyed by VNet name
    :param cluster_id: Parent cluster ID
    :return: List of subnet dicts
    """
    result = []
    for vnet, subnets in subnets_by_vnet.items():
        for subnet in subnets:
            subnet_id = subnet["subnet"]
            zone = subnet.get("zone") or vnet_zones.get(vnet)
            result.append(
                {
                    "id": cluster_scoped_id(cluster_id, subnet_id),
                    "cluster_id": cluster_id,
                    "subnet": subnet_id,
                    "cidr": subnet_cidr(subnet, zone),
                    "vnet": vnet,
                    "vnet_id": cluster_scoped_id(cluster_id, vnet),
                    "zone": zone,
                    "gateway": subnet.get("gateway"),
                    "snat": _to_bool(subnet.get("snat")),
                    "dnszoneprefix": subnet.get("dnszoneprefix"),
                    "dhcp_ranges": [
                        _dhcp_range(r) for r in subnet.get("dhcp-range") or []
                    ],
                    "dhcp_dns_server": subnet.get("dhcp-dns-server"),
                },
            )
    return result


def transform_controllers(
    controllers: list[dict[str, Any]],
    cluster_id: str,
) -> list[dict[str, Any]]:
    """
    Transform SDN controllers.

    :param controllers: Raw controller data from the API
    :param cluster_id: Parent cluster ID
    :return: List of controller dicts
    """
    result = []
    for controller in controllers:
        name = controller["controller"]
        nodes = _to_list(controller.get("nodes"))
        node_names = sorted({*_to_list(controller.get("node")), *nodes})
        route_maps = [controller.get("route-map-in"), controller.get("route-map-out")]
        result.append(
            {
                "id": cluster_scoped_id(cluster_id, name),
                "cluster_id": cluster_id,
                "name": name,
                "type": controller.get("type"),
                "asn": controller.get("asn"),
                "peers": _to_list(controller.get("peers")),
                "node": controller.get("node"),
                "nodes": nodes,
                "fabric": controller.get("fabric"),
                "bgp_mode": controller.get("bgp-mode"),
                "ebgp": _to_bool(controller.get("ebgp")),
                "ebgp_multihop": controller.get("ebgp-multihop"),
                # The API reads this option as bgp-multipath-as-relax and
                # writes it as bgp-multipath-as-path-relax.
                "bgp_multipath_as_relax": _to_bool(
                    controller.get(
                        "bgp-multipath-as-relax",
                        controller.get("bgp-multipath-as-path-relax"),
                    ),
                ),
                "loopback": controller.get("loopback"),
                "peer_group_name": controller.get("peer-group-name"),
                "route_map_in": controller.get("route-map-in"),
                "route_map_out": controller.get("route-map-out"),
                "isis_domain": controller.get("isis-domain"),
                "isis_ifaces": _to_list(controller.get("isis-ifaces")),
                "isis_net": controller.get("isis-net"),
                "node_ids": [cluster_scoped_id(cluster_id, n) for n in node_names],
                "fabric_id": _scoped(cluster_id, controller.get("fabric")),
                "route_map_ids": sorted(
                    {cluster_scoped_id(cluster_id, r) for r in route_maps if r},
                ),
            },
        )
    return result


def transform_ipams(
    ipams: list[dict[str, Any]],
    cluster_id: str,
) -> list[dict[str, Any]]:
    """
    Transform SDN IPAM plugins. The API token is never read.

    :param ipams: Raw IPAM data from the API
    :param cluster_id: Parent cluster ID
    :return: List of IPAM dicts
    """
    return [
        {
            "id": cluster_scoped_id(cluster_id, ipam["ipam"]),
            "cluster_id": cluster_id,
            "name": ipam["ipam"],
            "type": ipam.get("type"),
            "url": ipam.get("url"),
            "section": ipam.get("section"),
        }
        for ipam in ipams
    ]


def transform_ipam_entries(
    entries_by_ipam: dict[str, list[dict[str, Any]]],
    cluster_id: str,
) -> list[dict[str, Any]]:
    """
    Transform the address entries of IPAM plugins.

    :param entries_by_ipam: Raw IPAM status entries keyed by IPAM name
    :param cluster_id: Parent cluster ID
    :return: List of IPAM entry dicts
    """
    result = []
    for ipam, entries in entries_by_ipam.items():
        # The API schema does not type the status response, so skip anything
        # that is not a list of entry dicts instead of failing the sync.
        if not isinstance(entries, list):
            logger.warning("Ignoring IPAM %s status that is not a list", ipam)
            continue
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            ip = entry.get("ip")
            if not ip:
                continue
            zone = entry.get("zone")
            subnet = entry.get("subnet")
            result.append(
                {
                    "id": cluster_scoped_id(cluster_id, f"{ipam}:{zone}:{subnet}:{ip}"),
                    "cluster_id": cluster_id,
                    "ipam": ipam,
                    "ipam_id": cluster_scoped_id(cluster_id, ipam),
                    "ip": ip,
                    "zone": zone,
                    "subnet": subnet,
                    "vnet": entry.get("vnet"),
                    "mac": entry.get("mac"),
                    "hostname": entry.get("hostname"),
                    "vmid": _to_int(entry.get("vmid")),
                    "gateway": _to_bool(entry.get("gateway")) or False,
                },
            )
    return result


def transform_dns(
    dns_plugins: list[dict[str, Any]],
    cluster_id: str,
) -> list[dict[str, Any]]:
    """
    Transform SDN DNS plugins. The API key is never read.

    :param dns_plugins: Raw DNS plugin data from the API
    :param cluster_id: Parent cluster ID
    :return: List of DNS plugin dicts
    """
    return [
        {
            "id": cluster_scoped_id(cluster_id, dns["dns"]),
            "cluster_id": cluster_id,
            "name": dns["dns"],
            "type": dns.get("type"),
            "url": dns.get("url"),
            "ttl": dns.get("ttl"),
        }
        for dns in dns_plugins
    ]


def _prefix_list_entry(value: Any) -> tuple[int, str]:
    entry = _parse_property_string(value)
    seq = _to_int(entry.get("seq"))
    text = f"seq {seq} " if seq is not None else ""
    text += f"{entry.get('action')} {entry.get('prefix')}"
    if entry.get("ge") not in (None, ""):
        text += f" ge {entry['ge']}"
    if entry.get("le") not in (None, ""):
        text += f" le {entry['le']}"
    return (seq if seq is not None else 0, text)


def transform_prefix_lists(
    prefix_lists: list[dict[str, Any]],
    cluster_id: str,
) -> list[dict[str, Any]]:
    """
    Transform SDN prefix lists, flattening their entries in evaluation order.

    :param prefix_lists: Raw prefix list data from the API
    :param cluster_id: Parent cluster ID
    :return: List of prefix list dicts
    """
    return [
        {
            "id": cluster_scoped_id(cluster_id, prefix_list["id"]),
            "cluster_id": cluster_id,
            "name": prefix_list["id"],
            "entries": [
                text
                for _, text in sorted(
                    (_prefix_list_entry(e) for e in prefix_list.get("entries") or []),
                    key=lambda item: item[0],
                )
            ],
        }
        for prefix_list in prefix_lists
    ]


def transform_route_maps(
    route_maps: list[dict[str, Any]],
    entries: list[dict[str, Any]],
    cluster_id: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """
    Transform SDN route maps and their entries.

    :param route_maps: Raw route map data from the API
    :param entries: Raw route map entry data from the API
    :param cluster_id: Parent cluster ID
    :return: Tuple of route map dicts and route map entry dicts
    """
    names = {route_map["id"] for route_map in route_maps}
    transformed_entries = []
    for entry in entries:
        route_map = entry["route-map-id"]
        names.add(route_map)
        matches = [_key_value(m) for m in entry.get("match") or []]
        prefix_lists = sorted(
            {
                str(parsed["value"])
                for parsed in (
                    _parse_property_string(m) for m in entry.get("match") or []
                )
                if str(parsed.get("key", "")).endswith("prefix-list")
                and parsed.get("value")
            },
        )
        exit_action = entry.get("exit-action")
        transformed_entries.append(
            {
                "id": cluster_scoped_id(cluster_id, f"{route_map}:{entry['order']}"),
                "cluster_id": cluster_id,
                "route_map": route_map,
                "route_map_id": cluster_scoped_id(cluster_id, route_map),
                "order": entry["order"],
                "action": entry.get("action"),
                "match": matches,
                "set": [_key_value(s) for s in entry.get("set") or []],
                "exit_action": (
                    _key_value(exit_action).replace("=", " ") if exit_action else None
                ),
                "call": entry.get("call"),
                "call_id": _scoped(cluster_id, entry.get("call")),
                "prefix_list_ids": [
                    cluster_scoped_id(cluster_id, p) for p in prefix_lists
                ],
            },
        )
    transformed_maps = [
        {
            "id": cluster_scoped_id(cluster_id, name),
            "cluster_id": cluster_id,
            "name": name,
        }
        for name in sorted(names)
    ]
    return transformed_maps, transformed_entries


def transform_fabrics(
    fabrics: list[dict[str, Any]],
    cluster_id: str,
) -> list[dict[str, Any]]:
    """
    Transform SDN fabrics.

    :param fabrics: Raw fabric data from the API
    :param cluster_id: Parent cluster ID
    :return: List of fabric dicts
    """
    result = []
    for fabric in fabrics:
        name = fabric["id"]
        redistribute = []
        route_maps = set()
        for item in fabric.get("redistribute") or []:
            parsed = _parse_property_string(item)
            source = parsed.get("source", str(item))
            route_map = parsed.get("route-map")
            if route_map:
                route_maps.add(route_map)
                redistribute.append(f"{source}:{route_map}")
            else:
                redistribute.append(str(source))
        result.append(
            {
                "id": cluster_scoped_id(cluster_id, name),
                "cluster_id": cluster_id,
                "name": name,
                "protocol": fabric.get("protocol"),
                "ip_prefix": fabric.get("ip_prefix"),
                "ip6_prefix": fabric.get("ip6_prefix"),
                "area": fabric.get("area"),
                "hello_interval": fabric.get("hello_interval"),
                "csnp_interval": fabric.get("csnp_interval"),
                "persistent_keepalive": fabric.get("persistent_keepalive"),
                "route_filter": fabric.get("route_filter"),
                "route_filter_id": _scoped(cluster_id, fabric.get("route_filter")),
                "redistribute": redistribute,
                "route_map_ids": [
                    cluster_scoped_id(cluster_id, r) for r in sorted(route_maps)
                ],
            },
        )
    return result


def fabric_node_interfaces(fabric_node: dict[str, Any]) -> list[dict[str, Any]]:
    """
    Parse the interfaces of a fabric node configuration.

    :param fabric_node: Raw fabric node data from the API
    :return: List of interface dicts with at least a name
    """
    interfaces = []
    for item in fabric_node.get("interfaces") or []:
        parsed = _parse_property_string(item)
        if parsed.get("name"):
            interfaces.append(parsed)
    return interfaces


def transform_fabric_nodes(
    fabric_nodes: list[dict[str, Any]],
    cluster_id: str,
) -> list[dict[str, Any]]:
    """
    Transform the members of SDN fabrics.

    :param fabric_nodes: Raw fabric node data from the API
    :param cluster_id: Parent cluster ID
    :return: List of fabric node dicts
    """
    result = []
    for fabric_node in fabric_nodes:
        fabric = fabric_node["fabric_id"]
        node_name = fabric_node["node_id"]
        role = fabric_node.get("role")
        result.append(
            {
                "id": cluster_scoped_id(cluster_id, f"{fabric}:{node_name}"),
                "cluster_id": cluster_id,
                "fabric": fabric,
                "fabric_id": cluster_scoped_id(cluster_id, fabric),
                "node_name": node_name,
                "proxmox_node_id": (
                    None
                    if role == EXTERNAL_FABRIC_NODE_ROLE
                    else cluster_scoped_id(cluster_id, node_name)
                ),
                "protocol": fabric_node.get("protocol"),
                "ip": fabric_node.get("ip"),
                "ip6": fabric_node.get("ip6"),
                "interfaces": [i["name"] for i in fabric_node_interfaces(fabric_node)],
                "role": role,
                "endpoint": fabric_node.get("endpoint"),
                "allowed_ips": _to_list(fabric_node.get("allowed_ips")),
                "public_key": fabric_node.get("public_key"),
                "neighbors": [],
                "routes": [],
            },
        )
    return result


# ============================================================================
# TRANSFORM functions - per-node state
# ============================================================================


def format_ip_vrf(routes: list[dict[str, Any]]) -> list[str]:
    """Render IP VRF routes as 'cidr via nexthop[,nexthop] proto <p> metric <m>'."""
    result = []
    for route in routes:
        text = f"{route.get('ip')} via {','.join(_to_list(route.get('nexthops')))}"
        if route.get("protocol"):
            text += f" proto {route['protocol']}"
        if route.get("metric") is not None:
            text += f" metric {route['metric']}"
        result.append(text)
    return result


def format_mac_vrf(entries: list[dict[str, Any]]) -> list[str]:
    """Render MAC VRF entries as 'mac ip via nexthop'."""
    return [
        f"{entry.get('mac')} {entry.get('ip')} via {entry.get('nexthop')}"
        for entry in entries
    ]


def format_fabric_routes(routes: list[dict[str, Any]]) -> list[str]:
    """Render fabric routes as 'cidr via nexthop[,nexthop]'."""
    return [
        f"{route.get('route')} via {','.join(_to_list(route.get('via')))}"
        for route in routes
    ]


def transform_bridges(
    bridges: list[dict[str, Any]],
    node_name: str,
    zone: str,
    cluster_id: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """
    Transform the VNet bridges of a zone on a node and their ports.

    :param bridges: Raw bridge data from the API
    :param node_name: Node name
    :param zone: Zone name
    :param cluster_id: Parent cluster ID
    :return: Tuple of bridge dicts and bridge port dicts
    """
    transformed_bridges = []
    transformed_ports = []
    for bridge in bridges:
        name = bridge["name"]
        bridge_id = cluster_scoped_id(cluster_id, f"{node_name}:{name}")
        ports = bridge.get("ports") or []
        transformed_bridges.append(
            {
                "id": bridge_id,
                "cluster_id": cluster_id,
                "name": name,
                "node_name": node_name,
                "node_id": cluster_scoped_id(cluster_id, node_name),
                "zone": zone,
                # The bridge of an SDN VNet carries the VNet name.
                "vnet_id": cluster_scoped_id(cluster_id, name),
                "vlan_filtering": _to_bool(bridge.get("vlan_filtering")),
                "ports": [port["name"] for port in ports if port.get("name")],
            },
        )
        for port in ports:
            if not port.get("name"):
                continue
            index = port.get("index")
            transformed_ports.append(
                {
                    "id": cluster_scoped_id(
                        cluster_id,
                        f"{node_name}:{name}:{port['name']}",
                    ),
                    "cluster_id": cluster_id,
                    "name": port["name"],
                    "bridge": name,
                    "bridge_id": bridge_id,
                    "node_name": node_name,
                    "vmid": _to_int(port.get("vmid")),
                    "index": None if index is None else str(index),
                    "net_id": None if index is None else f"net{index}",
                    "primary_vlan": _to_int(port.get("primary_vlan")),
                    "vlans": _to_list(port.get("vlans")),
                },
            )
    return transformed_bridges, transformed_ports


def resolve_fabric_neighbors(
    fabric_node_id: str,
    neighbors: list[dict[str, Any]],
    fabric_peers: dict[str, str],
) -> list[dict[str, Any]]:
    """
    Link the neighbors a fabric node reports to the other fabric nodes.

    FRR reports a neighbor by IP or hostname, so a neighbor is matched against
    the node names, router IDs and interface addresses of the fabric members.

    :param fabric_node_id: ID of the reporting fabric node
    :param neighbors: Raw neighbor data from the API
    :param fabric_peers: Fabric node ID keyed by node name and address
    :return: List of neighbor link dicts
    """
    links = []
    for neighbor in neighbors:
        neighbor_id = fabric_peers.get(str(neighbor.get("neighbor")))
        if not neighbor_id or neighbor_id == fabric_node_id:
            continue
        links.append(
            {
                "fabric_node_id": fabric_node_id,
                "neighbor_id": neighbor_id,
                "status": neighbor.get("status"),
                "uptime": neighbor.get("uptime"),
            },
        )
    return links


def fabric_peer_index(
    fabric_nodes: list[dict[str, Any]],
    cluster_id: str,
) -> dict[str, dict[str, str]]:
    """
    Index the members of each fabric by node name and address.

    :param fabric_nodes: Raw fabric node data from the API
    :param cluster_id: Parent cluster ID
    :return: Per fabric name, the fabric node ID keyed by name and address
    """
    index: dict[str, dict[str, str]] = {}
    for fabric_node in fabric_nodes:
        fabric = fabric_node["fabric_id"]
        node_name = fabric_node["node_id"]
        node_id = cluster_scoped_id(cluster_id, f"{fabric}:{node_name}")
        peers = index.setdefault(fabric, {})
        keys = [node_name, fabric_node.get("ip"), fabric_node.get("ip6")]
        for interface in fabric_node_interfaces(fabric_node):
            keys.extend([interface.get("ip"), interface.get("ip6")])
        for key in keys:
            if key:
                peers[str(key).split("/")[0]] = node_id
    return index


def transform_fabric_interfaces(
    fabric_node: dict[str, Any],
    fabric_node_id: str,
    interface_states: list[dict[str, Any]],
    cluster_id: str,
) -> list[dict[str, Any]]:
    """
    Merge the configured and the reported interfaces of a fabric node.

    :param fabric_node: Raw fabric node data from the API
    :param fabric_node_id: ID of the fabric node
    :param interface_states: Raw interface state data reported by the node
    :param cluster_id: Parent cluster ID
    :return: List of fabric interface link dicts
    """
    node_name = fabric_node["node_id"]
    by_name: dict[str, dict[str, Any]] = {}
    for interface in fabric_node_interfaces(fabric_node):
        by_name[interface["name"]] = {
            "ip": interface.get("ip"),
            "ip6": interface.get("ip6"),
        }
    for state in interface_states:
        if not state.get("name"):
            continue
        link = by_name.setdefault(state["name"], {"ip": None, "ip6": None})
        link["state"] = state.get("state")
        link["type"] = state.get("type")
    return [
        {
            "fabric_node_id": fabric_node_id,
            "interface_id": cluster_scoped_id(cluster_id, f"{node_name}:{name}"),
            "ip": link.get("ip"),
            "ip6": link.get("ip6"),
            "state": link.get("state"),
            "type": link.get("type"),
        }
        for name, link in sorted(by_name.items())
    ]


# ============================================================================
# LOAD functions - ingest data to Neo4j using modern data model
# ============================================================================


def load_sdn_nodes(
    neo4j_session: neo4j.Session,
    schema: Any,
    data: list[dict[str, Any]],
    cluster_id: str,
    update_tag: int,
) -> None:
    """
    Load SDN nodes of one schema.

    :param neo4j_session: Neo4j session
    :param schema: Node schema instance
    :param data: Transformed node dicts
    :param cluster_id: Parent cluster ID
    :param update_tag: Sync timestamp
    """
    if not data:
        return
    load(
        neo4j_session,
        schema,
        data,
        lastupdated=update_tag,
        CLUSTER_ID=cluster_id,
    )


def load_sdn_matchlinks(
    neo4j_session: neo4j.Session,
    schema: Any,
    data: list[dict[str, Any]],
    cluster_id: str,
    update_tag: int,
) -> None:
    """
    Load SDN relationships that carry per-node state.

    :param neo4j_session: Neo4j session
    :param schema: MatchLink relationship schema instance
    :param data: Transformed link dicts
    :param cluster_id: Parent cluster ID
    :param update_tag: Sync timestamp
    """
    if not data:
        return
    load_matchlinks(
        neo4j_session,
        schema,
        data,
        lastupdated=update_tag,
        _sub_resource_label="ProxmoxCluster",
        _sub_resource_id=cluster_id,
    )


# ============================================================================
# SYNC function - orchestrates Get → Transform → Load
# ============================================================================


class NodeStateUnavailable(Exception):
    """A node could not report part of its SDN state."""

    def __init__(self, endpoint: str, error: Exception) -> None:
        super().__init__(f"{endpoint}: {error}")
        self.endpoint = endpoint
        self.error = error


def _read_node_state(endpoint: str, getter: Any, *args: Any) -> Any:
    """
    Call a per-node SDN state getter and name the endpoint when it fails.

    FRR or the SDN daemons of a single node can fail, for example with an HTTP
    500 from the VRF or fabric endpoints, while the cluster configuration and
    the other nodes answer. Such an error must not stop the whole SDN sync.

    :param endpoint: API path of the getter, for the log
    :param getter: The getter to call
    :return: What the getter returns
    :raises NodeStateUnavailable: When the API answers with an error
    """
    try:
        return getter(*args)
    except (ResourceException, requests.exceptions.RequestException) as e:
        raise NodeStateUnavailable(endpoint, e) from e


def _read_zone_state(
    proxmox_client: Any,
    cluster_id: str,
    node_name: str,
    node_zone: dict[str, Any],
    zone_types: dict[str, Any],
    vnet_zones: dict[str, Any],
) -> dict[str, list[dict[str, Any]]]:
    """
    Read and transform what one node reports for one SDN zone.

    :raises NodeStateUnavailable: When one of the zone endpoints fails
    """
    zone = node_zone["zone"]
    node_id = cluster_scoped_id(cluster_id, node_name)
    is_evpn = zone_types.get(zone) == EVPN_ZONE_TYPE
    ip_vrf = (
        format_ip_vrf(
            _read_node_state(
                "/nodes/{node}/sdn/zones/{zone}/ip-vrf",
                get_node_zone_ip_vrf,
                proxmox_client,
                node_name,
                zone,
            ),
        )
        if is_evpn
        else []
    )
    zone_state: dict[str, list[dict[str, Any]]] = {
        "zone_links": [
            {
                "zone_id": cluster_scoped_id(cluster_id, zone),
                "node_id": node_id,
                "status": node_zone.get("status"),
                "ip_vrf": ip_vrf,
            },
        ],
        "vnet_links": [],
    }

    contents = _read_node_state(
        "/nodes/{node}/sdn/zones/{zone}/content",
        get_node_zone_content,
        proxmox_client,
        node_name,
        zone,
    )
    for content in contents:
        vnet = content.get("vnet")
        if not vnet:
            continue
        mac_vrf = (
            format_mac_vrf(
                _read_node_state(
                    "/nodes/{node}/sdn/vnets/{vnet}/mac-vrf",
                    get_node_vnet_mac_vrf,
                    proxmox_client,
                    node_name,
                    vnet,
                ),
            )
            if is_evpn and vnet in vnet_zones
            else []
        )
        zone_state["vnet_links"].append(
            {
                "vnet_id": cluster_scoped_id(cluster_id, vnet),
                "node_id": node_id,
                "status": content.get("status"),
                "statusmsg": content.get("statusmsg"),
                "mac_vrf": mac_vrf,
            },
        )

    zone_state["bridges"], zone_state["ports"] = transform_bridges(
        _read_node_state(
            "/nodes/{node}/sdn/zones/{zone}/bridges",
            get_node_zone_bridges,
            proxmox_client,
            node_name,
            zone,
        ),
        node_name,
        zone,
        cluster_id,
    )
    return zone_state


def _read_fabric_state(
    proxmox_client: Any,
    cluster_id: str,
    fabric_node_raw: dict[str, Any],
    fabric_node: dict[str, Any],
    fabric_peers: dict[str, str],
) -> dict[str, list[dict[str, Any]]]:
    """
    Read and transform what one node reports for one fabric.

    Fills the neighbors and routes of the fabric node only when every fabric
    endpoint answered.

    :raises NodeStateUnavailable: When one of the fabric endpoints fails
    """
    node_name = fabric_node_raw["node_id"]
    fabric = fabric_node_raw["fabric_id"]
    neighbors = _read_node_state(
        "/nodes/{node}/sdn/fabrics/{fabric}/neighbors",
        get_node_fabric_neighbors,
        proxmox_client,
        node_name,
        fabric,
    )
    routes = _read_node_state(
        "/nodes/{node}/sdn/fabrics/{fabric}/routes",
        get_node_fabric_routes,
        proxmox_client,
        node_name,
        fabric,
    )
    interfaces = _read_node_state(
        "/nodes/{node}/sdn/fabrics/{fabric}/interfaces",
        get_node_fabric_interfaces,
        proxmox_client,
        node_name,
        fabric,
    )
    fabric_node["neighbors"] = [
        str(n["neighbor"]) for n in neighbors if n.get("neighbor")
    ]
    fabric_node["routes"] = format_fabric_routes(routes)
    return {
        "neighbor_links": resolve_fabric_neighbors(
            fabric_node["id"],
            neighbors,
            fabric_peers,
        ),
        "interface_links": transform_fabric_interfaces(
            fabric_node_raw,
            fabric_node["id"],
            interfaces,
            cluster_id,
        ),
    }


def _sync_node_state(
    proxmox_client: Any,
    cluster_id: str,
    zones: list[dict[str, Any]],
    vnets: list[dict[str, Any]],
    fabric_nodes_raw: list[dict[str, Any]],
    fabric_nodes: list[dict[str, Any]],
) -> tuple[dict[str, list[dict[str, Any]]], set[tuple[str, str | None]], set[str]]:
    """
    Read and transform what each online node reports for the SDN configuration.

    Fills the neighbors and routes of the fabric nodes in place. A node that
    fails to report a zone or a fabric is logged and skipped, and the sync goes
    on with the next zone, fabric or node. Errors listing the nodes propagate.

    :return: The node state, the (node name, zone name) pairs whose state could
        not be read, with zone None when the node could not list its zones, and
        the IDs of the fabric nodes whose state could not be read
    """
    zone_types = {zone["zone"]: zone.get("type") for zone in zones}
    vnet_zones = {vnet["vnet"]: vnet.get("zone") for vnet in vnets}
    fabric_nodes_by_id = {fn["id"]: fn for fn in fabric_nodes}
    peer_index = fabric_peer_index(fabric_nodes_raw, cluster_id)

    state: dict[str, list[dict[str, Any]]] = {
        "zone_links": [],
        "vnet_links": [],
        "bridges": [],
        "ports": [],
        "neighbor_links": [],
        "interface_links": [],
    }
    failed_zones: set[tuple[str, str | None]] = set()
    failed_fabric_nodes: set[str] = set()

    for node in get_nodes(proxmox_client):
        node_name = node["node"]
        if node.get("status") != "online":
            logger.info("Skipping SDN state of offline node %s", node_name)
            continue

        try:
            node_zones = _read_node_state(
                "/nodes/{node}/sdn/zones",
                get_node_zones,
                proxmox_client,
                node_name,
            )
        except NodeStateUnavailable as e:
            logger.warning(
                "Could not read SDN zones of node %s from %s, keeping its last "
                "known zone state: %s",
                node_name,
                e.endpoint,
                e.error,
            )
            failed_zones.add((node_name, None))
            node_zones = []

        for node_zone in node_zones:
            zone = node_zone["zone"]
            try:
                zone_state = _read_zone_state(
                    proxmox_client,
                    cluster_id,
                    node_name,
                    node_zone,
                    zone_types,
                    vnet_zones,
                )
            except NodeStateUnavailable as e:
                logger.warning(
                    "Could not read SDN zone %s of node %s from %s, keeping its "
                    "last known state: %s",
                    zone,
                    node_name,
                    e.endpoint,
                    e.error,
                )
                failed_zones.add((node_name, zone))
                continue
            for key, items in zone_state.items():
                state[key].extend(items)

        for fabric_node_raw in fabric_nodes_raw:
            if (
                fabric_node_raw["node_id"] != node_name
                or fabric_node_raw.get("role") == EXTERNAL_FABRIC_NODE_ROLE
            ):
                continue
            fabric = fabric_node_raw["fabric_id"]
            fabric_node_id = cluster_scoped_id(cluster_id, f"{fabric}:{node_name}")
            try:
                fabric_state = _read_fabric_state(
                    proxmox_client,
                    cluster_id,
                    fabric_node_raw,
                    fabric_nodes_by_id[fabric_node_id],
                    peer_index.get(fabric, {}),
                )
            except NodeStateUnavailable as e:
                logger.warning(
                    "Could not read SDN fabric %s of node %s from %s, keeping its "
                    "last known state: %s",
                    fabric,
                    node_name,
                    e.endpoint,
                    e.error,
                )
                failed_fabric_nodes.add(fabric_node_id)
                continue
            for key, items in fabric_state.items():
                state[key].extend(items)

    return state, failed_zones, failed_fabric_nodes


def _read_graph(neo4j_session: neo4j.Session, query: str, **kwargs: Any) -> list:
    return neo4j_session.execute_read(read_list_of_dicts_tx, query, **kwargs)


def keep_last_known_node_state(
    neo4j_session: neo4j.Session,
    cluster_id: str,
    state: dict[str, list[dict[str, Any]]],
    failed_zones: set[tuple[str, str | None]],
    failed_fabric_nodes: set[str],
    fabric_nodes: list[dict[str, Any]],
) -> None:
    """
    Add to the node state what the graph holds for the scopes that failed.

    The cleanup removes the per-node state that this sync does not load, so
    without this a node whose FRR answers an error would lose its zone and VNet
    deployments, bridges and fabric state until it answers again. Reloading the
    last known state keeps it, and the cleanup still removes stale state of the
    nodes that answered. Only reads the graph; the writes go through load().

    :param neo4j_session: Neo4j session
    :param cluster_id: Parent cluster ID
    :param state: Node state from _sync_node_state, extended in place
    :param failed_zones: (node name, zone name or None for all zones) pairs
    :param failed_fabric_nodes: IDs of fabric nodes whose state failed
    :param fabric_nodes: Transformed fabric nodes, whose neighbors and routes
        are filled in place for the failed ones
    """
    for node_name, zone in sorted(failed_zones, key=lambda f: (f[0], f[1] or "")):
        node_id = cluster_scoped_id(cluster_id, node_name)
        state["zone_links"].extend(
            _read_graph(
                neo4j_session,
                """
                MATCH (z:ProxmoxSDNZone)-[r:DEPLOYED_ON]->(:ProxmoxNode {id: $node_id})
                WHERE $zone IS NULL OR z.name = $zone
                RETURN z.id AS zone_id, $node_id AS node_id,
                       r.status AS status, r.ip_vrf AS ip_vrf
                """,
                node_id=node_id,
                zone=zone,
            ),
        )
        state["vnet_links"].extend(
            _read_graph(
                neo4j_session,
                """
                MATCH (v:ProxmoxSDNVNet)-[r:DEPLOYED_ON]->(:ProxmoxNode {id: $node_id})
                WHERE $zone IS NULL OR v.zone = $zone
                RETURN v.id AS vnet_id, $node_id AS node_id, r.status AS status,
                       r.statusmsg AS statusmsg, r.mac_vrf AS mac_vrf
                """,
                node_id=node_id,
                zone=zone,
            ),
        )
        for row in _read_graph(
            neo4j_session,
            """
            MATCH (:ProxmoxNode {id: $node_id})-[:HAS_SDN_BRIDGE]->(b:ProxmoxSDNBridge)
            WHERE $zone IS NULL OR b.zone = $zone
            OPTIONAL MATCH (b)-[:HAS_PORT]->(p:ProxmoxSDNBridgePort)
            RETURN properties(b) AS bridge, collect(properties(p)) AS ports
            """,
            node_id=node_id,
            zone=zone,
        ):
            bridge = row["bridge"]
            state["bridges"].append(
                {
                    **bridge,
                    "node_id": node_id,
                    "vnet_id": cluster_scoped_id(cluster_id, bridge["name"]),
                },
            )
            state["ports"].extend(
                {
                    **port,
                    "bridge_id": bridge["id"],
                    "net_id": (
                        None if port.get("index") is None else f"net{port['index']}"
                    ),
                }
                for port in row["ports"]
            )

    fabric_nodes_by_id = {fn["id"]: fn for fn in fabric_nodes}
    for fabric_node_id in sorted(failed_fabric_nodes):
        previous = _read_graph(
            neo4j_session,
            """
            MATCH (f:ProxmoxSDNFabricNode {id: $id})
            RETURN f.neighbors AS neighbors, f.routes AS routes
            """,
            id=fabric_node_id,
        )
        if previous:
            fabric_nodes_by_id[fabric_node_id]["neighbors"] = previous[0]["neighbors"]
            fabric_nodes_by_id[fabric_node_id]["routes"] = previous[0]["routes"]
        state["neighbor_links"].extend(
            _read_graph(
                neo4j_session,
                """
                MATCH (:ProxmoxSDNFabricNode {id: $id})-[r:FABRIC_NEIGHBOR]->(b:ProxmoxSDNFabricNode)
                RETURN $id AS fabric_node_id, b.id AS neighbor_id,
                       r.status AS status, r.uptime AS uptime
                """,
                id=fabric_node_id,
            ),
        )
        state["interface_links"].extend(
            _read_graph(
                neo4j_session,
                """
                MATCH (:ProxmoxSDNFabricNode {id: $id})-[r:USES_INTERFACE]->(i:ProxmoxNodeNetworkInterface)
                RETURN $id AS fabric_node_id, i.id AS interface_id, r.ip AS ip,
                       r.ip6 AS ip6, r.state AS state, r.type AS type
                """,
                id=fabric_node_id,
            ),
        )


@timeit
def sync(
    neo4j_session: neo4j.Session,
    proxmox_client: Any,
    cluster_id: str,
    update_tag: int,
    common_job_parameters: dict[str, Any],
    firewall_references: FirewallReferences | None = None,
) -> None:
    """
    Sync the SDN configuration and the SDN state of each node.

    Run it after the cluster, compute and firewall syncs so that relationships
    to nodes, node interfaces, guests and guest interfaces can be created.

    :param neo4j_session: Neo4j session
    :param proxmox_client: Proxmox API client
    :param cluster_id: Parent cluster ID
    :param update_tag: Sync timestamp
    :param common_job_parameters: Common parameters
    :param firewall_references: IP sets, aliases, and security groups returned
        by the firewall sync; VNet rules that name one of them link to it
    """
    logger.info("Syncing Proxmox SDN configuration")

    # GET - cluster configuration
    zones = get_zones(proxmox_client)
    vnets = get_vnets(proxmox_client)
    subnets_by_vnet = {}
    firewall_options = {}
    vnet_rules = []
    for vnet in vnets:
        name = vnet["vnet"]
        subnets_by_vnet[name] = get_subnets(proxmox_client, name)
        firewall_options[name] = get_vnet_firewall_options(proxmox_client, name)
        vnet_rules.extend(
            transform_firewall_rule_data(
                get_vnet_firewall_rules(proxmox_client, name),
                cluster_id,
                "vnet",
                name,
            ),
        )
    if firewall_references is not None:
        resolve_rule_references(vnet_rules, *firewall_references)
    controllers = get_controllers(proxmox_client)
    ipams = get_ipams(proxmox_client)
    entries_by_ipam = {
        ipam["ipam"]: get_ipam_status(proxmox_client, ipam["ipam"])
        for ipam in ipams
        if ipam.get("type") == PVE_IPAM_TYPE
    }
    dns_plugins = get_dns(proxmox_client)
    fabrics_data = get_fabrics(proxmox_client)
    prefix_lists = get_prefix_lists(proxmox_client)
    route_maps_raw = get_route_maps(proxmox_client)
    route_map_entries_raw = get_route_map_entries(proxmox_client)

    # TRANSFORM - cluster configuration
    fabric_nodes_raw = fabrics_data.get("nodes") or []
    fabric_nodes = transform_fabric_nodes(fabric_nodes_raw, cluster_id)
    route_maps, route_map_entries = transform_route_maps(
        route_maps_raw,
        route_map_entries_raw,
        cluster_id,
    )

    # GET and TRANSFORM - per-node state
    node_state, failed_zones, failed_fabric_nodes = _sync_node_state(
        proxmox_client,
        cluster_id,
        zones,
        vnets,
        fabric_nodes_raw,
        fabric_nodes,
    )
    keep_last_known_node_state(
        neo4j_session,
        cluster_id,
        node_state,
        failed_zones,
        failed_fabric_nodes,
        fabric_nodes,
    )

    # LOAD - referenced nodes first so relationships find their targets
    vnet_zones = {vnet["vnet"]: vnet.get("zone") for vnet in vnets}
    loads: list[tuple[Any, list[dict[str, Any]]]] = [
        (ProxmoxSDNIPAMSchema(), transform_ipams(ipams, cluster_id)),
        (ProxmoxSDNDNSSchema(), transform_dns(dns_plugins, cluster_id)),
        (
            ProxmoxSDNPrefixListSchema(),
            transform_prefix_lists(prefix_lists, cluster_id),
        ),
        (ProxmoxSDNRouteMapSchema(), route_maps),
        (ProxmoxSDNRouteMapEntrySchema(), route_map_entries),
        (
            ProxmoxSDNFabricSchema(),
            transform_fabrics(fabrics_data.get("fabrics") or [], cluster_id),
        ),
        (ProxmoxSDNFabricNodeSchema(), fabric_nodes),
        (ProxmoxSDNControllerSchema(), transform_controllers(controllers, cluster_id)),
        (ProxmoxSDNZoneSchema(), transform_zones(zones, cluster_id)),
        (
            ProxmoxSDNVNetSchema(),
            transform_vnets(vnets, firewall_options, cluster_id),
        ),
        (
            ProxmoxSDNSubnetSchema(),
            transform_subnets(subnets_by_vnet, vnet_zones, cluster_id),
        ),
        (
            ProxmoxSDNIPAMEntrySchema(),
            transform_ipam_entries(entries_by_ipam, cluster_id),
        ),
        (ProxmoxSDNBridgeSchema(), node_state["bridges"]),
        (ProxmoxSDNBridgePortSchema(), node_state["ports"]),
    ]
    for schema, data in loads:
        load_sdn_nodes(neo4j_session, schema, data, cluster_id, update_tag)

    load_firewall_rules(neo4j_session, vnet_rules, cluster_id, update_tag)

    matchlinks: list[tuple[Any, list[dict[str, Any]]]] = [
        (ProxmoxSDNZoneDeployedOnNodeMatchLink(), node_state["zone_links"]),
        (ProxmoxSDNVNetDeployedOnNodeMatchLink(), node_state["vnet_links"]),
        (ProxmoxSDNFabricNeighborMatchLink(), node_state["neighbor_links"]),
        (ProxmoxSDNFabricInterfaceMatchLink(), node_state["interface_links"]),
    ]
    for matchlink, data in matchlinks:
        load_sdn_matchlinks(neo4j_session, matchlink, data, cluster_id, update_tag)

    logger.info(
        "Synced %d SDN zones, %d VNets, %d controllers and %d fabrics",
        len(zones),
        len(vnets),
        len(controllers),
        len(fabrics_data.get("fabrics") or []),
    )


def cleanup(
    neo4j_session: neo4j.Session,
    common_job_parameters: dict[str, Any],
) -> None:
    """
    Remove stale SDN nodes and per-node SDN relationships of the cluster.

    VNet firewall rules are ProxmoxFirewallRule nodes, cleaned up with the
    other firewall rules.

    :param neo4j_session: Neo4j session
    :param common_job_parameters: Common parameters including UPDATE_TAG and CLUSTER_ID
    """
    for schema in NODE_SCHEMAS:
        GraphJob.from_node_schema(schema(), common_job_parameters).run(neo4j_session)
    for matchlink in MATCHLINK_SCHEMAS:
        GraphJob.from_matchlink(
            matchlink(),
            "ProxmoxCluster",
            common_job_parameters["CLUSTER_ID"],
            common_job_parameters["UPDATE_TAG"],
        ).run(neo4j_session)
