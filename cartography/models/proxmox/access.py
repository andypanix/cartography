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
        description="User ID in the form cluster_id/user@realm.",
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
    realm: PropertyRef = PropertyRef(
        "realm",
        description="Authentication realm of the user, the part of userid after @.",
    )
    realm_type: PropertyRef = PropertyRef(
        "realm_type",
        description="Type of the user's realm, such as pam, pve, ldap, ad, or openid.",
    )
    tfa_enabled: PropertyRef = PropertyRef(
        "tfa_enabled",
        description="Whether the user has at least one enabled second factor.",
    )
    tfa_types: PropertyRef = PropertyRef(
        "tfa_types",
        description=(
            "Types of the user's enabled second factors: totp, u2f, webauthn, "
            "recovery, or yubico."
        ),
    )
    totp_locked: PropertyRef = PropertyRef(
        "totp_locked",
        description=(
            "Whether the user is locked out of TOTP factors after too many "
            "failed attempts."
        ),
    )
    tfa_locked_until: PropertyRef = PropertyRef(
        "tfa_locked_until",
        description=(
            "Unix timestamp until which the user is locked out of all second "
            "factors, if a lock is active."
        ),
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
        {"id": PropertyRef("group_ids", one_to_many=True)},
    )
    direction: LinkDirection = LinkDirection.OUTWARD
    rel_label: str = "MEMBER_OF_GROUP"
    properties: ProxmoxUserToGroupRelProperties = ProxmoxUserToGroupRelProperties()


@dataclass(frozen=True)
class ProxmoxUserToRealmRelProperties(CartographyRelProperties):
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)


@dataclass(frozen=True)
class ProxmoxUserToRealmRel(CartographyRelSchema):
    """The user authenticates through the realm."""

    target_node_label: str = "ProxmoxRealm"
    target_node_matcher: TargetNodeMatcher = make_target_node_matcher(
        {"id": PropertyRef("realm_id")},
    )
    direction: LinkDirection = LinkDirection.OUTWARD
    rel_label: str = "IN_REALM"
    properties: ProxmoxUserToRealmRelProperties = ProxmoxUserToRealmRelProperties()


@dataclass(frozen=True)
class ProxmoxUserSchema(CartographyNodeSchema):
    """A user account in a Proxmox VE cluster."""

    label: str = "ProxmoxUser"
    properties: ProxmoxUserNodeProperties = ProxmoxUserNodeProperties()
    sub_resource_relationship: ProxmoxUserToClusterRel = ProxmoxUserToClusterRel()
    other_relationships: OtherRelationships = OtherRelationships(
        [ProxmoxUserToGroupRel(), ProxmoxUserToRealmRel()],
    )


# ============================================================================
# API tokens
# ============================================================================


@dataclass(frozen=True)
class ProxmoxAPITokenNodeProperties(CartographyNodeProperties):
    id: PropertyRef = PropertyRef(
        "id",
        description="API token ID in the form cluster_id/user@realm!tokenid.",
    )
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)
    full_tokenid: PropertyRef = PropertyRef(
        "full_tokenid",
        extra_index=True,
        description="Full API token ID in the form user@realm!tokenid, as used in ACLs.",
    )
    tokenid: PropertyRef = PropertyRef(
        "tokenid",
        description="Token identifier, unique per user.",
    )
    userid: PropertyRef = PropertyRef(
        "userid",
        description="ID of the user that owns the token, in the form user@realm.",
    )
    cluster_id: PropertyRef = PropertyRef(
        "cluster_id",
        description="ID of the Proxmox cluster the token belongs to.",
    )
    comment: PropertyRef = PropertyRef(
        "comment",
        description="Free-form comment on the token.",
    )
    expire: PropertyRef = PropertyRef(
        "expire",
        description=(
            "Token expiration date as a Unix timestamp; 0 means no expiration. "
            "Empty when the API omits it, in which case the user's expiration applies."
        ),
    )
    privsep: PropertyRef = PropertyRef(
        "privsep",
        description=(
            "Whether privilege separation is on. When true the token is limited "
            "to its own ACLs, intersected with the user's permissions; when false "
            "the token has all permissions of its user."
        ),
    )


@dataclass(frozen=True)
class ProxmoxAPITokenToClusterRelProperties(CartographyRelProperties):
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)


@dataclass(frozen=True)
class ProxmoxAPITokenToClusterRel(CartographyRelSchema):
    """The cluster contains the API token."""

    target_node_label: str = "ProxmoxCluster"
    target_node_matcher: TargetNodeMatcher = make_target_node_matcher(
        {"id": PropertyRef("CLUSTER_ID", set_in_kwargs=True)},
    )
    direction: LinkDirection = LinkDirection.INWARD
    rel_label: str = "RESOURCE"
    properties: ProxmoxAPITokenToClusterRelProperties = (
        ProxmoxAPITokenToClusterRelProperties()
    )


@dataclass(frozen=True)
class ProxmoxAPITokenToUserRelProperties(CartographyRelProperties):
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)


@dataclass(frozen=True)
class ProxmoxAPITokenToUserRel(CartographyRelSchema):
    """The user owns the API token."""

    target_node_label: str = "ProxmoxUser"
    target_node_matcher: TargetNodeMatcher = make_target_node_matcher(
        {"id": PropertyRef("user_id")},
    )
    direction: LinkDirection = LinkDirection.INWARD
    rel_label: str = "HAS_API_TOKEN"
    properties: ProxmoxAPITokenToUserRelProperties = (
        ProxmoxAPITokenToUserRelProperties()
    )


@dataclass(frozen=True)
class ProxmoxAPITokenSchema(CartographyNodeSchema):
    """An API token of a Proxmox VE user."""

    label: str = "ProxmoxAPIToken"
    properties: ProxmoxAPITokenNodeProperties = ProxmoxAPITokenNodeProperties()
    sub_resource_relationship: ProxmoxAPITokenToClusterRel = (
        ProxmoxAPITokenToClusterRel()
    )
    other_relationships: OtherRelationships = OtherRelationships(
        [ProxmoxAPITokenToUserRel()],
    )


# ============================================================================
# Second factors
# ============================================================================


@dataclass(frozen=True)
class ProxmoxTFAFactorNodeProperties(CartographyNodeProperties):
    id: PropertyRef = PropertyRef(
        "id",
        description="Second factor ID in the form cluster_id/user@realm/factor_id.",
    )
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)
    factor_id: PropertyRef = PropertyRef(
        "factor_id",
        description="ID of the second factor entry, unique per user.",
    )
    userid: PropertyRef = PropertyRef(
        "userid",
        description="ID of the user the factor belongs to, in the form user@realm.",
    )
    cluster_id: PropertyRef = PropertyRef(
        "cluster_id",
        description="ID of the Proxmox cluster the factor belongs to.",
    )
    type: PropertyRef = PropertyRef(
        "type",
        description="Factor type: totp, u2f, webauthn, recovery, or yubico.",
    )
    description: PropertyRef = PropertyRef(
        "description",
        description="Description the user gave the factor.",
    )
    enable: PropertyRef = PropertyRef(
        "enable",
        description="Whether the factor is enabled.",
    )
    created: PropertyRef = PropertyRef(
        "created",
        description="Creation time of the factor as a Unix timestamp.",
    )


@dataclass(frozen=True)
class ProxmoxTFAFactorToClusterRelProperties(CartographyRelProperties):
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)


@dataclass(frozen=True)
class ProxmoxTFAFactorToClusterRel(CartographyRelSchema):
    """The cluster contains the second factor."""

    target_node_label: str = "ProxmoxCluster"
    target_node_matcher: TargetNodeMatcher = make_target_node_matcher(
        {"id": PropertyRef("CLUSTER_ID", set_in_kwargs=True)},
    )
    direction: LinkDirection = LinkDirection.INWARD
    rel_label: str = "RESOURCE"
    properties: ProxmoxTFAFactorToClusterRelProperties = (
        ProxmoxTFAFactorToClusterRelProperties()
    )


@dataclass(frozen=True)
class ProxmoxTFAFactorToUserRelProperties(CartographyRelProperties):
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)


@dataclass(frozen=True)
class ProxmoxTFAFactorToUserRel(CartographyRelSchema):
    """The user has registered the second factor."""

    target_node_label: str = "ProxmoxUser"
    target_node_matcher: TargetNodeMatcher = make_target_node_matcher(
        {"id": PropertyRef("user_id")},
    )
    direction: LinkDirection = LinkDirection.INWARD
    rel_label: str = "HAS_TFA_FACTOR"
    properties: ProxmoxTFAFactorToUserRelProperties = (
        ProxmoxTFAFactorToUserRelProperties()
    )


@dataclass(frozen=True)
class ProxmoxTFAFactorSchema(CartographyNodeSchema):
    """A second authentication factor of a Proxmox VE user, without any secret."""

    label: str = "ProxmoxTFAFactor"
    properties: ProxmoxTFAFactorNodeProperties = ProxmoxTFAFactorNodeProperties()
    sub_resource_relationship: ProxmoxTFAFactorToClusterRel = (
        ProxmoxTFAFactorToClusterRel()
    )
    other_relationships: OtherRelationships = OtherRelationships(
        [ProxmoxTFAFactorToUserRel()],
    )


# ============================================================================
# Realms and realm sync jobs
# ============================================================================


@dataclass(frozen=True)
class ProxmoxRealmNodeProperties(CartographyNodeProperties):
    id: PropertyRef = PropertyRef(
        "id",
        description="Realm ID in the form cluster_id/realm.",
    )
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)
    realm: PropertyRef = PropertyRef(
        "realm",
        extra_index=True,
        description="Realm name, the part of a user ID after @.",
    )
    cluster_id: PropertyRef = PropertyRef(
        "cluster_id",
        description="ID of the Proxmox cluster the realm belongs to.",
    )
    type: PropertyRef = PropertyRef(
        "type",
        description="Realm type: pam, pve, ldap, ad, or openid.",
    )
    comment: PropertyRef = PropertyRef(
        "comment",
        description="Comment shown for the realm on the login screen.",
    )
    tfa: PropertyRef = PropertyRef(
        "tfa",
        description="Second factor the realm enforces: yubico or oath. Empty if none.",
    )
    default: PropertyRef = PropertyRef(
        "default",
        description="Whether the realm is preselected on the login screen.",
    )
    server1: PropertyRef = PropertyRef(
        "server1",
        description="Primary LDAP or Active Directory server.",
    )
    server2: PropertyRef = PropertyRef(
        "server2",
        description="Fallback LDAP or Active Directory server.",
    )
    port: PropertyRef = PropertyRef(
        "port",
        description="LDAP or Active Directory server port.",
    )
    mode: PropertyRef = PropertyRef(
        "mode",
        description="LDAP protocol mode: ldap, ldaps, or ldap+starttls.",
    )
    verify: PropertyRef = PropertyRef(
        "verify",
        description="Whether the LDAP server certificate is verified.",
    )
    base_dn: PropertyRef = PropertyRef(
        "base_dn",
        description="LDAP base DN users are searched under.",
    )
    bind_dn: PropertyRef = PropertyRef(
        "bind_dn",
        description="LDAP DN the realm binds as. The bind password is never read.",
    )
    domain: PropertyRef = PropertyRef(
        "domain",
        description="Active Directory domain name.",
    )
    issuer_url: PropertyRef = PropertyRef(
        "issuer_url",
        description="OpenID Connect issuer URL.",
    )
    client_id: PropertyRef = PropertyRef(
        "client_id",
        description="OpenID Connect client ID. The client key is never stored.",
    )
    autocreate: PropertyRef = PropertyRef(
        "autocreate",
        description="Whether users are created automatically on first login.",
    )


@dataclass(frozen=True)
class ProxmoxRealmToClusterRelProperties(CartographyRelProperties):
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)


@dataclass(frozen=True)
class ProxmoxRealmToClusterRel(CartographyRelSchema):
    """The cluster contains the authentication realm."""

    target_node_label: str = "ProxmoxCluster"
    target_node_matcher: TargetNodeMatcher = make_target_node_matcher(
        {"id": PropertyRef("CLUSTER_ID", set_in_kwargs=True)},
    )
    direction: LinkDirection = LinkDirection.INWARD
    rel_label: str = "RESOURCE"
    properties: ProxmoxRealmToClusterRelProperties = (
        ProxmoxRealmToClusterRelProperties()
    )


@dataclass(frozen=True)
class ProxmoxRealmSchema(CartographyNodeSchema):
    """An authentication realm (domain) of a Proxmox VE cluster."""

    label: str = "ProxmoxRealm"
    properties: ProxmoxRealmNodeProperties = ProxmoxRealmNodeProperties()
    sub_resource_relationship: ProxmoxRealmToClusterRel = ProxmoxRealmToClusterRel()


@dataclass(frozen=True)
class ProxmoxRealmSyncJobNodeProperties(CartographyNodeProperties):
    id: PropertyRef = PropertyRef(
        "id",
        description="Realm sync job ID in the form cluster_id/job_id.",
    )
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)
    job_id: PropertyRef = PropertyRef(
        "job_id",
        description="Job ID as returned by the Proxmox VE API.",
    )
    cluster_id: PropertyRef = PropertyRef(
        "cluster_id",
        description="ID of the Proxmox cluster the job belongs to.",
    )
    realm: PropertyRef = PropertyRef(
        "realm",
        description="Realm the job synchronizes users and groups from.",
    )
    enabled: PropertyRef = PropertyRef(
        "enabled",
        description="Whether the job is enabled.",
    )
    schedule: PropertyRef = PropertyRef(
        "schedule",
        description="Sync schedule in systemd calendar event format.",
    )
    scope: PropertyRef = PropertyRef(
        "scope",
        description="What the job synchronizes: users, groups, or both.",
    )
    remove_vanished: PropertyRef = PropertyRef(
        "remove_vanished",
        description=(
            "What the job removes when an entry vanishes from the source: a "
            "semicolon-separated list of acl, properties, and entry, or none."
        ),
    )
    comment: PropertyRef = PropertyRef(
        "comment",
        description="Free-form comment on the job.",
    )
    last_run: PropertyRef = PropertyRef(
        "last_run",
        description="Last run time as a Unix timestamp.",
    )
    next_run: PropertyRef = PropertyRef(
        "next_run",
        description="Next planned run time as a Unix timestamp.",
    )


@dataclass(frozen=True)
class ProxmoxRealmSyncJobToClusterRelProperties(CartographyRelProperties):
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)


@dataclass(frozen=True)
class ProxmoxRealmSyncJobToClusterRel(CartographyRelSchema):
    """The cluster contains the realm sync job."""

    target_node_label: str = "ProxmoxCluster"
    target_node_matcher: TargetNodeMatcher = make_target_node_matcher(
        {"id": PropertyRef("CLUSTER_ID", set_in_kwargs=True)},
    )
    direction: LinkDirection = LinkDirection.INWARD
    rel_label: str = "RESOURCE"
    properties: ProxmoxRealmSyncJobToClusterRelProperties = (
        ProxmoxRealmSyncJobToClusterRelProperties()
    )


@dataclass(frozen=True)
class ProxmoxRealmSyncJobToRealmRelProperties(CartographyRelProperties):
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)


@dataclass(frozen=True)
class ProxmoxRealmSyncJobToRealmRel(CartographyRelSchema):
    """The job synchronizes users and groups from the realm."""

    target_node_label: str = "ProxmoxRealm"
    target_node_matcher: TargetNodeMatcher = make_target_node_matcher(
        {"id": PropertyRef("realm_id")},
    )
    direction: LinkDirection = LinkDirection.OUTWARD
    rel_label: str = "SYNCS"
    properties: ProxmoxRealmSyncJobToRealmRelProperties = (
        ProxmoxRealmSyncJobToRealmRelProperties()
    )


@dataclass(frozen=True)
class ProxmoxRealmSyncJobSchema(CartographyNodeSchema):
    """A scheduled job that synchronizes users and groups from an LDAP or Active Directory realm."""

    label: str = "ProxmoxRealmSyncJob"
    properties: ProxmoxRealmSyncJobNodeProperties = ProxmoxRealmSyncJobNodeProperties()
    sub_resource_relationship: ProxmoxRealmSyncJobToClusterRel = (
        ProxmoxRealmSyncJobToClusterRel()
    )
    other_relationships: OtherRelationships = OtherRelationships(
        [ProxmoxRealmSyncJobToRealmRel()],
    )


@dataclass(frozen=True)
class ProxmoxGroupNodeProperties(CartographyNodeProperties):
    id: PropertyRef = PropertyRef(
        "id",
        description="Group ID in the form cluster_id/groupid.",
    )
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)
    groupid: PropertyRef = PropertyRef(
        "groupid",
        extra_index=True,
        description="Group ID as returned by the Proxmox VE API.",
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
    id: PropertyRef = PropertyRef(
        "id",
        description="Role ID in the form cluster_id/roleid.",
    )
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)
    roleid: PropertyRef = PropertyRef(
        "roleid",
        extra_index=True,
        description="Role ID as returned by the Proxmox VE API.",
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
        description="ACL entry ID in the form cluster_id/path:ugid:roleid.",
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
        description="Type of principal: user, token, or group.",
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
        {"id": PropertyRef("target_role_id")},
    )
    direction: LinkDirection = LinkDirection.OUTWARD
    rel_label: str = "GRANTS_ROLE"
    properties: ProxmoxACLToRoleRelProperties = ProxmoxACLToRoleRelProperties()


@dataclass(frozen=True)
class ProxmoxACLToUserRelProperties(CartographyRelProperties):
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)


@dataclass(frozen=True)
class ProxmoxACLToUserRel(CartographyRelSchema):
    """The ACL entry applies to the user."""

    target_node_label: str = "ProxmoxUser"
    target_node_matcher: TargetNodeMatcher = make_target_node_matcher(
        {"id": PropertyRef("target_user_id")},
    )
    direction: LinkDirection = LinkDirection.OUTWARD
    rel_label: str = "APPLIES_TO_USER"
    properties: ProxmoxACLToUserRelProperties = ProxmoxACLToUserRelProperties()


@dataclass(frozen=True)
class ProxmoxACLToAPITokenRelProperties(CartographyRelProperties):
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)


@dataclass(frozen=True)
class ProxmoxACLToAPITokenRel(CartographyRelSchema):
    """The ACL entry applies to the API token."""

    target_node_label: str = "ProxmoxAPIToken"
    target_node_matcher: TargetNodeMatcher = make_target_node_matcher(
        {"id": PropertyRef("target_token_id")},
    )
    direction: LinkDirection = LinkDirection.OUTWARD
    rel_label: str = "APPLIES_TO_TOKEN"
    properties: ProxmoxACLToAPITokenRelProperties = ProxmoxACLToAPITokenRelProperties()


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
            ProxmoxACLToAPITokenRel(),
            ProxmoxACLToGroupRel(),
            ProxmoxACLToVMRel(),
            ProxmoxACLToStorageRel(),
            ProxmoxACLToPoolRel(),
            ProxmoxACLToNodeRel(),
            ProxmoxACLToClusterAccessRel(),
        ],
    )
