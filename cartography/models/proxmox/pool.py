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
class ProxmoxPoolNodeProperties(CartographyNodeProperties):
    id: PropertyRef = PropertyRef(
        "id",
        description="Pool ID in the form cluster_id/poolid.",
    )
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)
    poolid: PropertyRef = PropertyRef(
        "poolid",
        extra_index=True,
        description="Pool ID as returned by the Proxmox VE API.",
    )
    comment: PropertyRef = PropertyRef("comment", description="Pool comment.")
    cluster_id: PropertyRef = PropertyRef(
        "cluster_id",
        description="ID of the cluster that defines the pool.",
    )
    parent_poolid: PropertyRef = PropertyRef(
        "parent_poolid",
        description="Pool ID of the parent pool, when the pool is nested, such as dev for dev/team1.",
    )


@dataclass(frozen=True)
class ProxmoxPoolToClusterRelProperties(CartographyRelProperties):
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)


@dataclass(frozen=True)
class ProxmoxPoolToClusterRel(CartographyRelSchema):
    """The cluster contains the resource pool."""

    target_node_label: str = "ProxmoxCluster"
    target_node_matcher: TargetNodeMatcher = make_target_node_matcher(
        {"id": PropertyRef("CLUSTER_ID", set_in_kwargs=True)},
    )
    direction: LinkDirection = LinkDirection.INWARD
    rel_label: str = "RESOURCE"
    properties: ProxmoxPoolToClusterRelProperties = ProxmoxPoolToClusterRelProperties()


@dataclass(frozen=True)
class ProxmoxPoolToVMRelProperties(CartographyRelProperties):
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)


@dataclass(frozen=True)
class ProxmoxPoolToVMRel(CartographyRelSchema):
    """The resource pool contains the VM or container."""

    target_node_label: str = "ProxmoxVM"
    target_node_matcher: TargetNodeMatcher = make_target_node_matcher(
        {"id": PropertyRef("vm_ids", one_to_many=True)},
    )
    direction: LinkDirection = LinkDirection.OUTWARD
    rel_label: str = "CONTAINS_VM"
    properties: ProxmoxPoolToVMRelProperties = ProxmoxPoolToVMRelProperties()


@dataclass(frozen=True)
class ProxmoxPoolToStorageRelProperties(CartographyRelProperties):
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)


@dataclass(frozen=True)
class ProxmoxPoolToStorageRel(CartographyRelSchema):
    """The resource pool contains the storage."""

    target_node_label: str = "ProxmoxStorage"
    target_node_matcher: TargetNodeMatcher = make_target_node_matcher(
        {"id": PropertyRef("storage_ids", one_to_many=True)},
    )
    direction: LinkDirection = LinkDirection.OUTWARD
    rel_label: str = "CONTAINS_STORAGE"
    properties: ProxmoxPoolToStorageRelProperties = ProxmoxPoolToStorageRelProperties()


@dataclass(frozen=True)
class ProxmoxPoolToParentPoolRelProperties(CartographyRelProperties):
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)


@dataclass(frozen=True)
class ProxmoxPoolToParentPoolRel(CartographyRelSchema):
    """The parent resource pool contains the nested pool."""

    target_node_label: str = "ProxmoxPool"
    target_node_matcher: TargetNodeMatcher = make_target_node_matcher(
        {"id": PropertyRef("parent_pool_id")},
    )
    direction: LinkDirection = LinkDirection.INWARD
    rel_label: str = "CONTAINS_POOL"
    properties: ProxmoxPoolToParentPoolRelProperties = (
        ProxmoxPoolToParentPoolRelProperties()
    )


@dataclass(frozen=True)
class ProxmoxPoolSchema(CartographyNodeSchema):
    """A resource pool grouping VMs, containers, storage, and nested pools in a Proxmox VE cluster."""

    label: str = "ProxmoxPool"
    properties: ProxmoxPoolNodeProperties = ProxmoxPoolNodeProperties()
    sub_resource_relationship: ProxmoxPoolToClusterRel = ProxmoxPoolToClusterRel()
    other_relationships: OtherRelationships = OtherRelationships(
        [ProxmoxPoolToVMRel(), ProxmoxPoolToStorageRel(), ProxmoxPoolToParentPoolRel()],
    )
