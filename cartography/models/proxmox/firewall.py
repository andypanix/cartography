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
        description="Level where the rule is defined: cluster, node, or vm.",
    )
    scope_id: PropertyRef = PropertyRef(
        "scope_id",
        description="Node name or VM ID for node and VM rules; empty for cluster rules.",
    )
    pos: PropertyRef = PropertyRef(
        "pos",
        description="Position of the rule in the rule list.",
    )
    type: PropertyRef = PropertyRef(
        "type",
        description="Rule type: in, out, or group.",
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
class ProxmoxFirewallRuleSchema(CartographyNodeSchema):
    """A firewall rule defined at cluster, node, or VM level in a Proxmox VE cluster."""

    label: str = "ProxmoxFirewallRule"
    properties: ProxmoxFirewallRuleNodeProperties = ProxmoxFirewallRuleNodeProperties()
    sub_resource_relationship: ProxmoxFirewallRuleToClusterRel = (
        ProxmoxFirewallRuleToClusterRel()
    )
    other_relationships: OtherRelationships = OtherRelationships(
        [ProxmoxFirewallRuleToNodeRel(), ProxmoxFirewallRuleToVMRel()],
    )


@dataclass(frozen=True)
class ProxmoxFirewallIPSetNodeProperties(CartographyNodeProperties):
    id: PropertyRef = PropertyRef(
        "id",
        description=(
            "IP set ID in the form cluster_id/scope[:scope_id]:name, such as "
            "prod/cluster:trusted."
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
        description="Level where the IP set is defined: cluster, node, or vm.",
    )
    scope_id: PropertyRef = PropertyRef(
        "scope_id",
        description="Node name or VM ID for node and VM IP sets; empty for cluster IP sets.",
    )
    comment: PropertyRef = PropertyRef("comment", description="IP set comment.")
    cidrs: PropertyRef = PropertyRef(
        "cidrs",
        description="Addresses and networks in the IP set, in CIDR notation.",
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
class ProxmoxFirewallIPSetSchema(CartographyNodeSchema):
    """A named set of IP addresses and networks for use in Proxmox VE firewall rules."""

    label: str = "ProxmoxFirewallIPSet"
    properties: ProxmoxFirewallIPSetNodeProperties = (
        ProxmoxFirewallIPSetNodeProperties()
    )
    sub_resource_relationship: ProxmoxFirewallIPSetToClusterRel = (
        ProxmoxFirewallIPSetToClusterRel()
    )
