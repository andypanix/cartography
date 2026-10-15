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
class ProxmoxStorageNodeProperties(CartographyNodeProperties):
    id: PropertyRef = PropertyRef("id", description="Storage ID.")
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)
    name: PropertyRef = PropertyRef(
        "name",
        extra_index=True,
        description="Storage name, identical to the storage ID.",
    )
    cluster_id: PropertyRef = PropertyRef(
        "cluster_id",
        description="ID of the cluster that defines the storage.",
    )
    type: PropertyRef = PropertyRef(
        "type",
        description="Storage type, such as dir, lvmthin, zfspool, nfs, or cephfs.",
    )
    content_types: PropertyRef = PropertyRef(
        "content_types",
        description="Content types the storage accepts, such as images, rootdir, iso, or backup.",
    )
    shared: PropertyRef = PropertyRef(
        "shared",
        description="Whether the storage is shared across all cluster nodes.",
    )
    enabled: PropertyRef = PropertyRef(
        "enabled",
        description="Whether the storage is enabled.",
    )
    total: PropertyRef = PropertyRef(
        "total",
        description="Total storage capacity in bytes, as reported by the node status.",
    )
    used: PropertyRef = PropertyRef(
        "used",
        description="Used storage space in bytes, as reported by the node status.",
    )
    available: PropertyRef = PropertyRef(
        "available",
        description="Available storage space in bytes, as reported by the node status.",
    )


@dataclass(frozen=True)
class ProxmoxStorageToClusterRelProperties(CartographyRelProperties):
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)


@dataclass(frozen=True)
class ProxmoxStorageToClusterRel(CartographyRelSchema):
    """The cluster contains the storage."""

    target_node_label: str = "ProxmoxCluster"
    target_node_matcher: TargetNodeMatcher = make_target_node_matcher(
        {"id": PropertyRef("CLUSTER_ID", set_in_kwargs=True)},
    )
    direction: LinkDirection = LinkDirection.INWARD
    rel_label: str = "RESOURCE"
    properties: ProxmoxStorageToClusterRelProperties = (
        ProxmoxStorageToClusterRelProperties()
    )


@dataclass(frozen=True)
class ProxmoxStorageToNodeRelProperties(CartographyRelProperties):
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)


@dataclass(frozen=True)
class ProxmoxStorageToNodeRel(CartographyRelSchema):
    """The storage is available on the cluster node."""

    target_node_label: str = "ProxmoxNode"
    target_node_matcher: TargetNodeMatcher = make_target_node_matcher(
        {"id": PropertyRef("nodes", one_to_many=True)},
    )
    direction: LinkDirection = LinkDirection.OUTWARD
    rel_label: str = "AVAILABLE_ON"
    properties: ProxmoxStorageToNodeRelProperties = ProxmoxStorageToNodeRelProperties()


@dataclass(frozen=True)
class ProxmoxStorageSchema(CartographyNodeSchema):
    """A storage backend configured in a Proxmox VE cluster."""

    label: str = "ProxmoxStorage"
    properties: ProxmoxStorageNodeProperties = ProxmoxStorageNodeProperties()
    sub_resource_relationship: ProxmoxStorageToClusterRel = ProxmoxStorageToClusterRel()
    other_relationships: OtherRelationships = OtherRelationships(
        [ProxmoxStorageToNodeRel()],
    )
