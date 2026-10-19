from dataclasses import dataclass

from cartography.models.core.common import PropertyRef
from cartography.models.core.nodes import CartographyNodeProperties
from cartography.models.core.nodes import CartographyNodeSchema
from cartography.models.core.relationships import CartographyRelProperties
from cartography.models.core.relationships import CartographyRelSchema
from cartography.models.core.relationships import LinkDirection
from cartography.models.core.relationships import make_target_node_matcher
from cartography.models.core.relationships import OtherRelationships
from cartography.models.core.relationships import TargetNodeMatcher


@dataclass(frozen=True)
class ProxmoxClusterNodeProperties(CartographyNodeProperties):
    id: PropertyRef = PropertyRef(
        "id",
        description=(
            "Cluster name, or an identifier derived from the API hostname for "
            "a standalone node."
        ),
    )
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)
    name: PropertyRef = PropertyRef(
        "name",
        extra_index=True,
        description="Cluster name.",
    )
    version: PropertyRef = PropertyRef(
        "version",
        description="Cluster configuration version reported by the cluster status.",
    )
    quorate: PropertyRef = PropertyRef(
        "quorate",
        description="Whether the cluster has quorum.",
    )
    nodes_online: PropertyRef = PropertyRef(
        "nodes_online",
        description="Number of cluster nodes currently online.",
    )
    nodes_total: PropertyRef = PropertyRef(
        "nodes_total",
        description="Total number of nodes in the cluster.",
    )
    cluster_id: PropertyRef = PropertyRef(
        "cluster_id",
        description="Internal cluster identifier reported by the cluster status.",
    )
    migration_type: PropertyRef = PropertyRef(
        "migration_type",
        description="Cluster-wide migration mode, secure or insecure (type key of the migration option).",
    )
    migration_network: PropertyRef = PropertyRef(
        "migration_network",
        description="Network CIDR used for migrations (network key of the migration option).",
    )
    migration_bandwidth_limit: PropertyRef = PropertyRef(
        "migration_bandwidth_limit",
        description="Cluster-wide I/O bandwidth limit for migrations in KiB/s (migration key of the bwlimit option).",
    )
    console: PropertyRef = PropertyRef(
        "console",
        description="Default console viewer.",
    )
    email_from: PropertyRef = PropertyRef(
        "email_from",
        description="Sender address for notification emails.",
    )
    http_proxy: PropertyRef = PropertyRef(
        "http_proxy",
        description="HTTP proxy used for external downloads.",
    )
    keyboard: PropertyRef = PropertyRef(
        "keyboard",
        description="Default keyboard layout for the VNC server.",
    )
    language: PropertyRef = PropertyRef(
        "language",
        description="Default web interface language.",
    )
    mac_prefix: PropertyRef = PropertyRef(
        "mac_prefix",
        description="Prefix for automatically generated MAC addresses.",
    )
    max_workers: PropertyRef = PropertyRef(
        "max_workers",
        description="Maximum number of workers started for bulk actions.",
    )
    next_id_lower: PropertyRef = PropertyRef(
        "next_id_lower",
        description="Lower bound of the range for automatically assigned VM IDs.",
    )
    next_id_upper: PropertyRef = PropertyRef(
        "next_id_upper",
        description="Upper bound of the range for automatically assigned VM IDs.",
    )
    totem_interface: PropertyRef = PropertyRef(
        "totem_interface",
        description="Corosync totem interface configuration.",
    )
    totem_cluster_name: PropertyRef = PropertyRef(
        "totem_cluster_name",
        description="Cluster name in the Corosync totem configuration.",
    )
    totem_config_version: PropertyRef = PropertyRef(
        "totem_config_version",
        description="Corosync configuration version.",
    )
    totem_ip_version: PropertyRef = PropertyRef(
        "totem_ip_version",
        description="IP version used by Corosync.",
    )
    totem_secauth: PropertyRef = PropertyRef(
        "totem_secauth",
        description="Whether Corosync authentication and encryption are enabled.",
    )
    totem_version: PropertyRef = PropertyRef(
        "totem_version",
        description="Corosync totem protocol version.",
    )


@dataclass(frozen=True)
class ProxmoxClusterSchema(CartographyNodeSchema):
    """A Proxmox VE cluster, the tenant that owns every other Proxmox resource."""

    label: str = "ProxmoxCluster"
    properties: ProxmoxClusterNodeProperties = ProxmoxClusterNodeProperties()
    sub_resource_relationship: None = None


@dataclass(frozen=True)
class ProxmoxNodeNodeProperties(CartographyNodeProperties):
    id: PropertyRef = PropertyRef(
        "id",
        description="Node ID in the form cluster_id/node_name.",
    )
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)
    name: PropertyRef = PropertyRef(
        "name",
        extra_index=True,
        description="Node name.",
    )
    cluster_id: PropertyRef = PropertyRef(
        "cluster_id",
        description="ID of the cluster the node belongs to.",
    )
    hostname: PropertyRef = PropertyRef(
        "hostname",
        description="Node hostname, the same value as the node name.",
    )
    ip: PropertyRef = PropertyRef("ip", description="Node IP address.")
    status: PropertyRef = PropertyRef(
        "status",
        description="Node status, such as online, offline or unknown.",
    )
    uptime: PropertyRef = PropertyRef(
        "uptime",
        description="Node uptime in seconds.",
    )
    cpu_count: PropertyRef = PropertyRef(
        "cpu_count",
        description="Number of CPUs available on the node.",
    )
    cpu_usage: PropertyRef = PropertyRef(
        "cpu_usage",
        description="CPU utilization as a fraction between 0 and 1.",
    )
    memory_total: PropertyRef = PropertyRef(
        "memory_total",
        description="Total memory in bytes.",
    )
    memory_used: PropertyRef = PropertyRef(
        "memory_used",
        description="Used memory in bytes.",
    )
    disk_total: PropertyRef = PropertyRef(
        "disk_total",
        description="Root file system size in bytes.",
    )
    disk_used: PropertyRef = PropertyRef(
        "disk_used",
        description="Used root file system space in bytes.",
    )
    level: PropertyRef = PropertyRef(
        "level",
        description="Support subscription level of the node.",
    )
    kversion: PropertyRef = PropertyRef("kversion", description="Kernel version.")
    loadavg: PropertyRef = PropertyRef(
        "loadavg",
        description="Load averages over 1, 5 and 15 minutes, comma-separated.",
    )
    wait: PropertyRef = PropertyRef(
        "wait",
        description="CPU I/O wait fraction.",
    )
    swap_total: PropertyRef = PropertyRef(
        "swap_total",
        description="Total swap space in bytes.",
    )
    swap_used: PropertyRef = PropertyRef(
        "swap_used",
        description="Used swap space in bytes.",
    )
    swap_free: PropertyRef = PropertyRef(
        "swap_free",
        description="Free swap space in bytes.",
    )
    pveversion: PropertyRef = PropertyRef(
        "pveversion",
        description="Proxmox VE version running on the node.",
    )
    cpuinfo: PropertyRef = PropertyRef(
        "cpuinfo",
        description="CPU model information.",
    )
    idle: PropertyRef = PropertyRef(
        "idle",
        description="CPU idle fraction.",
    )


@dataclass(frozen=True)
class ProxmoxNodeToClusterRelProperties(CartographyRelProperties):
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)


@dataclass(frozen=True)
class ProxmoxNodeToClusterRel(CartographyRelSchema):
    """The cluster contains the node."""

    target_node_label: str = "ProxmoxCluster"
    target_node_matcher: TargetNodeMatcher = make_target_node_matcher(
        {"id": PropertyRef("CLUSTER_ID", set_in_kwargs=True)},
    )
    direction: LinkDirection = LinkDirection.INWARD
    rel_label: str = "RESOURCE"
    properties: ProxmoxNodeToClusterRelProperties = ProxmoxNodeToClusterRelProperties()


@dataclass(frozen=True)
class ProxmoxNodeSchema(CartographyNodeSchema):
    """A physical host (node) in a Proxmox VE cluster."""

    label: str = "ProxmoxNode"
    properties: ProxmoxNodeNodeProperties = ProxmoxNodeNodeProperties()
    sub_resource_relationship: ProxmoxNodeToClusterRel = ProxmoxNodeToClusterRel()


@dataclass(frozen=True)
class ProxmoxNodeNetworkInterfaceNodeProperties(CartographyNodeProperties):
    id: PropertyRef = PropertyRef(
        "id",
        description=("Interface ID in the form cluster_id/node_name:interface_name."),
    )
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)
    cluster_id: PropertyRef = PropertyRef(
        "cluster_id",
        description="ID of the cluster the interface belongs to.",
    )
    name: PropertyRef = PropertyRef(
        "name",
        extra_index=True,
        description="Interface name, such as vmbr0 or eno1.",
    )
    node_name: PropertyRef = PropertyRef(
        "node_name",
        extra_index=True,
        description="Name of the node that owns the interface.",
    )
    type: PropertyRef = PropertyRef(
        "type",
        description="Interface type, such as bridge, bond, eth or vlan.",
    )
    address: PropertyRef = PropertyRef("address", description="IPv4 address.")
    netmask: PropertyRef = PropertyRef("netmask", description="IPv4 netmask.")
    gateway: PropertyRef = PropertyRef("gateway", description="IPv4 default gateway.")
    address6: PropertyRef = PropertyRef("address6", description="IPv6 address.")
    netmask6: PropertyRef = PropertyRef("netmask6", description="IPv6 prefix length.")
    gateway6: PropertyRef = PropertyRef(
        "gateway6",
        description="IPv6 default gateway.",
    )
    bridge_ports: PropertyRef = PropertyRef(
        "bridge_ports",
        description="Interfaces attached to the bridge.",
    )
    bond_slaves: PropertyRef = PropertyRef(
        "bond_slaves",
        description="Interfaces aggregated by the bond.",
    )
    active: PropertyRef = PropertyRef(
        "active",
        description="Whether the interface is active.",
    )
    autostart: PropertyRef = PropertyRef(
        "autostart",
        description="Whether the interface starts automatically at boot.",
    )
    mtu: PropertyRef = PropertyRef("mtu", description="Maximum transmission unit.")
    bond_mode: PropertyRef = PropertyRef(
        "bond_mode",
        description="Bonding mode, such as balance-rr or active-backup.",
    )
    bond_xmit_hash_policy: PropertyRef = PropertyRef(
        "bond_xmit_hash_policy",
        description="Transmit hash policy of the bond.",
    )
    cidr: PropertyRef = PropertyRef(
        "cidr",
        description="IPv4 address with prefix length in CIDR notation.",
    )
    cidr6: PropertyRef = PropertyRef(
        "cidr6",
        description="IPv6 address with prefix length in CIDR notation.",
    )
    method: PropertyRef = PropertyRef(
        "method",
        description="IPv4 configuration method, such as static, dhcp or manual.",
    )
    method6: PropertyRef = PropertyRef(
        "method6",
        description="IPv6 configuration method.",
    )
    comments: PropertyRef = PropertyRef(
        "comments",
        description="Comments on the interface.",
    )


@dataclass(frozen=True)
class ProxmoxNodeNetworkInterfaceToClusterRelProperties(CartographyRelProperties):
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)


@dataclass(frozen=True)
class ProxmoxNodeNetworkInterfaceToClusterRel(CartographyRelSchema):
    """The cluster contains the node network interface."""

    target_node_label: str = "ProxmoxCluster"
    target_node_matcher: TargetNodeMatcher = make_target_node_matcher(
        {"id": PropertyRef("CLUSTER_ID", set_in_kwargs=True)},
    )
    direction: LinkDirection = LinkDirection.INWARD
    rel_label: str = "RESOURCE"
    properties: ProxmoxNodeNetworkInterfaceToClusterRelProperties = (
        ProxmoxNodeNetworkInterfaceToClusterRelProperties()
    )


@dataclass(frozen=True)
class ProxmoxNodeNetworkInterfaceToNodeRelProperties(CartographyRelProperties):
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)


@dataclass(frozen=True)
class ProxmoxNodeNetworkInterfaceToNodeRel(CartographyRelSchema):
    """The node has the network interface."""

    target_node_label: str = "ProxmoxNode"
    target_node_matcher: TargetNodeMatcher = make_target_node_matcher(
        {"id": PropertyRef("node_id")},
    )
    direction: LinkDirection = LinkDirection.INWARD
    rel_label: str = "HAS_NETWORK_INTERFACE"
    properties: ProxmoxNodeNetworkInterfaceToNodeRelProperties = (
        ProxmoxNodeNetworkInterfaceToNodeRelProperties()
    )


@dataclass(frozen=True)
class ProxmoxNodeNetworkInterfaceSchema(CartographyNodeSchema):
    """A network interface, bridge, bond or VLAN configured on a Proxmox node."""

    label: str = "ProxmoxNodeNetworkInterface"
    properties: ProxmoxNodeNetworkInterfaceNodeProperties = (
        ProxmoxNodeNetworkInterfaceNodeProperties()
    )
    sub_resource_relationship: ProxmoxNodeNetworkInterfaceToClusterRel = (
        ProxmoxNodeNetworkInterfaceToClusterRel()
    )
    other_relationships: OtherRelationships = OtherRelationships(
        [ProxmoxNodeNetworkInterfaceToNodeRel()],
    )
