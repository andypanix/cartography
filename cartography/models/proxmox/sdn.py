"""
Data model for Proxmox VE Software-Defined Networking (SDN).

Covers the running SDN configuration (zones, VNets, subnets, controllers,
IPAM and DNS plugins, fabrics, prefix lists and route maps) and the state that
each node reports for it (zone and VNet status, VNet bridges and their ports,
fabric neighbors and interfaces).
"""

from dataclasses import dataclass

from cartography.models.core.common import PropertyRef
from cartography.models.core.nodes import CartographyNodeProperties
from cartography.models.core.nodes import CartographyNodeSchema
from cartography.models.core.relationships import CartographyRelProperties
from cartography.models.core.relationships import CartographyRelSchema
from cartography.models.core.relationships import LinkDirection
from cartography.models.core.relationships import make_source_node_matcher
from cartography.models.core.relationships import make_target_node_matcher
from cartography.models.core.relationships import OtherRelationships
from cartography.models.core.relationships import SourceNodeMatcher
from cartography.models.core.relationships import TargetNodeMatcher


@dataclass(frozen=True)
class ProxmoxSDNRelProperties(CartographyRelProperties):
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)


def _cluster_matcher() -> TargetNodeMatcher:
    return make_target_node_matcher(
        {"id": PropertyRef("CLUSTER_ID", set_in_kwargs=True)},
    )


# ============================================================================
# Zone
# ============================================================================


@dataclass(frozen=True)
class ProxmoxSDNZoneNodeProperties(CartographyNodeProperties):
    id: PropertyRef = PropertyRef(
        "id",
        description="Zone ID in the form cluster_id/zone, such as prod/evpn1.",
    )
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)
    cluster_id: PropertyRef = PropertyRef(
        "cluster_id",
        description="ID of the cluster that defines the zone.",
    )
    name: PropertyRef = PropertyRef(
        "name",
        extra_index=True,
        description="Zone name.",
    )
    type: PropertyRef = PropertyRef(
        "type",
        description="Zone type: simple, vlan, qinq, vxlan, evpn, or faucet.",
    )
    nodes: PropertyRef = PropertyRef(
        "nodes",
        description="Nodes where the zone is configured to be created; empty means every node.",
    )
    ipam: PropertyRef = PropertyRef(
        "ipam",
        description="ID of the IPAM plugin of the zone.",
    )
    dns: PropertyRef = PropertyRef(
        "dns",
        description="ID of the DNS plugin of the zone.",
    )
    reversedns: PropertyRef = PropertyRef(
        "reversedns",
        description="ID of the reverse DNS plugin of the zone.",
    )
    dnszone: PropertyRef = PropertyRef(
        "dnszone",
        description="DNS domain used to register guest hostnames.",
    )
    dhcp: PropertyRef = PropertyRef(
        "dhcp",
        description="DHCP server backend of the zone, such as dnsmasq.",
    )
    mtu: PropertyRef = PropertyRef(
        "mtu",
        description="MTU of the VNet bridges created for the zone.",
    )
    bridge: PropertyRef = PropertyRef(
        "bridge",
        description="Node bridge that carries the zone VLANs. VLAN and QinQ zones only.",
    )
    bridge_disable_mac_learning: PropertyRef = PropertyRef(
        "bridge_disable_mac_learning",
        description="Whether automatic MAC learning is disabled. VLAN zones only.",
    )
    tag: PropertyRef = PropertyRef(
        "tag",
        description="Service VLAN tag (outer VLAN). QinQ zones only.",
    )
    vlan_protocol: PropertyRef = PropertyRef(
        "vlan_protocol",
        description="Service VLAN protocol, 802.1q or 802.1ad. QinQ zones only.",
    )
    peers: PropertyRef = PropertyRef(
        "peers",
        description="IP addresses of the VXLAN peers. VXLAN zones only.",
    )
    vxlan_port: PropertyRef = PropertyRef(
        "vxlan_port",
        description="UDP port of the VXLAN tunnel. VXLAN zones only.",
    )
    fabric: PropertyRef = PropertyRef(
        "fabric",
        description="SDN fabric used as underlay instead of a peer list. VXLAN zones only.",
    )
    controller: PropertyRef = PropertyRef(
        "controller",
        description="ID of the primary controller. EVPN zones only.",
    )
    secondary_controllers: PropertyRef = PropertyRef(
        "secondary_controllers",
        description="IDs of the additional controllers that announce the zone routes. EVPN zones only.",
    )
    vrf_vxlan: PropertyRef = PropertyRef(
        "vrf_vxlan",
        description="VXLAN ID (VNI) of the zone VRF. EVPN zones only.",
    )
    mac: PropertyRef = PropertyRef(
        "mac",
        description="Anycast MAC address of the zone VNets. EVPN zones only.",
    )
    exitnodes: PropertyRef = PropertyRef(
        "exitnodes",
        description="Nodes that act as exit gateways from the EVPN network. EVPN zones only.",
    )
    exitnodes_primary: PropertyRef = PropertyRef(
        "exitnodes_primary",
        description="Exit node that traffic is forced through first. EVPN zones only.",
    )
    exitnodes_local_routing: PropertyRef = PropertyRef(
        "exitnodes_local_routing",
        description="Whether exit nodes get routes to reach EVPN guests. EVPN zones only.",
    )
    advertise_subnets: PropertyRef = PropertyRef(
        "advertise_subnets",
        description="Whether full subnets are announced instead of guest MAC/IP pairs. EVPN zones only.",
    )
    disable_arp_nd_suppression: PropertyRef = PropertyRef(
        "disable_arp_nd_suppression",
        description="Whether ARP and Neighbor Discovery suppression is disabled. EVPN zones only.",
    )
    rt_import: PropertyRef = PropertyRef(
        "rt_import",
        description="Route targets imported into the zone VRF through BGP. EVPN zones only.",
    )


@dataclass(frozen=True)
class ProxmoxSDNZoneToClusterRel(CartographyRelSchema):
    """The cluster contains the SDN zone."""

    target_node_label: str = "ProxmoxCluster"
    target_node_matcher: TargetNodeMatcher = _cluster_matcher()
    direction: LinkDirection = LinkDirection.INWARD
    rel_label: str = "RESOURCE"
    properties: ProxmoxSDNRelProperties = ProxmoxSDNRelProperties()


@dataclass(frozen=True)
class ProxmoxSDNZoneToControllerRel(CartographyRelSchema):
    """The SDN zone uses the controller, as primary or additional controller."""

    target_node_label: str = "ProxmoxSDNController"
    target_node_matcher: TargetNodeMatcher = make_target_node_matcher(
        {"id": PropertyRef("controller_ids", one_to_many=True)},
    )
    direction: LinkDirection = LinkDirection.OUTWARD
    rel_label: str = "USES_CONTROLLER"
    properties: ProxmoxSDNRelProperties = ProxmoxSDNRelProperties()


@dataclass(frozen=True)
class ProxmoxSDNZoneToIPAMRel(CartographyRelSchema):
    """The SDN zone manages guest IP addresses with the IPAM plugin."""

    target_node_label: str = "ProxmoxSDNIPAM"
    target_node_matcher: TargetNodeMatcher = make_target_node_matcher(
        {"id": PropertyRef("ipam_id")},
    )
    direction: LinkDirection = LinkDirection.OUTWARD
    rel_label: str = "USES_IPAM"
    properties: ProxmoxSDNRelProperties = ProxmoxSDNRelProperties()


@dataclass(frozen=True)
class ProxmoxSDNZoneToDNSRel(CartographyRelSchema):
    """The SDN zone registers guest names with the DNS plugin, forward or reverse."""

    target_node_label: str = "ProxmoxSDNDNS"
    target_node_matcher: TargetNodeMatcher = make_target_node_matcher(
        {"id": PropertyRef("dns_ids", one_to_many=True)},
    )
    direction: LinkDirection = LinkDirection.OUTWARD
    rel_label: str = "USES_DNS"
    properties: ProxmoxSDNRelProperties = ProxmoxSDNRelProperties()


@dataclass(frozen=True)
class ProxmoxSDNZoneToFabricRel(CartographyRelSchema):
    """The SDN zone uses the fabric as underlay network."""

    target_node_label: str = "ProxmoxSDNFabric"
    target_node_matcher: TargetNodeMatcher = make_target_node_matcher(
        {"id": PropertyRef("fabric_id")},
    )
    direction: LinkDirection = LinkDirection.OUTWARD
    rel_label: str = "USES_FABRIC"
    properties: ProxmoxSDNRelProperties = ProxmoxSDNRelProperties()


@dataclass(frozen=True)
class ProxmoxSDNZoneToBridgeRel(CartographyRelSchema):
    """The VLAN or QinQ zone carries its traffic over the node bridge with this name."""

    target_node_label: str = "ProxmoxNodeNetworkInterface"
    target_node_matcher: TargetNodeMatcher = make_target_node_matcher(
        {
            "name": PropertyRef("bridge"),
            "cluster_id": PropertyRef("CLUSTER_ID", set_in_kwargs=True),
        },
    )
    direction: LinkDirection = LinkDirection.OUTWARD
    rel_label: str = "USES_BRIDGE"
    properties: ProxmoxSDNRelProperties = ProxmoxSDNRelProperties()


@dataclass(frozen=True)
class ProxmoxSDNZoneSchema(CartographyNodeSchema):
    """A Proxmox VE SDN zone: a separated network area that holds VNets."""

    label: str = "ProxmoxSDNZone"
    properties: ProxmoxSDNZoneNodeProperties = ProxmoxSDNZoneNodeProperties()
    sub_resource_relationship: ProxmoxSDNZoneToClusterRel = ProxmoxSDNZoneToClusterRel()
    other_relationships: OtherRelationships = OtherRelationships(
        [
            ProxmoxSDNZoneToControllerRel(),
            ProxmoxSDNZoneToIPAMRel(),
            ProxmoxSDNZoneToDNSRel(),
            ProxmoxSDNZoneToFabricRel(),
            ProxmoxSDNZoneToBridgeRel(),
        ],
    )


# ============================================================================
# VNet
# ============================================================================


@dataclass(frozen=True)
class ProxmoxSDNVNetNodeProperties(CartographyNodeProperties):
    id: PropertyRef = PropertyRef(
        "id",
        description="VNet ID in the form cluster_id/vnet, such as prod/vnet1.",
    )
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)
    cluster_id: PropertyRef = PropertyRef(
        "cluster_id",
        description="ID of the cluster that defines the VNet.",
    )
    name: PropertyRef = PropertyRef(
        "name",
        extra_index=True,
        description="VNet name, also the name of the bridge guests attach to.",
    )
    zone: PropertyRef = PropertyRef(
        "zone",
        description="Name of the zone the VNet belongs to.",
    )
    alias: PropertyRef = PropertyRef(
        "alias",
        description="Descriptive alias of the VNet.",
    )
    tag: PropertyRef = PropertyRef(
        "tag",
        description="VLAN tag (VLAN and QinQ zones) or VXLAN VNI (VXLAN and EVPN zones).",
    )
    vlanaware: PropertyRef = PropertyRef(
        "vlanaware",
        description="Whether VLANs can pass through the VNet.",
    )
    isolate_ports: PropertyRef = PropertyRef(
        "isolate_ports",
        description="Whether guest ports on the VNet bridge are isolated from each other.",
    )
    firewall_enable: PropertyRef = PropertyRef(
        "firewall_enable",
        description="Whether the VNet firewall rules are enabled.",
    )
    firewall_policy_forward: PropertyRef = PropertyRef(
        "firewall_policy_forward",
        description="VNet firewall policy for forwarded traffic, ACCEPT or DROP.",
    )
    firewall_log_level_forward: PropertyRef = PropertyRef(
        "firewall_log_level_forward",
        description="VNet firewall log level for forwarded traffic.",
    )


@dataclass(frozen=True)
class ProxmoxSDNVNetToClusterRel(CartographyRelSchema):
    """The cluster contains the SDN VNet."""

    target_node_label: str = "ProxmoxCluster"
    target_node_matcher: TargetNodeMatcher = _cluster_matcher()
    direction: LinkDirection = LinkDirection.INWARD
    rel_label: str = "RESOURCE"
    properties: ProxmoxSDNRelProperties = ProxmoxSDNRelProperties()


@dataclass(frozen=True)
class ProxmoxSDNVNetToZoneRel(CartographyRelSchema):
    """The SDN zone contains the VNet."""

    target_node_label: str = "ProxmoxSDNZone"
    target_node_matcher: TargetNodeMatcher = make_target_node_matcher(
        {"id": PropertyRef("zone_id")},
    )
    direction: LinkDirection = LinkDirection.INWARD
    rel_label: str = "HAS_VNET"
    properties: ProxmoxSDNRelProperties = ProxmoxSDNRelProperties()


@dataclass(frozen=True)
class ProxmoxSDNVNetToNetworkInterfaceRel(CartographyRelSchema):
    """The guest network interface is attached to the VNet, its bridge being the VNet name."""

    target_node_label: str = "ProxmoxNetworkInterface"
    target_node_matcher: TargetNodeMatcher = make_target_node_matcher(
        {
            "bridge": PropertyRef("name"),
            "cluster_id": PropertyRef("CLUSTER_ID", set_in_kwargs=True),
        },
    )
    direction: LinkDirection = LinkDirection.INWARD
    rel_label: str = "CONNECTED_TO"
    properties: ProxmoxSDNRelProperties = ProxmoxSDNRelProperties()


@dataclass(frozen=True)
class ProxmoxSDNVNetSchema(CartographyNodeSchema):
    """A Proxmox VE SDN virtual network, available on each node as a bridge for guests."""

    label: str = "ProxmoxSDNVNet"
    properties: ProxmoxSDNVNetNodeProperties = ProxmoxSDNVNetNodeProperties()
    sub_resource_relationship: ProxmoxSDNVNetToClusterRel = ProxmoxSDNVNetToClusterRel()
    other_relationships: OtherRelationships = OtherRelationships(
        [ProxmoxSDNVNetToZoneRel(), ProxmoxSDNVNetToNetworkInterfaceRel()],
    )


# ============================================================================
# Subnet
# ============================================================================


@dataclass(frozen=True)
class ProxmoxSDNSubnetNodeProperties(CartographyNodeProperties):
    id: PropertyRef = PropertyRef(
        "id",
        description=(
            "Subnet ID in the form cluster_id/subnet, where subnet is the API "
            "identifier, such as prod/zone1-10.0.0.0-24."
        ),
    )
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)
    cluster_id: PropertyRef = PropertyRef(
        "cluster_id",
        description="ID of the cluster that defines the subnet.",
    )
    subnet: PropertyRef = PropertyRef(
        "subnet",
        description="Subnet identifier in the API, such as zone1-10.0.0.0-24.",
    )
    cidr: PropertyRef = PropertyRef(
        "cidr",
        extra_index=True,
        description="Network address of the subnet in CIDR notation.",
    )
    vnet: PropertyRef = PropertyRef(
        "vnet",
        description="Name of the VNet the subnet belongs to.",
    )
    zone: PropertyRef = PropertyRef(
        "zone",
        description="Name of the zone of the VNet.",
    )
    gateway: PropertyRef = PropertyRef(
        "gateway",
        description="Default gateway of the subnet, deployed on the VNet in layer 3 zones.",
    )
    snat: PropertyRef = PropertyRef(
        "snat",
        description="Whether source NAT is enabled for traffic leaving the subnet.",
    )
    dnszoneprefix: PropertyRef = PropertyRef(
        "dnszoneprefix",
        description="Prefix added to the DNS domain when registering guests.",
    )
    dhcp_ranges: PropertyRef = PropertyRef(
        "dhcp_ranges",
        description="DHCP ranges of the subnet, as returned by the API.",
    )
    dhcp_dns_server: PropertyRef = PropertyRef(
        "dhcp_dns_server",
        description="DNS server handed out by DHCP.",
    )


@dataclass(frozen=True)
class ProxmoxSDNSubnetToClusterRel(CartographyRelSchema):
    """The cluster contains the SDN subnet."""

    target_node_label: str = "ProxmoxCluster"
    target_node_matcher: TargetNodeMatcher = _cluster_matcher()
    direction: LinkDirection = LinkDirection.INWARD
    rel_label: str = "RESOURCE"
    properties: ProxmoxSDNRelProperties = ProxmoxSDNRelProperties()


@dataclass(frozen=True)
class ProxmoxSDNSubnetToVNetRel(CartographyRelSchema):
    """The SDN VNet contains the subnet."""

    target_node_label: str = "ProxmoxSDNVNet"
    target_node_matcher: TargetNodeMatcher = make_target_node_matcher(
        {"id": PropertyRef("vnet_id")},
    )
    direction: LinkDirection = LinkDirection.INWARD
    rel_label: str = "HAS_SUBNET"
    properties: ProxmoxSDNRelProperties = ProxmoxSDNRelProperties()


@dataclass(frozen=True)
class ProxmoxSDNSubnetSchema(CartographyNodeSchema):
    """An IP range inside a Proxmox VE SDN VNet."""

    label: str = "ProxmoxSDNSubnet"
    properties: ProxmoxSDNSubnetNodeProperties = ProxmoxSDNSubnetNodeProperties()
    sub_resource_relationship: ProxmoxSDNSubnetToClusterRel = (
        ProxmoxSDNSubnetToClusterRel()
    )
    other_relationships: OtherRelationships = OtherRelationships(
        [ProxmoxSDNSubnetToVNetRel()],
    )


# ============================================================================
# Controller
# ============================================================================


@dataclass(frozen=True)
class ProxmoxSDNControllerNodeProperties(CartographyNodeProperties):
    id: PropertyRef = PropertyRef(
        "id",
        description="Controller ID in the form cluster_id/controller.",
    )
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)
    cluster_id: PropertyRef = PropertyRef(
        "cluster_id",
        description="ID of the cluster that defines the controller.",
    )
    name: PropertyRef = PropertyRef(
        "name",
        extra_index=True,
        description="Controller name.",
    )
    type: PropertyRef = PropertyRef(
        "type",
        description="Controller type: evpn, bgp, isis, or faucet.",
    )
    asn: PropertyRef = PropertyRef(
        "asn",
        description="Local BGP autonomous system number. BGP and EVPN controllers only.",
    )
    peers: PropertyRef = PropertyRef(
        "peers",
        description="IP addresses of the BGP peers.",
    )
    node: PropertyRef = PropertyRef(
        "node",
        description="Node where the controller is active. BGP and IS-IS controllers only.",
    )
    nodes: PropertyRef = PropertyRef(
        "nodes",
        description="Nodes where the EVPN controller sets up peering sessions.",
    )
    fabric: PropertyRef = PropertyRef(
        "fabric",
        description="SDN fabric used as underlay. EVPN controllers only.",
    )
    bgp_mode: PropertyRef = PropertyRef(
        "bgp_mode",
        description="BGP session type of the EVPN controller: auto, external, or internal.",
    )
    ebgp: PropertyRef = PropertyRef(
        "ebgp",
        description="Whether eBGP is enabled. BGP controllers only.",
    )
    ebgp_multihop: PropertyRef = PropertyRef(
        "ebgp_multihop",
        description="Maximum number of hops to eBGP peers.",
    )
    bgp_multipath_as_relax: PropertyRef = PropertyRef(
        "bgp_multipath_as_relax",
        description="Whether paths with different AS paths of equal length are used for multipath.",
    )
    loopback: PropertyRef = PropertyRef(
        "loopback",
        description="Loopback or dummy interface that provides the router IP.",
    )
    peer_group_name: PropertyRef = PropertyRef(
        "peer_group_name",
        description="Name of the FRR peer group of the EVPN controller.",
    )
    route_map_in: PropertyRef = PropertyRef(
        "route_map_in",
        description="Route map applied to routes received from peers.",
    )
    route_map_out: PropertyRef = PropertyRef(
        "route_map_out",
        description="Route map applied to routes announced to peers.",
    )
    isis_domain: PropertyRef = PropertyRef(
        "isis_domain",
        description="IS-IS domain name. IS-IS controllers only.",
    )
    isis_ifaces: PropertyRef = PropertyRef(
        "isis_ifaces",
        description="Interfaces where IS-IS is active. IS-IS controllers only.",
    )
    isis_net: PropertyRef = PropertyRef(
        "isis_net",
        description="IS-IS network entity title of the node. IS-IS controllers only.",
    )


@dataclass(frozen=True)
class ProxmoxSDNControllerToClusterRel(CartographyRelSchema):
    """The cluster contains the SDN controller."""

    target_node_label: str = "ProxmoxCluster"
    target_node_matcher: TargetNodeMatcher = _cluster_matcher()
    direction: LinkDirection = LinkDirection.INWARD
    rel_label: str = "RESOURCE"
    properties: ProxmoxSDNRelProperties = ProxmoxSDNRelProperties()


@dataclass(frozen=True)
class ProxmoxSDNControllerToNodeRel(CartographyRelSchema):
    """The SDN controller is active on the cluster node."""

    target_node_label: str = "ProxmoxNode"
    target_node_matcher: TargetNodeMatcher = make_target_node_matcher(
        {"id": PropertyRef("node_ids", one_to_many=True)},
    )
    direction: LinkDirection = LinkDirection.OUTWARD
    rel_label: str = "RUNS_ON"
    properties: ProxmoxSDNRelProperties = ProxmoxSDNRelProperties()


@dataclass(frozen=True)
class ProxmoxSDNControllerToFabricRel(CartographyRelSchema):
    """The SDN controller uses the fabric as underlay network."""

    target_node_label: str = "ProxmoxSDNFabric"
    target_node_matcher: TargetNodeMatcher = make_target_node_matcher(
        {"id": PropertyRef("fabric_id")},
    )
    direction: LinkDirection = LinkDirection.OUTWARD
    rel_label: str = "USES_FABRIC"
    properties: ProxmoxSDNRelProperties = ProxmoxSDNRelProperties()


@dataclass(frozen=True)
class ProxmoxSDNControllerToRouteMapRel(CartographyRelSchema):
    """The SDN controller filters incoming or outgoing routes with the route map."""

    target_node_label: str = "ProxmoxSDNRouteMap"
    target_node_matcher: TargetNodeMatcher = make_target_node_matcher(
        {"id": PropertyRef("route_map_ids", one_to_many=True)},
    )
    direction: LinkDirection = LinkDirection.OUTWARD
    rel_label: str = "USES_ROUTE_MAP"
    properties: ProxmoxSDNRelProperties = ProxmoxSDNRelProperties()


@dataclass(frozen=True)
class ProxmoxSDNControllerSchema(CartographyNodeSchema):
    """A Proxmox VE SDN controller that runs the routing control plane through FRR."""

    label: str = "ProxmoxSDNController"
    properties: ProxmoxSDNControllerNodeProperties = (
        ProxmoxSDNControllerNodeProperties()
    )
    sub_resource_relationship: ProxmoxSDNControllerToClusterRel = (
        ProxmoxSDNControllerToClusterRel()
    )
    other_relationships: OtherRelationships = OtherRelationships(
        [
            ProxmoxSDNControllerToNodeRel(),
            ProxmoxSDNControllerToFabricRel(),
            ProxmoxSDNControllerToRouteMapRel(),
        ],
    )


# ============================================================================
# IPAM and DNS plugins
# ============================================================================


@dataclass(frozen=True)
class ProxmoxSDNIPAMNodeProperties(CartographyNodeProperties):
    id: PropertyRef = PropertyRef(
        "id",
        description="IPAM ID in the form cluster_id/ipam, such as prod/pve.",
    )
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)
    cluster_id: PropertyRef = PropertyRef(
        "cluster_id",
        description="ID of the cluster that defines the IPAM.",
    )
    name: PropertyRef = PropertyRef(
        "name",
        extra_index=True,
        description="IPAM name.",
    )
    type: PropertyRef = PropertyRef(
        "type",
        description="IPAM plugin type: pve, netbox, or phpipam.",
    )
    url: PropertyRef = PropertyRef(
        "url",
        description="API endpoint of an external IPAM.",
    )
    section: PropertyRef = PropertyRef(
        "section",
        description="phpIPAM section ID that holds the subnets.",
    )


@dataclass(frozen=True)
class ProxmoxSDNIPAMToClusterRel(CartographyRelSchema):
    """The cluster contains the SDN IPAM plugin."""

    target_node_label: str = "ProxmoxCluster"
    target_node_matcher: TargetNodeMatcher = _cluster_matcher()
    direction: LinkDirection = LinkDirection.INWARD
    rel_label: str = "RESOURCE"
    properties: ProxmoxSDNRelProperties = ProxmoxSDNRelProperties()


@dataclass(frozen=True)
class ProxmoxSDNIPAMSchema(CartographyNodeSchema):
    """An IP address management plugin that SDN zones use to allocate guest addresses."""

    label: str = "ProxmoxSDNIPAM"
    properties: ProxmoxSDNIPAMNodeProperties = ProxmoxSDNIPAMNodeProperties()
    sub_resource_relationship: ProxmoxSDNIPAMToClusterRel = ProxmoxSDNIPAMToClusterRel()


@dataclass(frozen=True)
class ProxmoxSDNIPAMEntryNodeProperties(CartographyNodeProperties):
    id: PropertyRef = PropertyRef(
        "id",
        description=(
            "Entry ID in the form cluster_id/ipam:zone:subnet:ip, such as "
            "prod/pve:zone1:10.0.0.0/24:10.0.0.5."
        ),
    )
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)
    cluster_id: PropertyRef = PropertyRef(
        "cluster_id",
        description="ID of the cluster that holds the entry.",
    )
    ipam: PropertyRef = PropertyRef(
        "ipam",
        description="Name of the IPAM that holds the entry.",
    )
    ip: PropertyRef = PropertyRef(
        "ip",
        extra_index=True,
        description="Allocated IP address.",
    )
    zone: PropertyRef = PropertyRef(
        "zone",
        description="Name of the zone of the subnet.",
    )
    subnet: PropertyRef = PropertyRef(
        "subnet",
        description="Subnet of the address in CIDR notation.",
    )
    vnet: PropertyRef = PropertyRef(
        "vnet",
        description="Name of the VNet of the subnet.",
    )
    mac: PropertyRef = PropertyRef(
        "mac",
        description="MAC address of the guest interface the address is leased to.",
    )
    hostname: PropertyRef = PropertyRef(
        "hostname",
        description="Hostname registered for the address.",
    )
    vmid: PropertyRef = PropertyRef(
        "vmid",
        description="Numeric ID of the guest that holds the address.",
    )
    gateway: PropertyRef = PropertyRef(
        "gateway",
        description="Whether the address is the subnet gateway.",
    )


@dataclass(frozen=True)
class ProxmoxSDNIPAMEntryToClusterRel(CartographyRelSchema):
    """The cluster contains the IPAM entry."""

    target_node_label: str = "ProxmoxCluster"
    target_node_matcher: TargetNodeMatcher = _cluster_matcher()
    direction: LinkDirection = LinkDirection.INWARD
    rel_label: str = "RESOURCE"
    properties: ProxmoxSDNRelProperties = ProxmoxSDNRelProperties()


@dataclass(frozen=True)
class ProxmoxSDNIPAMEntryToIPAMRel(CartographyRelSchema):
    """The IPAM holds the address entry."""

    target_node_label: str = "ProxmoxSDNIPAM"
    target_node_matcher: TargetNodeMatcher = make_target_node_matcher(
        {"id": PropertyRef("ipam_id")},
    )
    direction: LinkDirection = LinkDirection.INWARD
    rel_label: str = "HAS_ENTRY"
    properties: ProxmoxSDNRelProperties = ProxmoxSDNRelProperties()


@dataclass(frozen=True)
class ProxmoxSDNIPAMEntryToSubnetRel(CartographyRelSchema):
    """The SDN subnet has the IPAM address entry."""

    target_node_label: str = "ProxmoxSDNSubnet"
    target_node_matcher: TargetNodeMatcher = make_target_node_matcher(
        {
            "cidr": PropertyRef("subnet"),
            "zone": PropertyRef("zone"),
            "cluster_id": PropertyRef("CLUSTER_ID", set_in_kwargs=True),
        },
    )
    direction: LinkDirection = LinkDirection.INWARD
    rel_label: str = "HAS_IPAM_ENTRY"
    properties: ProxmoxSDNRelProperties = ProxmoxSDNRelProperties()


@dataclass(frozen=True)
class ProxmoxSDNIPAMEntryToVMRel(CartographyRelSchema):
    """The IPAM address is allocated to the VM or container of the same cluster."""

    target_node_label: str = "ProxmoxVM"
    target_node_matcher: TargetNodeMatcher = make_target_node_matcher(
        {
            "vmid": PropertyRef("vmid"),
            "cluster_id": PropertyRef("CLUSTER_ID", set_in_kwargs=True),
        },
    )
    direction: LinkDirection = LinkDirection.OUTWARD
    rel_label: str = "ALLOCATED_TO"
    properties: ProxmoxSDNRelProperties = ProxmoxSDNRelProperties()


@dataclass(frozen=True)
class ProxmoxSDNIPAMEntrySchema(CartographyNodeSchema):
    """An IP address recorded in the built-in Proxmox VE IPAM, for a guest or a subnet gateway."""

    label: str = "ProxmoxSDNIPAMEntry"
    properties: ProxmoxSDNIPAMEntryNodeProperties = ProxmoxSDNIPAMEntryNodeProperties()
    sub_resource_relationship: ProxmoxSDNIPAMEntryToClusterRel = (
        ProxmoxSDNIPAMEntryToClusterRel()
    )
    other_relationships: OtherRelationships = OtherRelationships(
        [
            ProxmoxSDNIPAMEntryToIPAMRel(),
            ProxmoxSDNIPAMEntryToSubnetRel(),
            ProxmoxSDNIPAMEntryToVMRel(),
        ],
    )


@dataclass(frozen=True)
class ProxmoxSDNDNSNodeProperties(CartographyNodeProperties):
    id: PropertyRef = PropertyRef(
        "id",
        description="DNS plugin ID in the form cluster_id/dns.",
    )
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)
    cluster_id: PropertyRef = PropertyRef(
        "cluster_id",
        description="ID of the cluster that defines the DNS plugin.",
    )
    name: PropertyRef = PropertyRef(
        "name",
        extra_index=True,
        description="DNS plugin name.",
    )
    type: PropertyRef = PropertyRef(
        "type",
        description="DNS plugin type, such as powerdns.",
    )
    url: PropertyRef = PropertyRef(
        "url",
        description="API endpoint of the DNS server.",
    )
    ttl: PropertyRef = PropertyRef(
        "ttl",
        description="TTL of the records the plugin registers.",
    )


@dataclass(frozen=True)
class ProxmoxSDNDNSToClusterRel(CartographyRelSchema):
    """The cluster contains the SDN DNS plugin."""

    target_node_label: str = "ProxmoxCluster"
    target_node_matcher: TargetNodeMatcher = _cluster_matcher()
    direction: LinkDirection = LinkDirection.INWARD
    rel_label: str = "RESOURCE"
    properties: ProxmoxSDNRelProperties = ProxmoxSDNRelProperties()


@dataclass(frozen=True)
class ProxmoxSDNDNSSchema(CartographyNodeSchema):
    """A DNS server integration that SDN zones use to register guest hostnames."""

    label: str = "ProxmoxSDNDNS"
    properties: ProxmoxSDNDNSNodeProperties = ProxmoxSDNDNSNodeProperties()
    sub_resource_relationship: ProxmoxSDNDNSToClusterRel = ProxmoxSDNDNSToClusterRel()


# ============================================================================
# Prefix lists and route maps (Proxmox VE 9)
# ============================================================================


@dataclass(frozen=True)
class ProxmoxSDNPrefixListNodeProperties(CartographyNodeProperties):
    id: PropertyRef = PropertyRef(
        "id",
        description="Prefix list ID in the form cluster_id/name.",
    )
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)
    cluster_id: PropertyRef = PropertyRef(
        "cluster_id",
        description="ID of the cluster that defines the prefix list.",
    )
    name: PropertyRef = PropertyRef(
        "name",
        extra_index=True,
        description="Prefix list name.",
    )
    entries: PropertyRef = PropertyRef(
        "entries",
        description=(
            "Entries in evaluation order, each as 'seq <n> <permit|deny> <prefix>' "
            "with optional 'ge <n>' and 'le <n>'."
        ),
    )


@dataclass(frozen=True)
class ProxmoxSDNPrefixListToClusterRel(CartographyRelSchema):
    """The cluster contains the SDN prefix list."""

    target_node_label: str = "ProxmoxCluster"
    target_node_matcher: TargetNodeMatcher = _cluster_matcher()
    direction: LinkDirection = LinkDirection.INWARD
    rel_label: str = "RESOURCE"
    properties: ProxmoxSDNRelProperties = ProxmoxSDNRelProperties()


@dataclass(frozen=True)
class ProxmoxSDNPrefixListSchema(CartographyNodeSchema):
    """An ordered list of permit and deny rules on route destinations, used to filter routes."""

    label: str = "ProxmoxSDNPrefixList"
    properties: ProxmoxSDNPrefixListNodeProperties = (
        ProxmoxSDNPrefixListNodeProperties()
    )
    sub_resource_relationship: ProxmoxSDNPrefixListToClusterRel = (
        ProxmoxSDNPrefixListToClusterRel()
    )


@dataclass(frozen=True)
class ProxmoxSDNRouteMapNodeProperties(CartographyNodeProperties):
    id: PropertyRef = PropertyRef(
        "id",
        description="Route map ID in the form cluster_id/name.",
    )
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)
    cluster_id: PropertyRef = PropertyRef(
        "cluster_id",
        description="ID of the cluster that defines the route map.",
    )
    name: PropertyRef = PropertyRef(
        "name",
        extra_index=True,
        description="Route map name.",
    )


@dataclass(frozen=True)
class ProxmoxSDNRouteMapToClusterRel(CartographyRelSchema):
    """The cluster contains the SDN route map."""

    target_node_label: str = "ProxmoxCluster"
    target_node_matcher: TargetNodeMatcher = _cluster_matcher()
    direction: LinkDirection = LinkDirection.INWARD
    rel_label: str = "RESOURCE"
    properties: ProxmoxSDNRelProperties = ProxmoxSDNRelProperties()


@dataclass(frozen=True)
class ProxmoxSDNRouteMapSchema(CartographyNodeSchema):
    """An ordered routing policy that matches routes and permits, denies, or modifies them."""

    label: str = "ProxmoxSDNRouteMap"
    properties: ProxmoxSDNRouteMapNodeProperties = ProxmoxSDNRouteMapNodeProperties()
    sub_resource_relationship: ProxmoxSDNRouteMapToClusterRel = (
        ProxmoxSDNRouteMapToClusterRel()
    )


@dataclass(frozen=True)
class ProxmoxSDNRouteMapEntryNodeProperties(CartographyNodeProperties):
    id: PropertyRef = PropertyRef(
        "id",
        description="Entry ID in the form cluster_id/route_map:order, such as prod/bgp-out:10.",
    )
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)
    cluster_id: PropertyRef = PropertyRef(
        "cluster_id",
        description="ID of the cluster that defines the entry.",
    )
    route_map: PropertyRef = PropertyRef(
        "route_map",
        description="Name of the route map the entry belongs to.",
    )
    order: PropertyRef = PropertyRef(
        "order",
        description="Position of the entry in the route map evaluation order.",
    )
    action: PropertyRef = PropertyRef(
        "action",
        description="Action when the entry matches: permit or deny.",
    )
    match: PropertyRef = PropertyRef(
        "match",
        description="Match conditions, each as key=value, such as ip-address-prefix-list=internal.",
    )
    set: PropertyRef = PropertyRef(
        "set",
        description="Route attributes set on a match, each as key=value, such as local-preference=50.",
    )
    exit_action: PropertyRef = PropertyRef(
        "exit_action",
        description="How evaluation continues after a match, such as on-match-next.",
    )
    call: PropertyRef = PropertyRef(
        "call",
        description="Route map called at the end of the entry processing.",
    )


@dataclass(frozen=True)
class ProxmoxSDNRouteMapEntryToClusterRel(CartographyRelSchema):
    """The cluster contains the route map entry."""

    target_node_label: str = "ProxmoxCluster"
    target_node_matcher: TargetNodeMatcher = _cluster_matcher()
    direction: LinkDirection = LinkDirection.INWARD
    rel_label: str = "RESOURCE"
    properties: ProxmoxSDNRelProperties = ProxmoxSDNRelProperties()


@dataclass(frozen=True)
class ProxmoxSDNRouteMapEntryToRouteMapRel(CartographyRelSchema):
    """The route map contains the entry."""

    target_node_label: str = "ProxmoxSDNRouteMap"
    target_node_matcher: TargetNodeMatcher = make_target_node_matcher(
        {"id": PropertyRef("route_map_id")},
    )
    direction: LinkDirection = LinkDirection.INWARD
    rel_label: str = "HAS_ENTRY"
    properties: ProxmoxSDNRelProperties = ProxmoxSDNRelProperties()


@dataclass(frozen=True)
class ProxmoxSDNRouteMapEntryToPrefixListRel(CartographyRelSchema):
    """The route map entry matches routes against the prefix list."""

    target_node_label: str = "ProxmoxSDNPrefixList"
    target_node_matcher: TargetNodeMatcher = make_target_node_matcher(
        {"id": PropertyRef("prefix_list_ids", one_to_many=True)},
    )
    direction: LinkDirection = LinkDirection.OUTWARD
    rel_label: str = "MATCHES_PREFIX_LIST"
    properties: ProxmoxSDNRelProperties = ProxmoxSDNRelProperties()


@dataclass(frozen=True)
class ProxmoxSDNRouteMapEntryToCalledRouteMapRel(CartographyRelSchema):
    """The route map entry calls another route map."""

    target_node_label: str = "ProxmoxSDNRouteMap"
    target_node_matcher: TargetNodeMatcher = make_target_node_matcher(
        {"id": PropertyRef("call_id")},
    )
    direction: LinkDirection = LinkDirection.OUTWARD
    rel_label: str = "CALLS"
    properties: ProxmoxSDNRelProperties = ProxmoxSDNRelProperties()


@dataclass(frozen=True)
class ProxmoxSDNRouteMapEntrySchema(CartographyNodeSchema):
    """One ordered entry of an SDN route map, with its match conditions and actions."""

    label: str = "ProxmoxSDNRouteMapEntry"
    properties: ProxmoxSDNRouteMapEntryNodeProperties = (
        ProxmoxSDNRouteMapEntryNodeProperties()
    )
    sub_resource_relationship: ProxmoxSDNRouteMapEntryToClusterRel = (
        ProxmoxSDNRouteMapEntryToClusterRel()
    )
    other_relationships: OtherRelationships = OtherRelationships(
        [
            ProxmoxSDNRouteMapEntryToRouteMapRel(),
            ProxmoxSDNRouteMapEntryToPrefixListRel(),
            ProxmoxSDNRouteMapEntryToCalledRouteMapRel(),
        ],
    )


# ============================================================================
# Fabrics (Proxmox VE 9)
# ============================================================================


@dataclass(frozen=True)
class ProxmoxSDNFabricNodeProperties(CartographyNodeProperties):
    id: PropertyRef = PropertyRef(
        "id",
        description="Fabric ID in the form cluster_id/fabric, such as prod/fab1.",
    )
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)
    cluster_id: PropertyRef = PropertyRef(
        "cluster_id",
        description="ID of the cluster that defines the fabric.",
    )
    name: PropertyRef = PropertyRef(
        "name",
        extra_index=True,
        description="Fabric name.",
    )
    protocol: PropertyRef = PropertyRef(
        "protocol",
        description="Fabric protocol: openfabric, ospf, wireguard, or bgp.",
    )
    ip_prefix: PropertyRef = PropertyRef(
        "ip_prefix",
        description="IPv4 prefix that contains the router IDs of the fabric nodes.",
    )
    ip6_prefix: PropertyRef = PropertyRef(
        "ip6_prefix",
        description="IPv6 prefix that contains the router IDs of the fabric nodes.",
    )
    area: PropertyRef = PropertyRef(
        "area",
        description="OSPF area. OSPF fabrics only.",
    )
    hello_interval: PropertyRef = PropertyRef(
        "hello_interval",
        description="Seconds between hello packets. OpenFabric fabrics only.",
    )
    csnp_interval: PropertyRef = PropertyRef(
        "csnp_interval",
        description="Seconds between routing database synchronizations. OpenFabric fabrics only.",
    )
    persistent_keepalive: PropertyRef = PropertyRef(
        "persistent_keepalive",
        description="Seconds between WireGuard keepalive packets. WireGuard fabrics only.",
    )
    route_filter: PropertyRef = PropertyRef(
        "route_filter",
        description="Prefix list that filters the routes installed into the kernel.",
    )
    redistribute: PropertyRef = PropertyRef(
        "redistribute",
        description="Route sources redistributed into the fabric, each as source or source:route_map.",
    )


@dataclass(frozen=True)
class ProxmoxSDNFabricToClusterRel(CartographyRelSchema):
    """The cluster contains the SDN fabric."""

    target_node_label: str = "ProxmoxCluster"
    target_node_matcher: TargetNodeMatcher = _cluster_matcher()
    direction: LinkDirection = LinkDirection.INWARD
    rel_label: str = "RESOURCE"
    properties: ProxmoxSDNRelProperties = ProxmoxSDNRelProperties()


@dataclass(frozen=True)
class ProxmoxSDNFabricToPrefixListRel(CartographyRelSchema):
    """The fabric filters installed routes with the prefix list."""

    target_node_label: str = "ProxmoxSDNPrefixList"
    target_node_matcher: TargetNodeMatcher = make_target_node_matcher(
        {"id": PropertyRef("route_filter_id")},
    )
    direction: LinkDirection = LinkDirection.OUTWARD
    rel_label: str = "USES_PREFIX_LIST"
    properties: ProxmoxSDNRelProperties = ProxmoxSDNRelProperties()


@dataclass(frozen=True)
class ProxmoxSDNFabricToRouteMapRel(CartographyRelSchema):
    """The fabric filters or transforms redistributed routes with the route map."""

    target_node_label: str = "ProxmoxSDNRouteMap"
    target_node_matcher: TargetNodeMatcher = make_target_node_matcher(
        {"id": PropertyRef("route_map_ids", one_to_many=True)},
    )
    direction: LinkDirection = LinkDirection.OUTWARD
    rel_label: str = "USES_ROUTE_MAP"
    properties: ProxmoxSDNRelProperties = ProxmoxSDNRelProperties()


@dataclass(frozen=True)
class ProxmoxSDNFabricSchema(CartographyNodeSchema):
    """A Proxmox VE SDN fabric: routed underlay network between cluster nodes."""

    label: str = "ProxmoxSDNFabric"
    properties: ProxmoxSDNFabricNodeProperties = ProxmoxSDNFabricNodeProperties()
    sub_resource_relationship: ProxmoxSDNFabricToClusterRel = (
        ProxmoxSDNFabricToClusterRel()
    )
    other_relationships: OtherRelationships = OtherRelationships(
        [ProxmoxSDNFabricToPrefixListRel(), ProxmoxSDNFabricToRouteMapRel()],
    )


@dataclass(frozen=True)
class ProxmoxSDNFabricNodeNodeProperties(CartographyNodeProperties):
    id: PropertyRef = PropertyRef(
        "id",
        description="Fabric node ID in the form cluster_id/fabric:node, such as prod/fab1:pve1.",
    )
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)
    cluster_id: PropertyRef = PropertyRef(
        "cluster_id",
        description="ID of the cluster that defines the fabric.",
    )
    fabric: PropertyRef = PropertyRef(
        "fabric",
        description="Name of the fabric.",
    )
    node_name: PropertyRef = PropertyRef(
        "node_name",
        extra_index=True,
        description="Cluster node name, or the name of an external WireGuard peer.",
    )
    protocol: PropertyRef = PropertyRef(
        "protocol",
        description="Fabric protocol: openfabric, ospf, wireguard, or bgp.",
    )
    ip: PropertyRef = PropertyRef(
        "ip",
        description="IPv4 router ID of the node in the fabric.",
    )
    ip6: PropertyRef = PropertyRef(
        "ip6",
        description="IPv6 router ID of the node in the fabric.",
    )
    interfaces: PropertyRef = PropertyRef(
        "interfaces",
        description="Names of the node interfaces that peer with the other fabric nodes.",
    )
    role: PropertyRef = PropertyRef(
        "role",
        description="WireGuard node role: internal for cluster nodes, external otherwise.",
    )
    endpoint: PropertyRef = PropertyRef(
        "endpoint",
        description="Address that peers use to connect to the node. WireGuard fabrics only.",
    )
    allowed_ips: PropertyRef = PropertyRef(
        "allowed_ips",
        description="Networks routed through the node. WireGuard fabrics only.",
    )
    public_key: PropertyRef = PropertyRef(
        "public_key",
        description="WireGuard public key of an external node.",
    )
    neighbors: PropertyRef = PropertyRef(
        "neighbors",
        description="IPs or hostnames of the neighbors the node currently sees, as reported by FRR.",
    )
    routes: PropertyRef = PropertyRef(
        "routes",
        description="Routes the node learned through the fabric, each as 'cidr via nexthop[,nexthop]'.",
    )


@dataclass(frozen=True)
class ProxmoxSDNFabricNodeToClusterRel(CartographyRelSchema):
    """The cluster contains the fabric node."""

    target_node_label: str = "ProxmoxCluster"
    target_node_matcher: TargetNodeMatcher = _cluster_matcher()
    direction: LinkDirection = LinkDirection.INWARD
    rel_label: str = "RESOURCE"
    properties: ProxmoxSDNRelProperties = ProxmoxSDNRelProperties()


@dataclass(frozen=True)
class ProxmoxSDNFabricNodeToFabricRel(CartographyRelSchema):
    """The fabric has the node as a member."""

    target_node_label: str = "ProxmoxSDNFabric"
    target_node_matcher: TargetNodeMatcher = make_target_node_matcher(
        {"id": PropertyRef("fabric_id")},
    )
    direction: LinkDirection = LinkDirection.INWARD
    rel_label: str = "HAS_NODE"
    properties: ProxmoxSDNRelProperties = ProxmoxSDNRelProperties()


@dataclass(frozen=True)
class ProxmoxSDNFabricNodeToProxmoxNodeRel(CartographyRelSchema):
    """The fabric node is the cluster node's membership in the fabric."""

    target_node_label: str = "ProxmoxNode"
    target_node_matcher: TargetNodeMatcher = make_target_node_matcher(
        {"id": PropertyRef("proxmox_node_id")},
    )
    direction: LinkDirection = LinkDirection.OUTWARD
    rel_label: str = "RUNS_ON"
    properties: ProxmoxSDNRelProperties = ProxmoxSDNRelProperties()


@dataclass(frozen=True)
class ProxmoxSDNFabricNodeSchema(CartographyNodeSchema):
    """A member of an SDN fabric: a cluster node, or an external WireGuard peer."""

    label: str = "ProxmoxSDNFabricNode"
    properties: ProxmoxSDNFabricNodeNodeProperties = (
        ProxmoxSDNFabricNodeNodeProperties()
    )
    sub_resource_relationship: ProxmoxSDNFabricNodeToClusterRel = (
        ProxmoxSDNFabricNodeToClusterRel()
    )
    other_relationships: OtherRelationships = OtherRelationships(
        [ProxmoxSDNFabricNodeToFabricRel(), ProxmoxSDNFabricNodeToProxmoxNodeRel()],
    )


# ============================================================================
# Per-node VNet bridges and ports (Proxmox VE 9)
# ============================================================================


@dataclass(frozen=True)
class ProxmoxSDNBridgeNodeProperties(CartographyNodeProperties):
    id: PropertyRef = PropertyRef(
        "id",
        description="Bridge ID in the form cluster_id/node:bridge, such as prod/pve1:vnet1.",
    )
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)
    cluster_id: PropertyRef = PropertyRef(
        "cluster_id",
        description="ID of the cluster the node belongs to.",
    )
    name: PropertyRef = PropertyRef(
        "name",
        extra_index=True,
        description="Bridge name, the name of the VNet it implements.",
    )
    node_name: PropertyRef = PropertyRef(
        "node_name",
        description="Name of the node that hosts the bridge.",
    )
    zone: PropertyRef = PropertyRef(
        "zone",
        description="Name of the SDN zone of the bridge.",
    )
    vlan_filtering: PropertyRef = PropertyRef(
        "vlan_filtering",
        description="Whether VLAN filtering is enabled on the bridge (VLAN-aware).",
    )
    ports: PropertyRef = PropertyRef(
        "ports",
        description="Names of the bridge ports.",
    )


@dataclass(frozen=True)
class ProxmoxSDNBridgeToClusterRel(CartographyRelSchema):
    """The cluster contains the SDN bridge."""

    target_node_label: str = "ProxmoxCluster"
    target_node_matcher: TargetNodeMatcher = _cluster_matcher()
    direction: LinkDirection = LinkDirection.INWARD
    rel_label: str = "RESOURCE"
    properties: ProxmoxSDNRelProperties = ProxmoxSDNRelProperties()


@dataclass(frozen=True)
class ProxmoxSDNBridgeToNodeRel(CartographyRelSchema):
    """The cluster node hosts the SDN bridge."""

    target_node_label: str = "ProxmoxNode"
    target_node_matcher: TargetNodeMatcher = make_target_node_matcher(
        {"id": PropertyRef("node_id")},
    )
    direction: LinkDirection = LinkDirection.INWARD
    rel_label: str = "HAS_SDN_BRIDGE"
    properties: ProxmoxSDNRelProperties = ProxmoxSDNRelProperties()


@dataclass(frozen=True)
class ProxmoxSDNBridgeToVNetRel(CartographyRelSchema):
    """The bridge implements the VNet on its node."""

    target_node_label: str = "ProxmoxSDNVNet"
    target_node_matcher: TargetNodeMatcher = make_target_node_matcher(
        {"id": PropertyRef("vnet_id")},
    )
    direction: LinkDirection = LinkDirection.OUTWARD
    rel_label: str = "IMPLEMENTS"
    properties: ProxmoxSDNRelProperties = ProxmoxSDNRelProperties()


@dataclass(frozen=True)
class ProxmoxSDNBridgeSchema(CartographyNodeSchema):
    """The Linux bridge that implements an SDN VNet on one cluster node."""

    label: str = "ProxmoxSDNBridge"
    properties: ProxmoxSDNBridgeNodeProperties = ProxmoxSDNBridgeNodeProperties()
    sub_resource_relationship: ProxmoxSDNBridgeToClusterRel = (
        ProxmoxSDNBridgeToClusterRel()
    )
    other_relationships: OtherRelationships = OtherRelationships(
        [ProxmoxSDNBridgeToNodeRel(), ProxmoxSDNBridgeToVNetRel()],
    )


@dataclass(frozen=True)
class ProxmoxSDNBridgePortNodeProperties(CartographyNodeProperties):
    id: PropertyRef = PropertyRef(
        "id",
        description="Port ID in the form cluster_id/node:bridge:port, such as prod/pve1:vnet1:tap100i0.",
    )
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)
    cluster_id: PropertyRef = PropertyRef(
        "cluster_id",
        description="ID of the cluster the node belongs to.",
    )
    name: PropertyRef = PropertyRef(
        "name",
        extra_index=True,
        description="Port name, such as tap100i0.",
    )
    bridge: PropertyRef = PropertyRef(
        "bridge",
        description="Name of the bridge the port is a member of.",
    )
    node_name: PropertyRef = PropertyRef(
        "node_name",
        description="Name of the node that hosts the bridge.",
    )
    vmid: PropertyRef = PropertyRef(
        "vmid",
        description="Numeric ID of the guest the port belongs to.",
    )
    index: PropertyRef = PropertyRef(
        "index",
        description="Index of the guest network device, 0 for net0.",
    )
    primary_vlan: PropertyRef = PropertyRef(
        "primary_vlan",
        description="Primary VLAN (PVID) of the port. VLAN-aware bridges only.",
    )
    vlans: PropertyRef = PropertyRef(
        "vlans",
        description="Additional VLANs and VLAN ranges allowed on the port. VLAN-aware bridges only.",
    )


@dataclass(frozen=True)
class ProxmoxSDNBridgePortToClusterRel(CartographyRelSchema):
    """The cluster contains the SDN bridge port."""

    target_node_label: str = "ProxmoxCluster"
    target_node_matcher: TargetNodeMatcher = _cluster_matcher()
    direction: LinkDirection = LinkDirection.INWARD
    rel_label: str = "RESOURCE"
    properties: ProxmoxSDNRelProperties = ProxmoxSDNRelProperties()


@dataclass(frozen=True)
class ProxmoxSDNBridgePortToBridgeRel(CartographyRelSchema):
    """The SDN bridge has the port as a member."""

    target_node_label: str = "ProxmoxSDNBridge"
    target_node_matcher: TargetNodeMatcher = make_target_node_matcher(
        {"id": PropertyRef("bridge_id")},
    )
    direction: LinkDirection = LinkDirection.INWARD
    rel_label: str = "HAS_PORT"
    properties: ProxmoxSDNRelProperties = ProxmoxSDNRelProperties()


@dataclass(frozen=True)
class ProxmoxSDNBridgePortToNetworkInterfaceRel(CartographyRelSchema):
    """The guest network interface is plugged into the bridge port."""

    target_node_label: str = "ProxmoxNetworkInterface"
    target_node_matcher: TargetNodeMatcher = make_target_node_matcher(
        {
            "vmid": PropertyRef("vmid"),
            "net_id": PropertyRef("net_id"),
            "cluster_id": PropertyRef("CLUSTER_ID", set_in_kwargs=True),
        },
    )
    direction: LinkDirection = LinkDirection.INWARD
    rel_label: str = "PLUGGED_INTO"
    properties: ProxmoxSDNRelProperties = ProxmoxSDNRelProperties()


@dataclass(frozen=True)
class ProxmoxSDNBridgePortSchema(CartographyNodeSchema):
    """A port of an SDN bridge on a node: a guest interface or an uplink."""

    label: str = "ProxmoxSDNBridgePort"
    properties: ProxmoxSDNBridgePortNodeProperties = (
        ProxmoxSDNBridgePortNodeProperties()
    )
    sub_resource_relationship: ProxmoxSDNBridgePortToClusterRel = (
        ProxmoxSDNBridgePortToClusterRel()
    )
    other_relationships: OtherRelationships = OtherRelationships(
        [
            ProxmoxSDNBridgePortToBridgeRel(),
            ProxmoxSDNBridgePortToNetworkInterfaceRel(),
        ],
    )


# ============================================================================
# MatchLinks: per-node state that carries properties on the relationship
# ============================================================================


@dataclass(frozen=True)
class ProxmoxSDNMatchLinkRelProperties(CartographyRelProperties):
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)
    _sub_resource_label: PropertyRef = PropertyRef(
        "_sub_resource_label",
        set_in_kwargs=True,
    )
    _sub_resource_id: PropertyRef = PropertyRef("_sub_resource_id", set_in_kwargs=True)


@dataclass(frozen=True)
class ProxmoxSDNZoneDeployedOnRelProperties(ProxmoxSDNMatchLinkRelProperties):
    status: PropertyRef = PropertyRef("status")
    ip_vrf: PropertyRef = PropertyRef("ip_vrf")


@dataclass(frozen=True)
class ProxmoxSDNZoneDeployedOnNodeMatchLink(CartographyRelSchema):
    """The SDN zone is deployed on the cluster node, with the status the node reports."""

    source_node_label: str = "ProxmoxSDNZone"
    source_node_matcher: SourceNodeMatcher = make_source_node_matcher(
        {"id": PropertyRef("zone_id")},
    )
    target_node_label: str = "ProxmoxNode"
    target_node_matcher: TargetNodeMatcher = make_target_node_matcher(
        {"id": PropertyRef("node_id")},
    )
    direction: LinkDirection = LinkDirection.OUTWARD
    rel_label: str = "DEPLOYED_ON"
    properties: ProxmoxSDNZoneDeployedOnRelProperties = (
        ProxmoxSDNZoneDeployedOnRelProperties()
    )


@dataclass(frozen=True)
class ProxmoxSDNVNetDeployedOnRelProperties(ProxmoxSDNMatchLinkRelProperties):
    status: PropertyRef = PropertyRef("status")
    statusmsg: PropertyRef = PropertyRef("statusmsg")
    mac_vrf: PropertyRef = PropertyRef("mac_vrf")


@dataclass(frozen=True)
class ProxmoxSDNVNetDeployedOnNodeMatchLink(CartographyRelSchema):
    """The SDN VNet is deployed on the cluster node, with the status the node reports."""

    source_node_label: str = "ProxmoxSDNVNet"
    source_node_matcher: SourceNodeMatcher = make_source_node_matcher(
        {"id": PropertyRef("vnet_id")},
    )
    target_node_label: str = "ProxmoxNode"
    target_node_matcher: TargetNodeMatcher = make_target_node_matcher(
        {"id": PropertyRef("node_id")},
    )
    direction: LinkDirection = LinkDirection.OUTWARD
    rel_label: str = "DEPLOYED_ON"
    properties: ProxmoxSDNVNetDeployedOnRelProperties = (
        ProxmoxSDNVNetDeployedOnRelProperties()
    )


@dataclass(frozen=True)
class ProxmoxSDNFabricNeighborRelProperties(ProxmoxSDNMatchLinkRelProperties):
    status: PropertyRef = PropertyRef("status")
    uptime: PropertyRef = PropertyRef("uptime")


@dataclass(frozen=True)
class ProxmoxSDNFabricNeighborMatchLink(CartographyRelSchema):
    """The fabric node sees the other fabric node as a routing neighbor."""

    source_node_label: str = "ProxmoxSDNFabricNode"
    source_node_matcher: SourceNodeMatcher = make_source_node_matcher(
        {"id": PropertyRef("fabric_node_id")},
    )
    target_node_label: str = "ProxmoxSDNFabricNode"
    target_node_matcher: TargetNodeMatcher = make_target_node_matcher(
        {"id": PropertyRef("neighbor_id")},
    )
    direction: LinkDirection = LinkDirection.OUTWARD
    rel_label: str = "FABRIC_NEIGHBOR"
    properties: ProxmoxSDNFabricNeighborRelProperties = (
        ProxmoxSDNFabricNeighborRelProperties()
    )


@dataclass(frozen=True)
class ProxmoxSDNFabricInterfaceRelProperties(ProxmoxSDNMatchLinkRelProperties):
    ip: PropertyRef = PropertyRef("ip")
    ip6: PropertyRef = PropertyRef("ip6")
    state: PropertyRef = PropertyRef("state")
    type: PropertyRef = PropertyRef("type")


@dataclass(frozen=True)
class ProxmoxSDNFabricInterfaceMatchLink(CartographyRelSchema):
    """The fabric node peers with the other fabric nodes through the node network interface."""

    source_node_label: str = "ProxmoxSDNFabricNode"
    source_node_matcher: SourceNodeMatcher = make_source_node_matcher(
        {"id": PropertyRef("fabric_node_id")},
    )
    target_node_label: str = "ProxmoxNodeNetworkInterface"
    target_node_matcher: TargetNodeMatcher = make_target_node_matcher(
        {"id": PropertyRef("interface_id")},
    )
    direction: LinkDirection = LinkDirection.OUTWARD
    rel_label: str = "USES_INTERFACE"
    properties: ProxmoxSDNFabricInterfaceRelProperties = (
        ProxmoxSDNFabricInterfaceRelProperties()
    )
