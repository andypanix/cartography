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
from cartography.models.proxmox.cluster import ProxmoxClusterNodeProperties
from cartography.models.proxmox.cluster import ProxmoxNodeNodeProperties
from cartography.models.proxmox.cluster import ProxmoxNodeToClusterRel
from cartography.models.proxmox.compute import ProxmoxVMNodeProperties
from cartography.models.proxmox.compute import ProxmoxVMToClusterRel


@dataclass(frozen=True)
class ProxmoxFirewallRuleNodeProperties(CartographyNodeProperties):
    id: PropertyRef = PropertyRef(
        "id",
        description=(
            "Rule ID in the form cluster_id/scope[:scope_id]:pos, such as "
            "prod/node:pve:0."
        ),
    )
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)
    cluster_id: PropertyRef = PropertyRef(
        "cluster_id",
        description="ID of the cluster that holds the rule.",
    )
    scope: PropertyRef = PropertyRef(
        "scope",
        description=(
            "Level where the rule is defined: cluster, node, vm, or group. "
            "Rules of QEMU VMs and LXC containers both use vm; rules inside a "
            "security group use group."
        ),
    )
    scope_id: PropertyRef = PropertyRef(
        "scope_id",
        description=(
            "Node name, VM ID, or security group name for node, VM, and group "
            "rules; empty for cluster rules."
        ),
    )
    pos: PropertyRef = PropertyRef(
        "pos",
        description="Position of the rule in the rule list.",
    )
    type: PropertyRef = PropertyRef(
        "type",
        description="Rule type: in, out, forward, or group.",
    )
    action: PropertyRef = PropertyRef(
        "action",
        description="Rule action, such as ACCEPT, DROP, or REJECT, or a security group name.",
    )
    enable: PropertyRef = PropertyRef(
        "enable",
        description="Whether the rule is enabled.",
    )
    iface: PropertyRef = PropertyRef(
        "iface",
        description="Network interface the rule applies to.",
    )
    source: PropertyRef = PropertyRef(
        "source",
        description="Source address, network, alias, or IP set.",
    )
    dest: PropertyRef = PropertyRef(
        "dest",
        description="Destination address, network, alias, or IP set.",
    )
    proto: PropertyRef = PropertyRef(
        "proto",
        description="IP protocol, such as tcp, udp, or icmp.",
    )
    sport: PropertyRef = PropertyRef("sport", description="Source port or port range.")
    dport: PropertyRef = PropertyRef(
        "dport",
        description="Destination port or port range.",
    )
    icmp_type: PropertyRef = PropertyRef(
        "icmp_type",
        description="ICMP type, for rules whose protocol is icmp or icmpv6.",
    )
    ipversion: PropertyRef = PropertyRef(
        "ipversion",
        description="IP version (4 or 6), derived by Proxmox from the source and destination.",
    )
    comment: PropertyRef = PropertyRef("comment", description="Rule comment.")
    macro: PropertyRef = PropertyRef(
        "macro",
        description="Name of the predefined firewall macro the rule uses.",
    )
    log: PropertyRef = PropertyRef(
        "log",
        description="Log level for packets matching the rule.",
    )


@dataclass(frozen=True)
class ProxmoxFirewallRuleToClusterRelProperties(CartographyRelProperties):
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)


@dataclass(frozen=True)
class ProxmoxFirewallRuleToClusterRel(CartographyRelSchema):
    """The cluster contains the firewall rule."""

    target_node_label: str = "ProxmoxCluster"
    target_node_matcher: TargetNodeMatcher = make_target_node_matcher(
        {"id": PropertyRef("CLUSTER_ID", set_in_kwargs=True)},
    )
    direction: LinkDirection = LinkDirection.INWARD
    rel_label: str = "RESOURCE"
    properties: ProxmoxFirewallRuleToClusterRelProperties = (
        ProxmoxFirewallRuleToClusterRelProperties()
    )


@dataclass(frozen=True)
class ProxmoxFirewallRuleToNodeRelProperties(CartographyRelProperties):
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)


@dataclass(frozen=True)
class ProxmoxFirewallRuleToNodeRel(CartographyRelSchema):
    """The node-level firewall rule applies to the cluster node."""

    target_node_label: str = "ProxmoxNode"
    target_node_matcher: TargetNodeMatcher = make_target_node_matcher(
        {"id": PropertyRef("target_node_id")},
    )
    direction: LinkDirection = LinkDirection.OUTWARD
    rel_label: str = "APPLIES_TO_NODE"
    properties: ProxmoxFirewallRuleToNodeRelProperties = (
        ProxmoxFirewallRuleToNodeRelProperties()
    )


@dataclass(frozen=True)
class ProxmoxFirewallRuleToVMRelProperties(CartographyRelProperties):
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)


@dataclass(frozen=True)
class ProxmoxFirewallRuleToVMRel(CartographyRelSchema):
    """The guest-level firewall rule applies to the VM or container of the same cluster."""

    target_node_label: str = "ProxmoxVM"
    target_node_matcher: TargetNodeMatcher = make_target_node_matcher(
        {
            "vmid": PropertyRef("target_vmid"),
            "cluster_id": PropertyRef("CLUSTER_ID", set_in_kwargs=True),
        },
    )
    direction: LinkDirection = LinkDirection.OUTWARD
    rel_label: str = "APPLIES_TO_VM"
    properties: ProxmoxFirewallRuleToVMRelProperties = (
        ProxmoxFirewallRuleToVMRelProperties()
    )


@dataclass(frozen=True)
class ProxmoxFirewallRuleToSecurityGroupRelProperties(CartographyRelProperties):
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)


@dataclass(frozen=True)
class ProxmoxFirewallRuleInSecurityGroupRel(CartographyRelSchema):
    """The security group contains the firewall rule."""

    target_node_label: str = "ProxmoxFirewallSecurityGroup"
    target_node_matcher: TargetNodeMatcher = make_target_node_matcher(
        {"id": PropertyRef("security_group_id")},
    )
    direction: LinkDirection = LinkDirection.INWARD
    rel_label: str = "HAS_RULE"
    properties: ProxmoxFirewallRuleToSecurityGroupRelProperties = (
        ProxmoxFirewallRuleToSecurityGroupRelProperties()
    )


@dataclass(frozen=True)
class ProxmoxFirewallRuleUsesSecurityGroupRel(CartographyRelSchema):
    """The group-type firewall rule includes every rule of the security group in its rule list."""

    target_node_label: str = "ProxmoxFirewallSecurityGroup"
    target_node_matcher: TargetNodeMatcher = make_target_node_matcher(
        {"id": PropertyRef("uses_security_group_id")},
    )
    direction: LinkDirection = LinkDirection.OUTWARD
    rel_label: str = "USES_SECURITY_GROUP"
    properties: ProxmoxFirewallRuleToSecurityGroupRelProperties = (
        ProxmoxFirewallRuleToSecurityGroupRelProperties()
    )


@dataclass(frozen=True)
class ProxmoxFirewallRuleToAddressRelProperties(CartographyRelProperties):
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)


@dataclass(frozen=True)
class ProxmoxFirewallRuleSourceIPSetRel(CartographyRelSchema):
    """The firewall rule matches packets whose source address is in the IP set."""

    target_node_label: str = "ProxmoxFirewallIPSet"
    target_node_matcher: TargetNodeMatcher = make_target_node_matcher(
        {"id": PropertyRef("source_ipset_id")},
    )
    direction: LinkDirection = LinkDirection.OUTWARD
    rel_label: str = "HAS_SOURCE"
    properties: ProxmoxFirewallRuleToAddressRelProperties = (
        ProxmoxFirewallRuleToAddressRelProperties()
    )


@dataclass(frozen=True)
class ProxmoxFirewallRuleDestIPSetRel(CartographyRelSchema):
    """The firewall rule matches packets whose destination address is in the IP set."""

    target_node_label: str = "ProxmoxFirewallIPSet"
    target_node_matcher: TargetNodeMatcher = make_target_node_matcher(
        {"id": PropertyRef("dest_ipset_id")},
    )
    direction: LinkDirection = LinkDirection.OUTWARD
    rel_label: str = "HAS_DESTINATION"
    properties: ProxmoxFirewallRuleToAddressRelProperties = (
        ProxmoxFirewallRuleToAddressRelProperties()
    )


@dataclass(frozen=True)
class ProxmoxFirewallRuleSourceAliasRel(CartographyRelSchema):
    """The firewall rule matches packets whose source address is the alias address."""

    target_node_label: str = "ProxmoxFirewallAlias"
    target_node_matcher: TargetNodeMatcher = make_target_node_matcher(
        {"id": PropertyRef("source_alias_id")},
    )
    direction: LinkDirection = LinkDirection.OUTWARD
    rel_label: str = "HAS_SOURCE"
    properties: ProxmoxFirewallRuleToAddressRelProperties = (
        ProxmoxFirewallRuleToAddressRelProperties()
    )


@dataclass(frozen=True)
class ProxmoxFirewallRuleDestAliasRel(CartographyRelSchema):
    """The firewall rule matches packets whose destination address is the alias address."""

    target_node_label: str = "ProxmoxFirewallAlias"
    target_node_matcher: TargetNodeMatcher = make_target_node_matcher(
        {"id": PropertyRef("dest_alias_id")},
    )
    direction: LinkDirection = LinkDirection.OUTWARD
    rel_label: str = "HAS_DESTINATION"
    properties: ProxmoxFirewallRuleToAddressRelProperties = (
        ProxmoxFirewallRuleToAddressRelProperties()
    )


@dataclass(frozen=True)
class ProxmoxFirewallRuleSchema(CartographyNodeSchema):
    """A firewall rule defined at cluster, node, VM, or security group level in a Proxmox VE cluster."""

    label: str = "ProxmoxFirewallRule"
    properties: ProxmoxFirewallRuleNodeProperties = ProxmoxFirewallRuleNodeProperties()
    sub_resource_relationship: ProxmoxFirewallRuleToClusterRel = (
        ProxmoxFirewallRuleToClusterRel()
    )
    other_relationships: OtherRelationships = OtherRelationships(
        [
            ProxmoxFirewallRuleToNodeRel(),
            ProxmoxFirewallRuleToVMRel(),
            ProxmoxFirewallRuleInSecurityGroupRel(),
            ProxmoxFirewallRuleUsesSecurityGroupRel(),
            ProxmoxFirewallRuleSourceIPSetRel(),
            ProxmoxFirewallRuleDestIPSetRel(),
            ProxmoxFirewallRuleSourceAliasRel(),
            ProxmoxFirewallRuleDestAliasRel(),
        ],
    )


@dataclass(frozen=True)
class ProxmoxFirewallIPSetNodeProperties(CartographyNodeProperties):
    id: PropertyRef = PropertyRef(
        "id",
        description=(
            "IP set ID in the form cluster_id/scope[:scope_id]:name, such as "
            "prod/cluster:trusted or prod/vm:100:backends."
        ),
    )
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)
    name: PropertyRef = PropertyRef(
        "name",
        extra_index=True,
        description="IP set name.",
    )
    cluster_id: PropertyRef = PropertyRef(
        "cluster_id",
        description="ID of the cluster that holds the IP set.",
    )
    scope: PropertyRef = PropertyRef(
        "scope",
        description=(
            "Level where the IP set is defined: cluster or vm. IP sets of QEMU "
            "VMs and LXC containers both use vm."
        ),
    )
    scope_id: PropertyRef = PropertyRef(
        "scope_id",
        description="VM ID for guest IP sets; empty for cluster IP sets.",
    )
    comment: PropertyRef = PropertyRef("comment", description="IP set comment.")
    cidrs: PropertyRef = PropertyRef(
        "cidrs",
        description=(
            "Addresses, networks, and alias names in the IP set, without the "
            "entries listed in nomatch_cidrs."
        ),
    )
    nomatch_cidrs: PropertyRef = PropertyRef(
        "nomatch_cidrs",
        description=(
            "Entries marked nomatch, which Proxmox excludes from the IP set "
            "even when another entry covers them."
        ),
    )


@dataclass(frozen=True)
class ProxmoxFirewallIPSetToClusterRelProperties(CartographyRelProperties):
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)


@dataclass(frozen=True)
class ProxmoxFirewallIPSetToClusterRel(CartographyRelSchema):
    """The cluster contains the firewall IP set."""

    target_node_label: str = "ProxmoxCluster"
    target_node_matcher: TargetNodeMatcher = make_target_node_matcher(
        {"id": PropertyRef("CLUSTER_ID", set_in_kwargs=True)},
    )
    direction: LinkDirection = LinkDirection.INWARD
    rel_label: str = "RESOURCE"
    properties: ProxmoxFirewallIPSetToClusterRelProperties = (
        ProxmoxFirewallIPSetToClusterRelProperties()
    )


@dataclass(frozen=True)
class ProxmoxFirewallIPSetToVMRelProperties(CartographyRelProperties):
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)


@dataclass(frozen=True)
class ProxmoxFirewallIPSetToVMRel(CartographyRelSchema):
    """The VM or container defines the IP set in its own firewall configuration."""

    target_node_label: str = "ProxmoxVM"
    target_node_matcher: TargetNodeMatcher = make_target_node_matcher(
        {"id": PropertyRef("vm_id")},
    )
    direction: LinkDirection = LinkDirection.INWARD
    rel_label: str = "HAS_FIREWALL_IPSET"
    properties: ProxmoxFirewallIPSetToVMRelProperties = (
        ProxmoxFirewallIPSetToVMRelProperties()
    )


@dataclass(frozen=True)
class ProxmoxFirewallIPSetSchema(CartographyNodeSchema):
    """A named set of IP addresses and networks for use in Proxmox VE firewall rules."""

    label: str = "ProxmoxFirewallIPSet"
    properties: ProxmoxFirewallIPSetNodeProperties = (
        ProxmoxFirewallIPSetNodeProperties()
    )
    sub_resource_relationship: ProxmoxFirewallIPSetToClusterRel = (
        ProxmoxFirewallIPSetToClusterRel()
    )
    other_relationships: OtherRelationships = OtherRelationships(
        [ProxmoxFirewallIPSetToVMRel()],
    )


# ============================================================================
# Firewall options, stored on the cluster, node, and guest they configure
# ============================================================================


@dataclass(frozen=True)
class ProxmoxClusterFirewallOptionsProperties(CartographyNodeProperties):
    id: PropertyRef = ProxmoxClusterNodeProperties.id
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)
    firewall_enabled: PropertyRef = PropertyRef(
        "firewall_enabled",
        description=(
            "Whether the firewall is enabled cluster wide. Node and guest "
            "rules are only enforced when this is true. Proxmox default: false."
        ),
    )
    firewall_ebtables: PropertyRef = PropertyRef(
        "firewall_ebtables",
        description="Whether ebtables rules are enabled cluster wide. Proxmox default: true.",
    )
    firewall_policy_in: PropertyRef = PropertyRef(
        "firewall_policy_in",
        description=(
            "Default policy for incoming traffic: ACCEPT, REJECT, or DROP. "
            "Empty when not set."
        ),
    )
    firewall_policy_out: PropertyRef = PropertyRef(
        "firewall_policy_out",
        description=(
            "Default policy for outgoing traffic: ACCEPT, REJECT, or DROP. "
            "Empty when not set."
        ),
    )
    firewall_policy_forward: PropertyRef = PropertyRef(
        "firewall_policy_forward",
        description="Default policy for forwarded traffic: ACCEPT or DROP. Empty when not set.",
    )
    firewall_log_ratelimit: PropertyRef = PropertyRef(
        "firewall_log_ratelimit",
        description=(
            "Log rate limiting settings as Proxmox returns them, such as "
            "enable=1,burst=5,rate=1/second. Empty when not set."
        ),
    )


@dataclass(frozen=True)
class ProxmoxClusterFirewallOptionsSchema(CartographyNodeSchema):
    """Cluster-wide firewall options of a Proxmox VE cluster."""

    label: str = "ProxmoxCluster"
    properties: ProxmoxClusterFirewallOptionsProperties = (
        ProxmoxClusterFirewallOptionsProperties()
    )
    sub_resource_relationship: None = None


@dataclass(frozen=True)
class ProxmoxNodeFirewallOptionsProperties(CartographyNodeProperties):
    id: PropertyRef = ProxmoxNodeNodeProperties.id
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)
    firewall_enabled: PropertyRef = PropertyRef(
        "firewall_enabled",
        description=(
            "Whether host firewall rules are enabled on the node. They are "
            "only enforced when the cluster firewall is enabled too. Proxmox "
            "default: true."
        ),
    )
    firewall_log_level_in: PropertyRef = PropertyRef(
        "firewall_log_level_in",
        description="Log level for incoming traffic, such as info or nolog.",
    )
    firewall_log_level_out: PropertyRef = PropertyRef(
        "firewall_log_level_out",
        description="Log level for outgoing traffic, such as info or nolog.",
    )
    firewall_log_level_forward: PropertyRef = PropertyRef(
        "firewall_log_level_forward",
        description="Log level for forwarded traffic, such as info or nolog.",
    )
    firewall_log_nf_conntrack: PropertyRef = PropertyRef(
        "firewall_log_nf_conntrack",
        description="Whether connection tracking information is logged. Proxmox default: false.",
    )
    firewall_ndp: PropertyRef = PropertyRef(
        "firewall_ndp",
        description="Whether NDP (Neighbor Discovery Protocol) is enabled. Proxmox default: true.",
    )
    firewall_nf_conntrack_allow_invalid: PropertyRef = PropertyRef(
        "firewall_nf_conntrack_allow_invalid",
        description=(
            "Whether invalid packets are allowed on connection tracking. "
            "Proxmox default: false."
        ),
    )
    firewall_nf_conntrack_helpers: PropertyRef = PropertyRef(
        "firewall_nf_conntrack_helpers",
        description="Protocols with a conntrack helper enabled, such as ftp,sip.",
    )
    firewall_nf_conntrack_max: PropertyRef = PropertyRef(
        "firewall_nf_conntrack_max",
        description="Maximum number of tracked connections. Proxmox default: 262144.",
    )
    firewall_nf_conntrack_tcp_timeout_established: PropertyRef = PropertyRef(
        "firewall_nf_conntrack_tcp_timeout_established",
        description=(
            "Conntrack timeout of established connections, in seconds. "
            "Proxmox default: 432000."
        ),
    )
    firewall_nf_conntrack_tcp_timeout_syn_recv: PropertyRef = PropertyRef(
        "firewall_nf_conntrack_tcp_timeout_syn_recv",
        description="Conntrack SYN_RECV timeout, in seconds. Proxmox default: 60.",
    )
    firewall_nftables: PropertyRef = PropertyRef(
        "firewall_nftables",
        description="Whether the nftables based firewall is used. Proxmox default: false.",
    )
    firewall_nosmurfs: PropertyRef = PropertyRef(
        "firewall_nosmurfs",
        description="Whether the SMURFS filter is enabled. Empty when not set.",
    )
    firewall_smurf_log_level: PropertyRef = PropertyRef(
        "firewall_smurf_log_level",
        description="Log level for the SMURFS filter.",
    )
    firewall_tcpflags: PropertyRef = PropertyRef(
        "firewall_tcpflags",
        description=(
            "Whether illegal combinations of TCP flags are filtered. Proxmox "
            "default: false."
        ),
    )
    firewall_tcp_flags_log_level: PropertyRef = PropertyRef(
        "firewall_tcp_flags_log_level",
        description="Log level for the illegal TCP flags filter.",
    )
    firewall_protection_synflood: PropertyRef = PropertyRef(
        "firewall_protection_synflood",
        description="Whether SYN flood protection is enabled. Proxmox default: false.",
    )
    firewall_protection_synflood_burst: PropertyRef = PropertyRef(
        "firewall_protection_synflood_burst",
        description="SYN flood protection rate burst by source IP. Proxmox default: 1000.",
    )
    firewall_protection_synflood_rate: PropertyRef = PropertyRef(
        "firewall_protection_synflood_rate",
        description=(
            "SYN flood protection rate, in SYN packets per second by source "
            "IP. Proxmox default: 200."
        ),
    )


@dataclass(frozen=True)
class ProxmoxNodeFirewallOptionsSchema(CartographyNodeSchema):
    """Host firewall options of a Proxmox VE node."""

    label: str = "ProxmoxNode"
    properties: ProxmoxNodeFirewallOptionsProperties = (
        ProxmoxNodeFirewallOptionsProperties()
    )
    sub_resource_relationship: ProxmoxNodeToClusterRel = ProxmoxNodeToClusterRel()


@dataclass(frozen=True)
class ProxmoxVMFirewallOptionsProperties(CartographyNodeProperties):
    id: PropertyRef = ProxmoxVMNodeProperties.id
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)
    firewall_enabled: PropertyRef = PropertyRef(
        "firewall_enabled",
        description=(
            "Whether the guest firewall rules are enabled. They are only "
            "enforced when the cluster firewall is enabled, and only on "
            "network interfaces whose firewall flag is set. Proxmox default: "
            "false."
        ),
    )
    firewall_policy_in: PropertyRef = PropertyRef(
        "firewall_policy_in",
        description=(
            "Default policy for incoming traffic: ACCEPT, REJECT, or DROP. "
            "Empty when not set."
        ),
    )
    firewall_policy_out: PropertyRef = PropertyRef(
        "firewall_policy_out",
        description=(
            "Default policy for outgoing traffic: ACCEPT, REJECT, or DROP. "
            "Empty when not set."
        ),
    )
    firewall_log_level_in: PropertyRef = PropertyRef(
        "firewall_log_level_in",
        description="Log level for incoming traffic, such as info or nolog.",
    )
    firewall_log_level_out: PropertyRef = PropertyRef(
        "firewall_log_level_out",
        description="Log level for outgoing traffic, such as info or nolog.",
    )
    firewall_dhcp: PropertyRef = PropertyRef(
        "firewall_dhcp",
        description="Whether DHCP is enabled. Proxmox default: false.",
    )
    firewall_ipfilter: PropertyRef = PropertyRef(
        "firewall_ipfilter",
        description=(
            "Whether the default IP filters are enabled, which restrict each "
            "interface to its expected addresses. Empty when not set."
        ),
    )
    firewall_macfilter: PropertyRef = PropertyRef(
        "firewall_macfilter",
        description="Whether the MAC address filter is enabled. Proxmox default: true.",
    )
    firewall_ndp: PropertyRef = PropertyRef(
        "firewall_ndp",
        description="Whether NDP (Neighbor Discovery Protocol) is enabled. Proxmox default: true.",
    )
    firewall_radv: PropertyRef = PropertyRef(
        "firewall_radv",
        description="Whether the guest may send Router Advertisements. Empty when not set.",
    )


@dataclass(frozen=True)
class ProxmoxVMFirewallOptionsSchema(CartographyNodeSchema):
    """Firewall options of a QEMU VM or LXC container."""

    label: str = "ProxmoxVM"
    properties: ProxmoxVMFirewallOptionsProperties = (
        ProxmoxVMFirewallOptionsProperties()
    )
    sub_resource_relationship: ProxmoxVMToClusterRel = ProxmoxVMToClusterRel()


# ============================================================================
# Security groups
# ============================================================================


@dataclass(frozen=True)
class ProxmoxFirewallSecurityGroupNodeProperties(CartographyNodeProperties):
    id: PropertyRef = PropertyRef(
        "id",
        description="Security group ID in the form cluster_id/group:name.",
    )
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)
    name: PropertyRef = PropertyRef(
        "name",
        extra_index=True,
        description="Security group name.",
    )
    cluster_id: PropertyRef = PropertyRef(
        "cluster_id",
        description="ID of the cluster that holds the security group.",
    )
    comment: PropertyRef = PropertyRef(
        "comment",
        description="Security group comment.",
    )


@dataclass(frozen=True)
class ProxmoxFirewallSecurityGroupToClusterRelProperties(CartographyRelProperties):
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)


@dataclass(frozen=True)
class ProxmoxFirewallSecurityGroupToClusterRel(CartographyRelSchema):
    """The cluster contains the firewall security group."""

    target_node_label: str = "ProxmoxCluster"
    target_node_matcher: TargetNodeMatcher = make_target_node_matcher(
        {"id": PropertyRef("CLUSTER_ID", set_in_kwargs=True)},
    )
    direction: LinkDirection = LinkDirection.INWARD
    rel_label: str = "RESOURCE"
    properties: ProxmoxFirewallSecurityGroupToClusterRelProperties = (
        ProxmoxFirewallSecurityGroupToClusterRelProperties()
    )


@dataclass(frozen=True)
class ProxmoxFirewallSecurityGroupSchema(CartographyNodeSchema):
    """A named list of firewall rules, defined at cluster level, that cluster, node, and guest rule lists can include."""

    label: str = "ProxmoxFirewallSecurityGroup"
    properties: ProxmoxFirewallSecurityGroupNodeProperties = (
        ProxmoxFirewallSecurityGroupNodeProperties()
    )
    sub_resource_relationship: ProxmoxFirewallSecurityGroupToClusterRel = (
        ProxmoxFirewallSecurityGroupToClusterRel()
    )


# ============================================================================
# Aliases
# ============================================================================


@dataclass(frozen=True)
class ProxmoxFirewallAliasNodeProperties(CartographyNodeProperties):
    id: PropertyRef = PropertyRef(
        "id",
        description=(
            "Alias ID in the form cluster_id/scope[:scope_id]:name, such as "
            "prod/cluster:office or prod/vm:100:backend."
        ),
    )
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)
    name: PropertyRef = PropertyRef(
        "name",
        extra_index=True,
        description="Alias name.",
    )
    cluster_id: PropertyRef = PropertyRef(
        "cluster_id",
        description="ID of the cluster that holds the alias.",
    )
    scope: PropertyRef = PropertyRef(
        "scope",
        description=(
            "Level where the alias is defined: cluster or vm. Aliases of QEMU "
            "VMs and LXC containers both use vm."
        ),
    )
    scope_id: PropertyRef = PropertyRef(
        "scope_id",
        description="VM ID for guest aliases; empty for cluster aliases.",
    )
    cidr: PropertyRef = PropertyRef(
        "cidr",
        description="Address or network the alias stands for.",
    )
    comment: PropertyRef = PropertyRef("comment", description="Alias comment.")


@dataclass(frozen=True)
class ProxmoxFirewallAliasToClusterRelProperties(CartographyRelProperties):
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)


@dataclass(frozen=True)
class ProxmoxFirewallAliasToClusterRel(CartographyRelSchema):
    """The cluster contains the firewall alias."""

    target_node_label: str = "ProxmoxCluster"
    target_node_matcher: TargetNodeMatcher = make_target_node_matcher(
        {"id": PropertyRef("CLUSTER_ID", set_in_kwargs=True)},
    )
    direction: LinkDirection = LinkDirection.INWARD
    rel_label: str = "RESOURCE"
    properties: ProxmoxFirewallAliasToClusterRelProperties = (
        ProxmoxFirewallAliasToClusterRelProperties()
    )


@dataclass(frozen=True)
class ProxmoxFirewallAliasToVMRelProperties(CartographyRelProperties):
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)


@dataclass(frozen=True)
class ProxmoxFirewallAliasToVMRel(CartographyRelSchema):
    """The VM or container defines the alias in its own firewall configuration."""

    target_node_label: str = "ProxmoxVM"
    target_node_matcher: TargetNodeMatcher = make_target_node_matcher(
        {"id": PropertyRef("vm_id")},
    )
    direction: LinkDirection = LinkDirection.INWARD
    rel_label: str = "HAS_FIREWALL_ALIAS"
    properties: ProxmoxFirewallAliasToVMRelProperties = (
        ProxmoxFirewallAliasToVMRelProperties()
    )


@dataclass(frozen=True)
class ProxmoxFirewallAliasSchema(CartographyNodeSchema):
    """A name for an address or network that Proxmox VE firewall rules and IP sets can refer to."""

    label: str = "ProxmoxFirewallAlias"
    properties: ProxmoxFirewallAliasNodeProperties = (
        ProxmoxFirewallAliasNodeProperties()
    )
    sub_resource_relationship: ProxmoxFirewallAliasToClusterRel = (
        ProxmoxFirewallAliasToClusterRel()
    )
    other_relationships: OtherRelationships = OtherRelationships(
        [ProxmoxFirewallAliasToVMRel()],
    )
