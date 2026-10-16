"""
Sync Proxmox access control (users, groups, roles, ACLs).

Follows Cartography's Get → Transform → Load pattern.
"""

import logging
from typing import Any

import neo4j

from cartography.client.core.tx import load
from cartography.intel.proxmox.util import cluster_scoped_id
from cartography.intel.proxmox.util import proxmox_api_retry
from cartography.models.proxmox.access import ProxmoxACLSchema
from cartography.models.proxmox.access import ProxmoxGroupSchema
from cartography.models.proxmox.access import ProxmoxRoleSchema
from cartography.models.proxmox.access import ProxmoxUserSchema
from cartography.util import timeit

logger = logging.getLogger(__name__)


# ============================================================================
# GET functions - retrieve data from Proxmox API
# ============================================================================


@timeit
@proxmox_api_retry
def get_users(proxmox_client: Any) -> list[dict[str, Any]]:
    """
    Get all users in the cluster.

    :param proxmox_client: Proxmox API client
    :return: List of user dicts
    :raises: Exception if API call fails
    """
    return proxmox_client.access.users.get()


@timeit
@proxmox_api_retry
def get_groups(proxmox_client: Any) -> list[dict[str, Any]]:
    """
    Get all groups in the cluster.

    :param proxmox_client: Proxmox API client
    :return: List of group dicts
    :raises: Exception if API call fails
    """
    return proxmox_client.access.groups.get()


@timeit
@proxmox_api_retry
def get_group_members(
    proxmox_client: Any, groups: list[dict[str, Any]]
) -> dict[str, list[str]]:
    """
    Get group membership information for all groups.
    Returns a mapping of group_id -> list of user_ids.

    This is especially important for SSO users whose group memberships
    might not be returned in the user API endpoint.

    :param proxmox_client: Proxmox API client
    :param groups: List of group dicts from get_groups()
    :return: Dict mapping group IDs to lists of member user IDs
    :raises: Exception if API call fails
    """
    group_members: dict[str, list[str]] = {}

    for group in groups:
        groupid = group.get("groupid")
        if not groupid:
            continue

        # Get detailed group info including members
        group_detail = proxmox_client.access.groups(groupid).get()
        members = group_detail.get("members", [])
        if members:
            # Members is a list of user IDs
            group_members[groupid] = members
            logger.debug(f"Group {groupid} has {len(members)} members")

    return group_members


@timeit
@proxmox_api_retry
def get_roles(proxmox_client: Any) -> list[dict[str, Any]]:
    """
    Get all roles in the cluster.

    :param proxmox_client: Proxmox API client
    :return: List of role dicts
    :raises: Exception if API call fails
    """
    return proxmox_client.access.roles.get()


@timeit
@proxmox_api_retry
def get_acls(proxmox_client: Any) -> list[dict[str, Any]]:
    """
    Get all ACL entries in the cluster.

    :param proxmox_client: Proxmox API client
    :return: List of ACL dicts
    :raises: Exception if API call fails
    """
    return proxmox_client.access.acl.get()


# ============================================================================
# TRANSFORM functions - manipulate data for graph ingestion
# ============================================================================


def transform_user_data(
    users: list[dict[str, Any]],
    cluster_id: str,
    group_members: dict[str, list[str]] | None = None,
) -> list[dict[str, Any]]:
    """
    Transform user data into standard format.

    Per Cartography guidelines:
    - Use data['field'] for required fields (will raise KeyError if missing)
    - Use data.get('field') for optional fields

    :param users: Raw user data from API
    :param cluster_id: Parent cluster ID
    :param group_members: Optional dict mapping group IDs to member user IDs
                         (important for SSO users)
    :return: List of transformed user dicts
    """
    transformed_users = []

    for user in users:
        # Required field - use direct access
        userid = user["userid"]

        # Parse groups if they exist (Proxmox returns comma-separated string)
        groups = []
        groups_str = user.get("groups", "")
        if groups_str:
            groups = [g.strip() for g in groups_str.split(",") if g.strip()]

        # Enrich with group memberships from group_members data (important for SSO users)
        # SSO users often don't have groups in their user record, but groups have member lists
        if group_members:
            for groupid, members in group_members.items():
                if userid in members and groupid not in groups:
                    groups.append(groupid)
                    logger.debug(
                        f"Enriched user {userid} with group {groupid} from group membership data"
                    )

        # Parse tokens if they exist (tokens field contains list)
        tokens = user.get("tokens", [])

        transformed_users.append(
            {
                "id": cluster_scoped_id(cluster_id, userid),
                "userid": userid,
                "cluster_id": cluster_id,
                "enable": bool(user.get("enable", True)),
                "expire": user.get("expire", 0),
                "firstname": user.get("firstname"),
                "lastname": user.get("lastname"),
                "email": user.get("email"),
                "comment": user.get("comment"),
                "groups": groups,
                "group_ids": [cluster_scoped_id(cluster_id, g) for g in groups],
                "tokens": tokens,
            }
        )

    return transformed_users


def transform_group_data(
    groups: list[dict[str, Any]],
    cluster_id: str,
) -> list[dict[str, Any]]:
    """
    Transform group data into standard format.

    :param groups: Raw group data from API
    :param cluster_id: Parent cluster ID
    :return: List of transformed group dicts
    """
    transformed_groups = []

    for group in groups:
        # Required field
        groupid = group["groupid"]

        transformed_groups.append(
            {
                "id": cluster_scoped_id(cluster_id, groupid),
                "groupid": groupid,
                "cluster_id": cluster_id,
                "comment": group.get("comment"),
            }
        )

    return transformed_groups


def transform_role_data(
    roles: list[dict[str, Any]],
    cluster_id: str,
) -> list[dict[str, Any]]:
    """
    Transform role data into standard format.

    :param roles: Raw role data from API
    :param cluster_id: Parent cluster ID
    :return: List of transformed role dicts
    """
    transformed_roles = []

    for role in roles:
        # Required field
        roleid = role["roleid"]

        # Parse privileges (Proxmox returns comma-separated string)
        privs = []
        privs_str = role.get("privs", "")
        if privs_str:
            privs = [p.strip() for p in privs_str.split(",") if p.strip()]

        transformed_roles.append(
            {
                "id": cluster_scoped_id(cluster_id, roleid),
                "roleid": roleid,
                "cluster_id": cluster_id,
                "privs": privs,
                "special": bool(role.get("special", False)),
            }
        )

    return transformed_roles


def _parse_acl_path(path: str) -> tuple[str, str | None]:
    """
    Parse Proxmox ACL path to determine resource type and ID.

    Proxmox ACL paths follow patterns:
    - "/" = entire cluster
    - "/vms/<vmid>" = specific VM
    - "/storage/<storage_id>" = specific storage
    - "/pool/<pool_id>" = specific pool
    - "/nodes/<node_name>" = specific node
    - "/access" = access control itself

    :param path: ACL path
    :return: Tuple of (resource_type, resource_id)
    """
    if path == "/":
        return "cluster", None
    elif path.startswith("/vms/"):
        return "vm", path.split("/")[-1]
    elif path.startswith("/storage/"):
        return "storage", path.split("/")[-1]
    elif path.startswith("/pool/"):
        return "pool", path.split("/")[-1]
    elif path.startswith("/nodes/"):
        return "node", path.split("/")[-1]
    elif path.startswith("/access"):
        return "access", None
    else:
        # Unknown path format
        return "unknown", None


def transform_acl_data(
    acls: list[dict[str, Any]],
    cluster_id: str,
) -> list[dict[str, Any]]:
    """
    Transform ACL data into standard format.

    Parses ACL paths to determine resource types and IDs for better relationship mapping.

    :param acls: Raw ACL data from API
    :param cluster_id: Parent cluster ID
    :return: List of transformed ACL dicts
    """
    transformed_acls = []

    for acl in acls:
        # Required fields
        path = acl["path"]
        roleid = acl["roleid"]
        ugid = acl["ugid"]  # User or group ID

        # Create unique ID from path + ugid + roleid
        acl_id = cluster_scoped_id(cluster_id, f"{path}:{ugid}:{roleid}")

        # Determine principal type and extract base user ID for tokens
        # Proxmox format: groups don't have @, users are user@realm, tokens are user@realm!tokenname
        if "@" in ugid:
            principal_type = "user"
            # For API tokens (user@realm!token), extract base user (user@realm)
            base_userid = ugid.split("!")[0] if "!" in ugid else ugid
        else:
            principal_type = "group"
            base_userid = ugid

        # Parse path to extract resource type and ID
        resource_type, resource_id = _parse_acl_path(path)

        def _target(kind: str) -> str | None:
            if resource_type != kind or not resource_id:
                return None
            return cluster_scoped_id(cluster_id, resource_id)

        vm_id = resource_id if resource_type == "vm" else None

        transformed_acls.append(
            {
                "id": acl_id,
                "path": path,
                "cluster_id": cluster_id,
                "roleid": roleid,
                "ugid": ugid,
                "base_userid": base_userid,  # Base user ID without token suffix
                "propagate": bool(acl.get("propagate", True)),
                "principal_type": principal_type,
                "resource_type": resource_type,
                "resource_id": resource_id,
                # Relationship targets: each is None unless the ACL names that
                # kind of principal or resource, so only one edge per kind matches.
                "target_role_id": cluster_scoped_id(cluster_id, roleid),
                "target_user_id": (
                    cluster_scoped_id(cluster_id, base_userid)
                    if principal_type == "user"
                    else None
                ),
                "target_group_id": (
                    cluster_scoped_id(cluster_id, ugid)
                    if principal_type == "group"
                    else None
                ),
                "target_vmid": int(vm_id) if vm_id and vm_id.isdigit() else None,
                "target_storage_id": _target("storage"),
                "target_pool_id": _target("pool"),
                "target_node_id": _target("node"),
                "target_cluster_id": (
                    cluster_id if resource_type == "cluster" else None
                ),
            }
        )

    return transformed_acls


# ============================================================================
# LOAD functions - ingest data to Neo4j using modern data model
# ============================================================================


def load_users(
    neo4j_session: neo4j.Session,
    users: list[dict[str, Any]],
    cluster_id: str,
    update_tag: int,
) -> None:
    """
    Load user data into Neo4j using modern data model.

    :param neo4j_session: Neo4j session
    :param users: List of transformed user dicts
    :param cluster_id: Parent cluster ID
    :param update_tag: Sync timestamp
    """
    load(
        neo4j_session,
        ProxmoxUserSchema(),
        users,
        lastupdated=update_tag,
        CLUSTER_ID=cluster_id,
    )


def load_groups(
    neo4j_session: neo4j.Session,
    groups: list[dict[str, Any]],
    cluster_id: str,
    update_tag: int,
) -> None:
    """
    Load group data into Neo4j using modern data model.

    :param neo4j_session: Neo4j session
    :param groups: List of transformed group dicts
    :param cluster_id: Parent cluster ID
    :param update_tag: Sync timestamp
    """
    load(
        neo4j_session,
        ProxmoxGroupSchema(),
        groups,
        lastupdated=update_tag,
        CLUSTER_ID=cluster_id,
    )


def load_roles(
    neo4j_session: neo4j.Session,
    roles: list[dict[str, Any]],
    cluster_id: str,
    update_tag: int,
) -> None:
    """
    Load role data into Neo4j using modern data model.

    :param neo4j_session: Neo4j session
    :param roles: List of transformed role dicts
    :param cluster_id: Parent cluster ID
    :param update_tag: Sync timestamp
    """
    load(
        neo4j_session,
        ProxmoxRoleSchema(),
        roles,
        lastupdated=update_tag,
        CLUSTER_ID=cluster_id,
    )


def load_acls(
    neo4j_session: neo4j.Session,
    acls: list[dict[str, Any]],
    cluster_id: str,
    update_tag: int,
) -> None:
    """
    Load ACL data into Neo4j using modern data model.

    :param neo4j_session: Neo4j session
    :param acls: List of transformed ACL dicts
    :param cluster_id: Parent cluster ID
    :param update_tag: Sync timestamp
    """
    load(
        neo4j_session,
        ProxmoxACLSchema(),
        acls,
        lastupdated=update_tag,
        CLUSTER_ID=cluster_id,
    )


# ============================================================================
# SYNC function - orchestrates Get → Transform → Load
# ============================================================================


@timeit
def sync(
    neo4j_session: neo4j.Session,
    proxmox_client: Any,
    cluster_id: str,
    update_tag: int,
    common_job_parameters: dict[str, Any],
) -> None:
    """
    Sync access control configuration.

    Follows Cartography's Get → Transform → Load pattern.

    :param neo4j_session: Neo4j session
    :param proxmox_client: Proxmox API client
    :param cluster_id: Parent cluster ID
    :param update_tag: Sync timestamp
    :param common_job_parameters: Common parameters
    """
    logger.info("Syncing Proxmox access control (users, groups, roles, ACLs)")

    # GET - retrieve data from API
    users = get_users(proxmox_client)
    groups = get_groups(proxmox_client)
    roles = get_roles(proxmox_client)
    acls = get_acls(proxmox_client)

    # Get group membership information (important for SSO users)
    group_members = get_group_members(proxmox_client, groups)

    # TRANSFORM - manipulate data for ingestion
    transformed_users = transform_user_data(users, cluster_id, group_members)
    transformed_groups = transform_group_data(groups, cluster_id)
    transformed_roles = transform_role_data(roles, cluster_id)
    transformed_acls = transform_acl_data(acls, cluster_id)

    # LOAD - ingest to Neo4j
    if transformed_groups:
        load_groups(neo4j_session, transformed_groups, cluster_id, update_tag)

    if transformed_users:
        # User-to-Group relationships are now handled by the schema via one_to_many
        load_users(neo4j_session, transformed_users, cluster_id, update_tag)

    if transformed_roles:
        load_roles(neo4j_session, transformed_roles, cluster_id, update_tag)

    if transformed_acls:
        load_acls(neo4j_session, transformed_acls, cluster_id, update_tag)

    logger.info(
        "Synced %d users, %d groups, %d roles, and %d ACLs",
        len(transformed_users),
        len(transformed_groups),
        len(transformed_roles),
        len(transformed_acls),
    )
