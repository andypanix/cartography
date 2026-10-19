"""
Sync Proxmox access control: realms, realm sync jobs, users, API tokens,
second factors, groups, roles, and ACLs.

Follows Cartography's Get → Transform → Load pattern.
"""

import logging
from typing import Any

import neo4j
from proxmoxer.core import ResourceException

from cartography.client.core.tx import load
from cartography.intel.proxmox.util import cluster_scoped_id
from cartography.intel.proxmox.util import proxmox_api_retry
from cartography.models.core.nodes import CartographyNodeSchema
from cartography.models.proxmox.access import ProxmoxACLSchema
from cartography.models.proxmox.access import ProxmoxAPITokenSchema
from cartography.models.proxmox.access import ProxmoxGroupSchema
from cartography.models.proxmox.access import ProxmoxRealmSchema
from cartography.models.proxmox.access import ProxmoxRealmSyncJobSchema
from cartography.models.proxmox.access import ProxmoxRoleSchema
from cartography.models.proxmox.access import ProxmoxTFAFactorSchema
from cartography.models.proxmox.access import ProxmoxUserSchema
from cartography.util import timeit

logger = logging.getLogger(__name__)

# Realm types whose configuration holds nothing beyond what /access/domains
# already returns, so their detail endpoint is not called.
_REALM_TYPES_WITHOUT_DETAILS = frozenset({"pam", "pve"})

# Non-secret realm configuration fields read from /access/domains/{realm},
# mapped to node property names. The endpoint returns the raw realm config,
# which for OpenID realms includes the client key: never copy other fields.
_REALM_DETAIL_FIELDS = {
    "server1": "server1",
    "server2": "server2",
    "port": "port",
    "mode": "mode",
    "verify": "verify",
    "base_dn": "base_dn",
    "bind_dn": "bind_dn",
    "domain": "domain",
    "issuer-url": "issuer_url",
    "client-id": "client_id",
    "autocreate": "autocreate",
}
_REALM_BOOLEAN_DETAIL_FIELDS = frozenset({"verify", "autocreate"})


# ============================================================================
# GET functions - retrieve data from Proxmox API
# ============================================================================


@timeit
@proxmox_api_retry
def get_users(proxmox_client: Any) -> list[dict[str, Any]]:
    """
    Get all users in the cluster, with their groups and API tokens.

    full=1 adds the groups and API tokens of every user in the same call, so
    the sync needs no per-user /access/users/{userid}/token request. That
    request also needs User.Modify for other users' tokens, which PVEAuditor
    lacks, while this list only needs Sys.Audit.

    :param proxmox_client: Proxmox API client
    :return: List of user dicts
    :raises: Exception if API call fails
    """
    return proxmox_client.access.users.get(full=1)


@timeit
@proxmox_api_retry
def get_realms(proxmox_client: Any) -> list[dict[str, Any]]:
    """
    Get all authentication realms (domains) of the cluster.

    :param proxmox_client: Proxmox API client
    :return: List of realm dicts
    :raises: Exception if API call fails
    """
    return proxmox_client.access.domains.get()


@timeit
@proxmox_api_retry
def get_realm_details(
    proxmox_client: Any,
    realms: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """
    Get the configuration of every realm that has more than the list shows.

    PAM and PVE realms are skipped: their configuration has no extra fields.
    The caller must keep only non-secret fields of the returned configuration.

    :param proxmox_client: Proxmox API client
    :param realms: Realm dicts from get_realms()
    :return: Dict mapping realm names to their raw configuration
    :raises: Exception if API call fails
    """
    details: dict[str, dict[str, Any]] = {}
    for realm in realms:
        name = realm.get("realm")
        if not name or realm.get("type") in _REALM_TYPES_WITHOUT_DETAILS:
            continue
        details[name] = proxmox_client.access.domains(name).get()
    return details


@timeit
@proxmox_api_retry
def get_realm_sync_jobs(proxmox_client: Any) -> list[dict[str, Any]]:
    """
    Get all scheduled realm sync jobs of the cluster.

    :param proxmox_client: Proxmox API client
    :return: List of realm sync job dicts
    :raises: Exception if API call fails
    """
    return proxmox_client.cluster.jobs("realm-sync").get()


@timeit
@proxmox_api_retry
def get_tfa(proxmox_client: Any) -> list[dict[str, Any]]:
    """
    Get the second factor entries of every user.

    The API returns only metadata (ID, type, description, state); it never
    returns TOTP secrets or recovery codes.

    :param proxmox_client: Proxmox API client
    :return: List of per-user dicts with userid, entries, and lock state
    :raises: Exception if API call fails
    """
    return proxmox_client.access.tfa.get()


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


def _realm_of(userid: str) -> str | None:
    """
    Return the realm of a Proxmox user ID, the part after the last @.

    :param userid: User ID in the form user@realm
    :return: Realm name, or None if the ID has no realm
    """
    if "@" not in userid:
        return None
    return userid.rsplit("@", 1)[1] or None


def _tfa_summary(tfa_entry: dict[str, Any] | None) -> dict[str, Any]:
    """
    Summarize the second factors of one user.

    :param tfa_entry: The user's item from get_tfa(), or None if absent
    :return: Dict with tfa_enabled, tfa_types, totp_locked, tfa_locked_until
    """
    entries = (tfa_entry or {}).get("entries") or []
    enabled_types = sorted(
        {
            entry["type"]
            for entry in entries
            if entry.get("type") and bool(entry.get("enable", True))
        },
    )
    return {
        "tfa_enabled": bool(enabled_types),
        "tfa_types": enabled_types,
        "totp_locked": (tfa_entry or {}).get("totp-locked"),
        "tfa_locked_until": (tfa_entry or {}).get("tfa-locked-until"),
    }


def transform_user_data(
    users: list[dict[str, Any]],
    cluster_id: str,
    group_members: dict[str, list[str]] | None = None,
    tfa: list[dict[str, Any]] | None = None,
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
    :param tfa: Optional per-user second factor data from get_tfa()
    :return: List of transformed user dicts
    """
    tfa_by_user = {
        entry["userid"]: entry for entry in (tfa or []) if entry.get("userid")
    }
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

        realm = _realm_of(userid)
        tfa_summary = _tfa_summary(tfa_by_user.get(userid))
        # The user list carries the lock state too; prefer it over /access/tfa.
        for field, api_field in (
            ("totp_locked", "totp-locked"),
            ("tfa_locked_until", "tfa-locked-until"),
        ):
            if user.get(api_field) is not None:
                tfa_summary[field] = user[api_field]
        if tfa_summary["totp_locked"] is not None:
            tfa_summary["totp_locked"] = bool(tfa_summary["totp_locked"])

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
                "realm": realm,
                "realm_type": user.get("realm-type"),
                "realm_id": cluster_scoped_id(cluster_id, realm) if realm else None,
                **tfa_summary,
            }
        )

    return transformed_users


def transform_token_data(
    users: list[dict[str, Any]],
    cluster_id: str,
) -> list[dict[str, Any]]:
    """
    Extract the API tokens listed under each user.

    The token secret is never returned by the API and is not stored.

    :param users: Raw user data from get_users() (full=1)
    :param cluster_id: Parent cluster ID
    :return: List of transformed token dicts
    """
    transformed_tokens = []
    for user in users:
        userid = user["userid"]
        for token in user.get("tokens") or []:
            tokenid = token["tokenid"]
            full_tokenid = f"{userid}!{tokenid}"
            transformed_tokens.append(
                {
                    "id": cluster_scoped_id(cluster_id, full_tokenid),
                    "full_tokenid": full_tokenid,
                    "tokenid": tokenid,
                    "userid": userid,
                    "user_id": cluster_scoped_id(cluster_id, userid),
                    "cluster_id": cluster_id,
                    "comment": token.get("comment"),
                    "expire": token.get("expire"),
                    # Proxmox defaults to privilege separation when unset.
                    "privsep": bool(token.get("privsep", True)),
                }
            )
    return transformed_tokens


def transform_tfa_factor_data(
    tfa: list[dict[str, Any]],
    cluster_id: str,
) -> list[dict[str, Any]]:
    """
    Transform per-user second factor entries into one dict per factor.

    Only the metadata the API returns is kept: no secret, key, or recovery
    code is ever part of the response.

    :param tfa: Raw data from get_tfa()
    :param cluster_id: Parent cluster ID
    :return: List of transformed factor dicts
    """
    transformed_factors = []
    for user_entry in tfa:
        userid = user_entry["userid"]
        for entry in user_entry.get("entries") or []:
            factor_id = entry["id"]
            transformed_factors.append(
                {
                    "id": cluster_scoped_id(cluster_id, f"{userid}/{factor_id}"),
                    "factor_id": factor_id,
                    "userid": userid,
                    "user_id": cluster_scoped_id(cluster_id, userid),
                    "cluster_id": cluster_id,
                    "type": entry.get("type"),
                    "description": entry.get("description"),
                    "enable": bool(entry.get("enable", True)),
                    "created": entry.get("created"),
                }
            )
    return transformed_factors


def transform_realm_data(
    realms: list[dict[str, Any]],
    realm_details: dict[str, dict[str, Any]],
    cluster_id: str,
) -> list[dict[str, Any]]:
    """
    Transform realms, adding the non-secret fields of their configuration.

    :param realms: Raw data from get_realms()
    :param realm_details: Raw configuration per realm from get_realm_details()
    :param cluster_id: Parent cluster ID
    :return: List of transformed realm dicts
    """
    transformed_realms = []
    for realm in realms:
        name = realm["realm"]
        config = realm_details.get(name) or {}
        transformed = {
            "id": cluster_scoped_id(cluster_id, name),
            "realm": name,
            "cluster_id": cluster_id,
            "type": realm.get("type"),
            "comment": realm.get("comment"),
            "tfa": realm.get("tfa"),
            "default": bool(realm.get("default", config.get("default", False))),
        }
        for api_field, prop in _REALM_DETAIL_FIELDS.items():
            value = config.get(api_field)
            if value is not None and api_field in _REALM_BOOLEAN_DETAIL_FIELDS:
                value = bool(value)
            transformed[prop] = value
        transformed_realms.append(transformed)
    return transformed_realms


def transform_realm_sync_job_data(
    jobs: list[dict[str, Any]],
    cluster_id: str,
) -> list[dict[str, Any]]:
    """
    Transform realm sync jobs into standard format.

    :param jobs: Raw data from get_realm_sync_jobs()
    :param cluster_id: Parent cluster ID
    :return: List of transformed job dicts
    """
    return [
        {
            "id": cluster_scoped_id(cluster_id, job["id"]),
            "job_id": job["id"],
            "cluster_id": cluster_id,
            "realm": job["realm"],
            "realm_id": cluster_scoped_id(cluster_id, job["realm"]),
            "enabled": bool(job.get("enabled", True)),
            "schedule": job.get("schedule"),
            "scope": job.get("scope"),
            "remove_vanished": job.get("remove-vanished"),
            "comment": job.get("comment"),
            "last_run": job.get("last-run"),
            "next_run": job.get("next-run"),
        }
        for job in jobs
    ]


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

        # The API types each entry as user, group, or token. Fall back to the
        # ID format (groups have no @, tokens are user@realm!tokenid).
        principal_type = acl.get("type")
        if principal_type not in ("user", "group", "token"):
            if "@" not in ugid:
                principal_type = "group"
            elif "!" in ugid:
                principal_type = "token"
            else:
                principal_type = "user"
        # The owning user of a token, kept as a property only: a token ACL
        # grants the token, not its user, so it links to the token alone.
        base_userid = ugid.split("!")[0] if principal_type == "token" else ugid

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
                    cluster_scoped_id(cluster_id, ugid)
                    if principal_type == "user"
                    else None
                ),
                "target_token_id": (
                    cluster_scoped_id(cluster_id, ugid)
                    if principal_type == "token"
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


def _load_cluster_scoped(
    neo4j_session: neo4j.Session,
    schema: CartographyNodeSchema,
    data: list[dict[str, Any]],
    cluster_id: str,
    update_tag: int,
) -> None:
    """
    Load cluster-scoped nodes of one schema, skipping empty lists.

    :param neo4j_session: Neo4j session
    :param schema: Node schema instance to load
    :param data: List of transformed dicts
    :param cluster_id: Parent cluster ID
    :param update_tag: Sync timestamp
    """
    if not data:
        return
    load(
        neo4j_session,
        schema,
        data,
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
    logger.info(
        "Syncing Proxmox access control (realms, users, tokens, second factors, "
        "groups, roles, ACLs)",
    )

    # GET - retrieve data from API
    realms = get_realms(proxmox_client)
    realm_details = _get_realm_details_if_allowed(proxmox_client, realms)
    realm_sync_jobs = get_realm_sync_jobs(proxmox_client)
    users = get_users(proxmox_client)
    tfa = get_tfa(proxmox_client)
    groups = get_groups(proxmox_client)
    roles = get_roles(proxmox_client)
    acls = get_acls(proxmox_client)

    # Get group membership information (important for SSO users)
    group_members = get_group_members(proxmox_client, groups)

    # TRANSFORM - manipulate data for ingestion
    transformed_realms = transform_realm_data(realms, realm_details, cluster_id)
    transformed_realm_sync_jobs = transform_realm_sync_job_data(
        realm_sync_jobs,
        cluster_id,
    )
    transformed_users = transform_user_data(users, cluster_id, group_members, tfa)
    transformed_tokens = transform_token_data(users, cluster_id)
    transformed_tfa_factors = transform_tfa_factor_data(tfa, cluster_id)
    transformed_groups = transform_group_data(groups, cluster_id)
    transformed_roles = transform_role_data(roles, cluster_id)
    transformed_acls = transform_acl_data(acls, cluster_id)

    # LOAD - ingest to Neo4j. Targets load before the nodes that link to them:
    # realms before users and sync jobs, users before tokens and factors,
    # tokens before ACLs.
    _load_cluster_scoped(
        neo4j_session, ProxmoxRealmSchema(), transformed_realms, cluster_id, update_tag
    )
    _load_cluster_scoped(
        neo4j_session,
        ProxmoxRealmSyncJobSchema(),
        transformed_realm_sync_jobs,
        cluster_id,
        update_tag,
    )

    if transformed_groups:
        load_groups(neo4j_session, transformed_groups, cluster_id, update_tag)

    if transformed_users:
        # User-to-Group relationships are now handled by the schema via one_to_many
        load_users(neo4j_session, transformed_users, cluster_id, update_tag)

    _load_cluster_scoped(
        neo4j_session,
        ProxmoxAPITokenSchema(),
        transformed_tokens,
        cluster_id,
        update_tag,
    )
    _load_cluster_scoped(
        neo4j_session,
        ProxmoxTFAFactorSchema(),
        transformed_tfa_factors,
        cluster_id,
        update_tag,
    )

    if transformed_roles:
        load_roles(neo4j_session, transformed_roles, cluster_id, update_tag)

    if transformed_acls:
        load_acls(neo4j_session, transformed_acls, cluster_id, update_tag)

    logger.info(
        "Synced %d realms, %d realm sync jobs, %d users, %d API tokens, "
        "%d second factors, %d groups, %d roles, and %d ACLs",
        len(transformed_realms),
        len(transformed_realm_sync_jobs),
        len(transformed_users),
        len(transformed_tokens),
        len(transformed_tfa_factors),
        len(transformed_groups),
        len(transformed_roles),
        len(transformed_acls),
    )


def _get_realm_details_if_allowed(
    proxmox_client: Any,
    realms: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """
    Read realm configurations, or skip them when the API user may not.

    The detail endpoint needs Sys.Audit or Realm.Allocate on /access/realm,
    while the realm list is public. Without that privilege Cartography still
    loads every realm, only without its server and client settings.

    :param proxmox_client: Proxmox API client
    :param realms: Realm dicts from get_realms()
    :return: Raw configuration per realm, empty when access is denied
    """
    try:
        return get_realm_details(proxmox_client, realms)
    except ResourceException as e:
        if e.status_code != 403:
            raise
        logger.info(
            "Proxmox API user may not read realm configurations "
            "(needs Sys.Audit on /access/realm), syncing realms without them: %s",
            e,
        )
        return {}
