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
class ProxmoxResourceMappingNodeProperties(CartographyNodeProperties):
    id: PropertyRef = PropertyRef(
        "id",
        description="Resource mapping ID in the form cluster_id/type/mapping_id, such as prod/pci/gpu.",
    )
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)
    mapping_id: PropertyRef = PropertyRef(
        "mapping_id",
        extra_index=True,
        description="Logical ID of the mapping, unique per mapping type inside the cluster.",
    )
    type: PropertyRef = PropertyRef(
        "type",
        description="Mapping type: pci, usb, or dir.",
    )
    cluster_id: PropertyRef = PropertyRef(
        "cluster_id",
        description="ID of the cluster that defines the mapping.",
    )
    description: PropertyRef = PropertyRef(
        "description",
        description="Description of the logical mapping.",
    )
    map: PropertyRef = PropertyRef(
        "map",
        description="Per-node entries of the mapping as returned by the API, such as node=pve,path=0000:01:00.0.",
    )
    nodes: PropertyRef = PropertyRef(
        "nodes",
        description="Names of the cluster nodes that have an entry in the mapping.",
    )


@dataclass(frozen=True)
class ProxmoxResourceMappingToClusterRelProperties(CartographyRelProperties):
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)


@dataclass(frozen=True)
class ProxmoxResourceMappingToClusterRel(CartographyRelSchema):
    """The cluster contains the resource mapping."""

    target_node_label: str = "ProxmoxCluster"
    target_node_matcher: TargetNodeMatcher = make_target_node_matcher(
        {"id": PropertyRef("CLUSTER_ID", set_in_kwargs=True)},
    )
    direction: LinkDirection = LinkDirection.INWARD
    rel_label: str = "RESOURCE"
    properties: ProxmoxResourceMappingToClusterRelProperties = (
        ProxmoxResourceMappingToClusterRelProperties()
    )


@dataclass(frozen=True)
class ProxmoxResourceMappingToNodeRelProperties(CartographyRelProperties):
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)


@dataclass(frozen=True)
class ProxmoxResourceMappingToNodeRel(CartographyRelSchema):
    """The resource mapping has an entry for a device or directory on the cluster node."""

    target_node_label: str = "ProxmoxNode"
    target_node_matcher: TargetNodeMatcher = make_target_node_matcher(
        {"id": PropertyRef("node_ids", one_to_many=True)},
    )
    direction: LinkDirection = LinkDirection.OUTWARD
    rel_label: str = "AVAILABLE_ON"
    properties: ProxmoxResourceMappingToNodeRelProperties = (
        ProxmoxResourceMappingToNodeRelProperties()
    )


@dataclass(frozen=True)
class ProxmoxVMToResourceMappingRelProperties(CartographyRelProperties):
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)


@dataclass(frozen=True)
class ProxmoxVMToResourceMappingRel(CartographyRelSchema):
    """The VM configuration passes the mapped PCI device, USB device, or directory through to the guest."""

    target_node_label: str = "ProxmoxVM"
    target_node_matcher: TargetNodeMatcher = make_target_node_matcher(
        {"id": PropertyRef("guest_ids", one_to_many=True)},
    )
    direction: LinkDirection = LinkDirection.INWARD
    rel_label: str = "USES_MAPPING"
    properties: ProxmoxVMToResourceMappingRelProperties = (
        ProxmoxVMToResourceMappingRelProperties()
    )


@dataclass(frozen=True)
class ProxmoxResourceMappingSchema(CartographyNodeSchema):
    """A cluster-wide mapping of a PCI device, USB device, or host directory that guests can use on any node listed in it."""

    label: str = "ProxmoxResourceMapping"
    properties: ProxmoxResourceMappingNodeProperties = (
        ProxmoxResourceMappingNodeProperties()
    )
    sub_resource_relationship: ProxmoxResourceMappingToClusterRel = (
        ProxmoxResourceMappingToClusterRel()
    )
    other_relationships: OtherRelationships = OtherRelationships(
        [ProxmoxResourceMappingToNodeRel(), ProxmoxVMToResourceMappingRel()],
    )
