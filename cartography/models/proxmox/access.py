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
class ProxmoxUserNodeProperties(CartographyNodeProperties):
    id: PropertyRef = PropertyRef(
        "id",
        description="User ID in the form user@realm.",
    )
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)
    userid: PropertyRef = PropertyRef(
        "userid",
        extra_index=True,
        description="User ID in the form user@realm.",
    )
    cluster_id: PropertyRef = PropertyRef(
        "cluster_id",
        description="ID of the Proxmox cluster the user belongs to.",
    )
    enable: PropertyRef = PropertyRef(
        "enable",
        description="Whether the user account is enabled.",
    )
    expire: PropertyRef = PropertyRef(
        "expire",
        description="Account expiration date as a Unix timestamp; 0 means no expiration.",
    )
    firstname: PropertyRef = PropertyRef(
        "firstname",
        description="First name of the user.",
    )
    lastname: PropertyRef = PropertyRef(
        "lastname",
        description="Last name of the user.",
    )
    email: PropertyRef = PropertyRef(
        "email",
        extra_index=True,
        description="Email address of the user.",
    )
    comment: PropertyRef = PropertyRef(
        "comment",
        description="Free-form comment on the user account.",
    )
    groups: PropertyRef = PropertyRef(
        "groups",
        description="IDs of the groups the user is a member of.",
    )
    tokens: PropertyRef = PropertyRef(
        "tokens",
        description="API tokens of the user, as returned by the Proxmox API.",
    )


@dataclass(frozen=True)
class ProxmoxUserToClusterRelProperties(CartographyRelProperties):
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)


@dataclass(frozen=True)
class ProxmoxUserToClusterRel(CartographyRelSchema):
    """The cluster contains the user."""

    target_node_label: str = "ProxmoxCluster"
    target_node_matcher: TargetNodeMatcher = make_target_node_matcher(
        {"id": PropertyRef("CLUSTER_ID", set_in_kwargs=True)},
    )
    direction: LinkDirection = LinkDirection.INWARD
    rel_label: str = "RESOURCE"
    properties: ProxmoxUserToClusterRelProperties = ProxmoxUserToClusterRelProperties()


@dataclass(frozen=True)
class ProxmoxUserToGroupRelProperties(CartographyRelProperties):
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)


@dataclass(frozen=True)
class ProxmoxUserToGroupRel(CartographyRelSchema):
    """The user is a member of the group."""

    target_node_label: str = "ProxmoxGroup"
    target_node_matcher: TargetNodeMatcher = make_target_node_matcher(
        {"groupid": PropertyRef("groups", one_to_many=True)},
    )
    direction: LinkDirection = LinkDirection.OUTWARD
    rel_label: str = "MEMBER_OF_GROUP"
    properties: ProxmoxUserToGroupRelProperties = ProxmoxUserToGroupRelProperties()


@dataclass(frozen=True)
class ProxmoxUserSchema(CartographyNodeSchema):
    """A user account in a Proxmox VE cluster."""

    label: str = "ProxmoxUser"
    properties: ProxmoxUserNodeProperties = ProxmoxUserNodeProperties()
    sub_resource_relationship: ProxmoxUserToClusterRel = ProxmoxUserToClusterRel()
    other_relationships: OtherRelationships = OtherRelationships(
        [ProxmoxUserToGroupRel()],
    )


@dataclass(frozen=True)
class ProxmoxGroupNodeProperties(CartographyNodeProperties):
    id: PropertyRef = PropertyRef("id", description="Group ID.")
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)
    groupid: PropertyRef = PropertyRef(
        "groupid",
        extra_index=True,
        description="Group ID.",
    )
    cluster_id: PropertyRef = PropertyRef(
        "cluster_id",
        description="ID of the Proxmox cluster the group belongs to.",
    )
    comment: PropertyRef = PropertyRef(
        "comment",
        description="Free-form comment on the group.",
    )


@dataclass(frozen=True)
class ProxmoxGroupToClusterRelProperties(CartographyRelProperties):
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)


@dataclass(frozen=True)
class ProxmoxGroupToClusterRel(CartographyRelSchema):
    """The cluster contains the group."""

    target_node_label: str = "ProxmoxCluster"
    target_node_matcher: TargetNodeMatcher = make_target_node_matcher(
        {"id": PropertyRef("CLUSTER_ID", set_in_kwargs=True)},
    )
    direction: LinkDirection = LinkDirection.INWARD
    rel_label: str = "RESOURCE"
    properties: ProxmoxGroupToClusterRelProperties = (
        ProxmoxGroupToClusterRelProperties()
    )


@dataclass(frozen=True)
class ProxmoxGroupSchema(CartographyNodeSchema):
    """A user group in a Proxmox VE cluster."""

    label: str = "ProxmoxGroup"
    properties: ProxmoxGroupNodeProperties = ProxmoxGroupNodeProperties()
    sub_resource_relationship: ProxmoxGroupToClusterRel = ProxmoxGroupToClusterRel()


@dataclass(frozen=True)
class ProxmoxRoleNodeProperties(CartographyNodeProperties):
    id: PropertyRef = PropertyRef("id", description="Role ID.")
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)
    roleid: PropertyRef = PropertyRef(
        "roleid",
        extra_index=True,
        description="Role ID.",
    )
    cluster_id: PropertyRef = PropertyRef(
        "cluster_id",
        description="ID of the Proxmox cluster the role belongs to.",
    )
    privs: PropertyRef = PropertyRef(
        "privs",
        description="Privileges granted by the role.",
    )
    special: PropertyRef = PropertyRef(
        "special",
        description="Whether the role is a built-in role.",
    )


@dataclass(frozen=True)
class ProxmoxRoleToClusterRelProperties(CartographyRelProperties):
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)


@dataclass(frozen=True)
class ProxmoxRoleToClusterRel(CartographyRelSchema):
    """The cluster contains the role."""

    target_node_label: str = "ProxmoxCluster"
    target_node_matcher: TargetNodeMatcher = make_target_node_matcher(
        {"id": PropertyRef("CLUSTER_ID", set_in_kwargs=True)},
    )
    direction: LinkDirection = LinkDirection.INWARD
    rel_label: str = "RESOURCE"
    properties: ProxmoxRoleToClusterRelProperties = ProxmoxRoleToClusterRelProperties()


@dataclass(frozen=True)
class ProxmoxRoleSchema(CartographyNodeSchema):
    """A permission role in a Proxmox VE cluster."""

    label: str = "ProxmoxRole"
    properties: ProxmoxRoleNodeProperties = ProxmoxRoleNodeProperties()
    sub_resource_relationship: ProxmoxRoleToClusterRel = ProxmoxRoleToClusterRel()


@dataclass(frozen=True)
class ProxmoxACLNodeProperties(CartographyNodeProperties):
    id: PropertyRef = PropertyRef(
        "id",
        description="ACL entry ID in the form path:ugid:roleid.",
    )
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)
    path: PropertyRef = PropertyRef(
        "path",
        extra_index=True,
        description="Object path the ACL entry applies to, such as / or /vms/100.",
    )
    cluster_id: PropertyRef = PropertyRef(
        "cluster_id",
        description="ID of the Proxmox cluster the ACL entry belongs to.",
    )
    roleid: PropertyRef = PropertyRef(
        "roleid",
        description="ID of the role granted by the ACL entry.",
    )
    ugid: PropertyRef = PropertyRef(
        "ugid",
        extra_index=True,
        description="User, API token, or group ID the ACL entry grants the role to.",
    )
    propagate: PropertyRef = PropertyRef(
        "propagate",
        description="Whether the ACL entry propagates to child paths.",
    )
    principal_type: PropertyRef = PropertyRef(
        "principal_type",
        description="Type of principal: user or group.",
    )
    resource_type: PropertyRef = PropertyRef(
        "resource_type",
        description=(
            "Resource type parsed from the path: cluster, vm, storage, pool, "
            "node, access, or unknown."
        ),
    )
    resource_id: PropertyRef = PropertyRef(
        "resource_id",
        description="Resource ID parsed from the path, when the path names a single resource.",
    )


@dataclass(frozen=True)
class ProxmoxACLToClusterRelProperties(CartographyRelProperties):
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)


@dataclass(frozen=True)
class ProxmoxACLToClusterRel(CartographyRelSchema):
    """The cluster contains the ACL entry."""

    target_node_label: str = "ProxmoxCluster"
    target_node_matcher: TargetNodeMatcher = make_target_node_matcher(
        {"id": PropertyRef("CLUSTER_ID", set_in_kwargs=True)},
    )
    direction: LinkDirection = LinkDirection.INWARD
    rel_label: str = "RESOURCE"
    properties: ProxmoxACLToClusterRelProperties = ProxmoxACLToClusterRelProperties()


@dataclass(frozen=True)
class ProxmoxACLToRoleRelProperties(CartographyRelProperties):
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)


@dataclass(frozen=True)
class ProxmoxACLToRoleRel(CartographyRelSchema):
    """The ACL entry grants the role."""

    target_node_label: str = "ProxmoxRole"
    target_node_matcher: TargetNodeMatcher = make_target_node_matcher(
        {"roleid": PropertyRef("roleid")},
    )
    direction: LinkDirection = LinkDirection.OUTWARD
    rel_label: str = "GRANTS_ROLE"
    properties: ProxmoxACLToRoleRelProperties = ProxmoxACLToRoleRelProperties()


@dataclass(frozen=True)
class ProxmoxACLToUserRelProperties(CartographyRelProperties):
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)


@dataclass(frozen=True)
class ProxmoxACLToUserRel(CartographyRelSchema):
    """The ACL entry applies to the user, or to the user that owns the API token."""

    target_node_label: str = "ProxmoxUser"
    target_node_matcher: TargetNodeMatcher = make_target_node_matcher(
        {"id": PropertyRef("target_user_id")},
    )
    direction: LinkDirection = LinkDirection.OUTWARD
    rel_label: str = "APPLIES_TO_USER"
    properties: ProxmoxACLToUserRelProperties = ProxmoxACLToUserRelProperties()


@dataclass(frozen=True)
class ProxmoxACLToGroupRelProperties(CartographyRelProperties):
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)


@dataclass(frozen=True)
class ProxmoxACLToGroupRel(CartographyRelSchema):
    """The ACL entry applies to the group."""

    target_node_label: str = "ProxmoxGroup"
    target_node_matcher: TargetNodeMatcher = make_target_node_matcher(
        {"id": PropertyRef("target_group_id")},
    )
    direction: LinkDirection = LinkDirection.OUTWARD
    rel_label: str = "APPLIES_TO_GROUP"
    properties: ProxmoxACLToGroupRelProperties = ProxmoxACLToGroupRelProperties()


@dataclass(frozen=True)
class ProxmoxACLToVMRelProperties(CartographyRelProperties):
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)


@dataclass(frozen=True)
class ProxmoxACLToVMRel(CartographyRelSchema):
    """The ACL entry grants access to the VM or container of the same cluster."""

    target_node_label: str = "ProxmoxVM"
    target_node_matcher: TargetNodeMatcher = make_target_node_matcher(
        {
            "vmid": PropertyRef("target_vmid"),
            "cluster_id": PropertyRef("CLUSTER_ID", set_in_kwargs=True),
        },
    )
    direction: LinkDirection = LinkDirection.OUTWARD
    rel_label: str = "GRANTS_ACCESS_TO"
    properties: ProxmoxACLToVMRelProperties = ProxmoxACLToVMRelProperties()


@dataclass(frozen=True)
class ProxmoxACLToStorageRelProperties(CartographyRelProperties):
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)


@dataclass(frozen=True)
class ProxmoxACLToStorageRel(CartographyRelSchema):
    """The ACL entry grants access to the storage."""

    target_node_label: str = "ProxmoxStorage"
    target_node_matcher: TargetNodeMatcher = make_target_node_matcher(
        {"id": PropertyRef("target_storage_id")},
    )
    direction: LinkDirection = LinkDirection.OUTWARD
    rel_label: str = "GRANTS_ACCESS_TO"
    properties: ProxmoxACLToStorageRelProperties = ProxmoxACLToStorageRelProperties()


@dataclass(frozen=True)
class ProxmoxACLToPoolRelProperties(CartographyRelProperties):
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)


@dataclass(frozen=True)
class ProxmoxACLToPoolRel(CartographyRelSchema):
    """The ACL entry grants access to the resource pool."""

    target_node_label: str = "ProxmoxPool"
    target_node_matcher: TargetNodeMatcher = make_target_node_matcher(
        {"id": PropertyRef("target_pool_id")},
    )
    direction: LinkDirection = LinkDirection.OUTWARD
    rel_label: str = "GRANTS_ACCESS_TO"
    properties: ProxmoxACLToPoolRelProperties = ProxmoxACLToPoolRelProperties()


@dataclass(frozen=True)
class ProxmoxACLToNodeRelProperties(CartographyRelProperties):
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)


@dataclass(frozen=True)
class ProxmoxACLToNodeRel(CartographyRelSchema):
    """The ACL entry grants access to the cluster node."""

    target_node_label: str = "ProxmoxNode"
    target_node_matcher: TargetNodeMatcher = make_target_node_matcher(
        {"id": PropertyRef("target_node_id")},
    )
    direction: LinkDirection = LinkDirection.OUTWARD
    rel_label: str = "GRANTS_ACCESS_TO"
    properties: ProxmoxACLToNodeRelProperties = ProxmoxACLToNodeRelProperties()


@dataclass(frozen=True)
class ProxmoxACLToClusterAccessRelProperties(CartographyRelProperties):
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)


@dataclass(frozen=True)
class ProxmoxACLToClusterAccessRel(CartographyRelSchema):
    """The ACL entry on the root path grants access to the whole cluster."""

    target_node_label: str = "ProxmoxCluster"
    target_node_matcher: TargetNodeMatcher = make_target_node_matcher(
        {"id": PropertyRef("target_cluster_id")},
    )
    direction: LinkDirection = LinkDirection.OUTWARD
    rel_label: str = "GRANTS_ACCESS_TO"
    properties: ProxmoxACLToClusterAccessRelProperties = (
        ProxmoxACLToClusterAccessRelProperties()
    )


@dataclass(frozen=True)
class ProxmoxACLSchema(CartographyNodeSchema):
    """An access control list entry granting a role on a path in a Proxmox VE cluster."""

    label: str = "ProxmoxACL"
    properties: ProxmoxACLNodeProperties = ProxmoxACLNodeProperties()
    sub_resource_relationship: ProxmoxACLToClusterRel = ProxmoxACLToClusterRel()
    other_relationships: OtherRelationships = OtherRelationships(
        [
            ProxmoxACLToRoleRel(),
            ProxmoxACLToUserRel(),
            ProxmoxACLToGroupRel(),
            ProxmoxACLToVMRel(),
            ProxmoxACLToStorageRel(),
            ProxmoxACLToPoolRel(),
            ProxmoxACLToNodeRel(),
            ProxmoxACLToClusterAccessRel(),
        ],
    )
