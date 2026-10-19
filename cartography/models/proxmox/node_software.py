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
class ProxmoxNodeSoftwareRelProperties(CartographyRelProperties):
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)


# ============================================================================
# ProxmoxPackage
# ============================================================================


@dataclass(frozen=True)
class ProxmoxPackageNodeProperties(CartographyNodeProperties):
    id: PropertyRef = PropertyRef(
        "id",
        description="Package ID in the form cluster_id/node_name:package:package_name.",
    )
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)
    cluster_id: PropertyRef = PropertyRef(
        "cluster_id",
        description="ID of the Proxmox cluster the package belongs to.",
    )
    node_name: PropertyRef = PropertyRef(
        "node_name",
        description="Name of the Proxmox node the package is on.",
    )
    name: PropertyRef = PropertyRef(
        "name",
        extra_index=True,
        description="Debian package name, such as pve-manager or proxmox-ve.",
    )
    version: PropertyRef = PropertyRef(
        "version",
        description="Package version.",
    )
    old_version: PropertyRef = PropertyRef(
        "old_version",
        description="Version currently installed, when an update is pending.",
    )
    current_state: PropertyRef = PropertyRef(
        "current_state",
        description="Installation state of the package, such as Installed or ConfigFiles.",
    )
    origin: PropertyRef = PropertyRef(
        "origin",
        description="Package origin, such as Proxmox or Debian.",
    )
    arch: PropertyRef = PropertyRef(
        "arch",
        description="Package architecture.",
    )
    section: PropertyRef = PropertyRef(
        "section",
        description="Package section.",
    )
    priority: PropertyRef = PropertyRef(
        "priority",
        description="Package priority.",
    )
    title: PropertyRef = PropertyRef(
        "title",
        description="Short package title.",
    )
    running_kernel: PropertyRef = PropertyRef(
        "running_kernel",
        description="Release of the running kernel, set only on the proxmox-ve package.",
    )
    manager_version: PropertyRef = PropertyRef(
        "manager_version",
        description="Version of the running pve-manager API server, set only on the pve-manager package.",
    )


@dataclass(frozen=True)
class ProxmoxPackageToClusterRel(CartographyRelSchema):
    """The cluster contains the package."""

    target_node_label: str = "ProxmoxCluster"
    target_node_matcher: TargetNodeMatcher = make_target_node_matcher(
        {"id": PropertyRef("CLUSTER_ID", set_in_kwargs=True)},
    )
    direction: LinkDirection = LinkDirection.INWARD
    rel_label: str = "RESOURCE"
    properties: ProxmoxNodeSoftwareRelProperties = ProxmoxNodeSoftwareRelProperties()


@dataclass(frozen=True)
class ProxmoxPackageToNodeRel(CartographyRelSchema):
    """The package is installed on the Proxmox node."""

    target_node_label: str = "ProxmoxNode"
    target_node_matcher: TargetNodeMatcher = make_target_node_matcher(
        {"id": PropertyRef("node_id")},
    )
    direction: LinkDirection = LinkDirection.INWARD
    rel_label: str = "HAS_PACKAGE"
    properties: ProxmoxNodeSoftwareRelProperties = ProxmoxNodeSoftwareRelProperties()


@dataclass(frozen=True)
class ProxmoxPackageSchema(CartographyNodeSchema):
    """A key Proxmox VE package on a node, as listed by the node package versions."""

    label: str = "ProxmoxPackage"
    properties: ProxmoxPackageNodeProperties = ProxmoxPackageNodeProperties()
    sub_resource_relationship: ProxmoxPackageToClusterRel = ProxmoxPackageToClusterRel()
    other_relationships: OtherRelationships = OtherRelationships(
        [ProxmoxPackageToNodeRel()],
    )


# ============================================================================
# ProxmoxAPTRepository
# ============================================================================


@dataclass(frozen=True)
class ProxmoxAPTRepositoryNodeProperties(CartographyNodeProperties):
    id: PropertyRef = PropertyRef(
        "id",
        description="Repository ID in the form cluster_id/node_name:apt:file_path:index.",
    )
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)
    cluster_id: PropertyRef = PropertyRef(
        "cluster_id",
        description="ID of the Proxmox cluster the repository belongs to.",
    )
    node_name: PropertyRef = PropertyRef(
        "node_name",
        description="Name of the Proxmox node the repository is configured on.",
    )
    path: PropertyRef = PropertyRef(
        "path",
        description="Path of the APT source file that defines the repository.",
    )
    index: PropertyRef = PropertyRef(
        "index",
        description="Position of the repository in its source file, starting at 0.",
    )
    file_type: PropertyRef = PropertyRef(
        "file_type",
        description="Format of the source file, list or sources.",
    )
    enabled: PropertyRef = PropertyRef(
        "enabled",
        description="Whether the repository is enabled.",
    )
    types: PropertyRef = PropertyRef(
        "types",
        description="Package types of the repository, deb or deb-src.",
    )
    uris: PropertyRef = PropertyRef(
        "uris",
        description="URIs of the repository.",
    )
    suites: PropertyRef = PropertyRef(
        "suites",
        description="Distributions of the repository, such as bookworm or trixie.",
    )
    components: PropertyRef = PropertyRef(
        "components",
        description="Components of the repository, such as main or pve-enterprise.",
    )
    comment: PropertyRef = PropertyRef(
        "comment",
        description="Comment attached to the repository.",
    )


@dataclass(frozen=True)
class ProxmoxAPTRepositoryToClusterRel(CartographyRelSchema):
    """The cluster contains the APT repository."""

    target_node_label: str = "ProxmoxCluster"
    target_node_matcher: TargetNodeMatcher = make_target_node_matcher(
        {"id": PropertyRef("CLUSTER_ID", set_in_kwargs=True)},
    )
    direction: LinkDirection = LinkDirection.INWARD
    rel_label: str = "RESOURCE"
    properties: ProxmoxNodeSoftwareRelProperties = ProxmoxNodeSoftwareRelProperties()


@dataclass(frozen=True)
class ProxmoxAPTRepositoryToNodeRel(CartographyRelSchema):
    """The Proxmox node has the APT repository configured."""

    target_node_label: str = "ProxmoxNode"
    target_node_matcher: TargetNodeMatcher = make_target_node_matcher(
        {"id": PropertyRef("node_id")},
    )
    direction: LinkDirection = LinkDirection.INWARD
    rel_label: str = "HAS_APT_REPOSITORY"
    properties: ProxmoxNodeSoftwareRelProperties = ProxmoxNodeSoftwareRelProperties()


@dataclass(frozen=True)
class ProxmoxAPTRepositorySchema(CartographyNodeSchema):
    """An APT repository configured on a Proxmox VE node."""

    label: str = "ProxmoxAPTRepository"
    properties: ProxmoxAPTRepositoryNodeProperties = (
        ProxmoxAPTRepositoryNodeProperties()
    )
    sub_resource_relationship: ProxmoxAPTRepositoryToClusterRel = (
        ProxmoxAPTRepositoryToClusterRel()
    )
    other_relationships: OtherRelationships = OtherRelationships(
        [ProxmoxAPTRepositoryToNodeRel()],
    )


# ============================================================================
# ProxmoxSubscription
# ============================================================================


@dataclass(frozen=True)
class ProxmoxSubscriptionNodeProperties(CartographyNodeProperties):
    id: PropertyRef = PropertyRef(
        "id",
        description="Subscription ID in the form cluster_id/node_name:subscription.",
    )
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)
    cluster_id: PropertyRef = PropertyRef(
        "cluster_id",
        description="ID of the Proxmox cluster the subscription belongs to.",
    )
    node_name: PropertyRef = PropertyRef(
        "node_name",
        description="Name of the Proxmox node the subscription is set on.",
    )
    status: PropertyRef = PropertyRef(
        "status",
        description="Subscription status, such as active, notfound or expired.",
    )
    level: PropertyRef = PropertyRef(
        "level",
        description="Short code of the subscription level, such as c, b, s or p.",
    )
    productname: PropertyRef = PropertyRef(
        "productname",
        description="Product name of the subscription.",
    )
    regdate: PropertyRef = PropertyRef(
        "regdate",
        description="Registration date of the subscription.",
    )
    nextduedate: PropertyRef = PropertyRef(
        "nextduedate",
        description="Next due date of the subscription.",
    )
    checktime: PropertyRef = PropertyRef(
        "checktime",
        description="Unix timestamp of the last subscription check.",
    )
    sockets: PropertyRef = PropertyRef(
        "sockets",
        description="Number of CPU sockets of the node.",
    )
    message: PropertyRef = PropertyRef(
        "message",
        description="Human readable subscription status message.",
    )
    key_suffix: PropertyRef = PropertyRef(
        "key_suffix",
        description=(
            "Last four characters of the subscription key. The full key and "
            "the offline signature are never stored."
        ),
    )


@dataclass(frozen=True)
class ProxmoxSubscriptionToClusterRel(CartographyRelSchema):
    """The cluster contains the subscription."""

    target_node_label: str = "ProxmoxCluster"
    target_node_matcher: TargetNodeMatcher = make_target_node_matcher(
        {"id": PropertyRef("CLUSTER_ID", set_in_kwargs=True)},
    )
    direction: LinkDirection = LinkDirection.INWARD
    rel_label: str = "RESOURCE"
    properties: ProxmoxNodeSoftwareRelProperties = ProxmoxNodeSoftwareRelProperties()


@dataclass(frozen=True)
class ProxmoxSubscriptionToNodeRel(CartographyRelSchema):
    """The Proxmox node has the subscription."""

    target_node_label: str = "ProxmoxNode"
    target_node_matcher: TargetNodeMatcher = make_target_node_matcher(
        {"id": PropertyRef("node_id")},
    )
    direction: LinkDirection = LinkDirection.INWARD
    rel_label: str = "HAS_SUBSCRIPTION"
    properties: ProxmoxNodeSoftwareRelProperties = ProxmoxNodeSoftwareRelProperties()


@dataclass(frozen=True)
class ProxmoxSubscriptionSchema(CartographyNodeSchema):
    """The Proxmox VE support subscription of a node."""

    label: str = "ProxmoxSubscription"
    properties: ProxmoxSubscriptionNodeProperties = ProxmoxSubscriptionNodeProperties()
    sub_resource_relationship: ProxmoxSubscriptionToClusterRel = (
        ProxmoxSubscriptionToClusterRel()
    )
    other_relationships: OtherRelationships = OtherRelationships(
        [ProxmoxSubscriptionToNodeRel()],
    )
