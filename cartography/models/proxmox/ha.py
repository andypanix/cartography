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
class ProxmoxHAGroupNodeProperties(CartographyNodeProperties):
    id: PropertyRef = PropertyRef(
        "id",
        description="HA group ID in the form cluster_id/group.",
    )
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)
    group: PropertyRef = PropertyRef(
        "group",
        extra_index=True,
        description="HA group name.",
    )
    cluster_id: PropertyRef = PropertyRef(
        "cluster_id",
        description="ID of the cluster that defines the HA group.",
    )
    nodes: PropertyRef = PropertyRef(
        "nodes",
        description="Cluster nodes in the group, with optional priorities, as returned by the API.",
    )
    restricted: PropertyRef = PropertyRef(
        "restricted",
        description="Whether resources in the group can run only on the group's nodes.",
    )
    nofailback: PropertyRef = PropertyRef(
        "nofailback",
        description="Whether resources stay put instead of migrating back to a higher-priority node.",
    )
    comment: PropertyRef = PropertyRef("comment", description="HA group comment.")


@dataclass(frozen=True)
class ProxmoxHAGroupToClusterRelProperties(CartographyRelProperties):
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)


@dataclass(frozen=True)
class ProxmoxHAGroupToClusterRel(CartographyRelSchema):
    """The cluster contains the HA group."""

    target_node_label: str = "ProxmoxCluster"
    target_node_matcher: TargetNodeMatcher = make_target_node_matcher(
        {"id": PropertyRef("CLUSTER_ID", set_in_kwargs=True)},
    )
    direction: LinkDirection = LinkDirection.INWARD
    rel_label: str = "RESOURCE"
    properties: ProxmoxHAGroupToClusterRelProperties = (
        ProxmoxHAGroupToClusterRelProperties()
    )


@dataclass(frozen=True)
class ProxmoxHAGroupSchema(CartographyNodeSchema):
    """A high availability group that sets node preferences for HA resources in a Proxmox VE cluster."""

    label: str = "ProxmoxHAGroup"
    properties: ProxmoxHAGroupNodeProperties = ProxmoxHAGroupNodeProperties()
    sub_resource_relationship: ProxmoxHAGroupToClusterRel = ProxmoxHAGroupToClusterRel()


@dataclass(frozen=True)
class ProxmoxHAResourceNodeProperties(CartographyNodeProperties):
    id: PropertyRef = PropertyRef(
        "id",
        description="HA resource ID in the form cluster_id/sid, such as prod/vm:100.",
    )
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)
    sid: PropertyRef = PropertyRef(
        "sid",
        extra_index=True,
        description="HA resource service ID, such as vm:100 or ct:200.",
    )
    cluster_id: PropertyRef = PropertyRef(
        "cluster_id",
        description="ID of the cluster that manages the HA resource.",
    )
    state: PropertyRef = PropertyRef(
        "state",
        description="Requested HA state, such as started, stopped, disabled, or ignored.",
    )
    group: PropertyRef = PropertyRef(
        "group",
        description="Name of the HA group the resource belongs to.",
    )
    max_restart: PropertyRef = PropertyRef(
        "max_restart",
        description="Maximum number of restart attempts on a node after a start failure.",
    )
    max_relocate: PropertyRef = PropertyRef(
        "max_relocate",
        description="Maximum number of relocation attempts to another node after a start failure.",
    )
    comment: PropertyRef = PropertyRef("comment", description="HA resource comment.")
    vmid: PropertyRef = PropertyRef(
        "vmid",
        description="Numeric VM ID parsed from the service ID, when the resource is a VM or container.",
    )


@dataclass(frozen=True)
class ProxmoxHAResourceToClusterRelProperties(CartographyRelProperties):
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)


@dataclass(frozen=True)
class ProxmoxHAResourceToClusterRel(CartographyRelSchema):
    """The cluster contains the HA resource."""

    target_node_label: str = "ProxmoxCluster"
    target_node_matcher: TargetNodeMatcher = make_target_node_matcher(
        {"id": PropertyRef("CLUSTER_ID", set_in_kwargs=True)},
    )
    direction: LinkDirection = LinkDirection.INWARD
    rel_label: str = "RESOURCE"
    properties: ProxmoxHAResourceToClusterRelProperties = (
        ProxmoxHAResourceToClusterRelProperties()
    )


@dataclass(frozen=True)
class ProxmoxHAResourceToHAGroupRelProperties(CartographyRelProperties):
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)


@dataclass(frozen=True)
class ProxmoxHAResourceToHAGroupRel(CartographyRelSchema):
    """The HA resource is assigned to the HA group."""

    target_node_label: str = "ProxmoxHAGroup"
    target_node_matcher: TargetNodeMatcher = make_target_node_matcher(
        {"id": PropertyRef("group_id")},
    )
    direction: LinkDirection = LinkDirection.OUTWARD
    rel_label: str = "MEMBER_OF_HA_GROUP"
    properties: ProxmoxHAResourceToHAGroupRelProperties = (
        ProxmoxHAResourceToHAGroupRelProperties()
    )


@dataclass(frozen=True)
class ProxmoxHAResourceToVMRelProperties(CartographyRelProperties):
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)


@dataclass(frozen=True)
class ProxmoxHAResourceToVMRel(CartographyRelSchema):
    """The HA resource keeps the VM or container of the same cluster highly available."""

    target_node_label: str = "ProxmoxVM"
    target_node_matcher: TargetNodeMatcher = make_target_node_matcher(
        {
            "vmid": PropertyRef("vmid"),
            "cluster_id": PropertyRef("CLUSTER_ID", set_in_kwargs=True),
        },
    )
    direction: LinkDirection = LinkDirection.OUTWARD
    rel_label: str = "PROTECTS"
    properties: ProxmoxHAResourceToVMRelProperties = (
        ProxmoxHAResourceToVMRelProperties()
    )


@dataclass(frozen=True)
class ProxmoxHAResourceSchema(CartographyNodeSchema):
    """A VM or container managed by the high availability stack of a Proxmox VE cluster."""

    label: str = "ProxmoxHAResource"
    properties: ProxmoxHAResourceNodeProperties = ProxmoxHAResourceNodeProperties()
    sub_resource_relationship: ProxmoxHAResourceToClusterRel = (
        ProxmoxHAResourceToClusterRel()
    )
    other_relationships: OtherRelationships = OtherRelationships(
        [ProxmoxHAResourceToHAGroupRel(), ProxmoxHAResourceToVMRel()],
    )
