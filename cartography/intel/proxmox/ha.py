"""
Sync Proxmox High Availability (HA) groups, resources, rules, and status.

Follows Cartography's Get → Transform → Load pattern.
"""

import logging
from typing import Any

import neo4j
from proxmoxer.core import ResourceException

from cartography.client.core.tx import load
from cartography.intel.proxmox.util import cluster_scoped_id
from cartography.intel.proxmox.util import proxmox_api_retry
from cartography.intel.proxmox.util import proxmox_optional_endpoint
from cartography.models.proxmox.ha import ProxmoxHAGroupSchema
from cartography.models.proxmox.ha import ProxmoxHALRMSchema
from cartography.models.proxmox.ha import ProxmoxHAManagerSchema
from cartography.models.proxmox.ha import ProxmoxHAResourceSchema
from cartography.models.proxmox.ha import ProxmoxHARuleSchema
from cartography.util import timeit

logger = logging.getLogger(__name__)

# Proxmox VE 9 migrates HA groups to HA rules once every node is upgraded.
# From then on GET /cluster/ha/groups answers HTTP 500 with this message
# (pve-ha-manager src/PVE/API2/HA/Groups.pm).
HA_GROUPS_MIGRATED_MESSAGE = "ha groups have been migrated to rules"


# ============================================================================
# GET functions - retrieve data from Proxmox API
# ============================================================================


@timeit
@proxmox_api_retry
def get_ha_groups(proxmox_client: Any) -> list[dict[str, Any]]:
    """
    Get all HA groups in the cluster.

    :param proxmox_client: Proxmox API client
    :return: List of HA group dicts
    :raises: Exception if API call fails
    """
    return proxmox_client.cluster.ha.groups.get()


@timeit
@proxmox_api_retry
def get_ha_resources(proxmox_client: Any) -> list[dict[str, Any]]:
    """
    Get all HA resources in the cluster.

    :param proxmox_client: Proxmox API client
    :return: List of HA resource dicts
    :raises: Exception if API call fails
    """
    return proxmox_client.cluster.ha.resources.get()


@timeit
@proxmox_optional_endpoint(list)
@proxmox_api_retry
def get_ha_rules(proxmox_client: Any) -> list[dict[str, Any]]:
    """
    Get all HA rules in the cluster. The endpoint exists on Proxmox VE 9 only.

    :param proxmox_client: Proxmox API client
    :return: List of HA rule dicts, empty when the endpoint does not exist
    :raises: Exception if API call fails
    """
    return proxmox_client.cluster.ha.rules.get()


@timeit
@proxmox_api_retry
def get_ha_status(proxmox_client: Any) -> list[dict[str, Any]]:
    """
    Get the HA status entries: quorum, master, fencing, lrm, and service.

    :param proxmox_client: Proxmox API client
    :return: List of HA status entry dicts
    :raises: Exception if API call fails
    """
    return proxmox_client.cluster.ha.status.current.get()


@timeit
@proxmox_api_retry
def get_ha_manager_status(proxmox_client: Any) -> dict[str, Any]:
    """
    Get the full HA manager status, including the LRM status of each node.

    :param proxmox_client: Proxmox API client
    :return: Dict with manager_status, lrm_status, and quorum keys
    :raises: Exception if API call fails
    """
    return proxmox_client.cluster.ha.status.manager_status.get()


def is_ha_groups_migrated_error(exc: Exception) -> bool:
    """
    Check if an HA groups API error means the groups were migrated to HA rules.

    :param exc: The exception raised by the Proxmox API client
    :return: True for the HTTP 500 that Proxmox VE 9 returns after the migration
    """
    return (
        isinstance(exc, ResourceException)
        and exc.status_code == 500
        and HA_GROUPS_MIGRATED_MESSAGE in str(exc)
    )


# ============================================================================
# TRANSFORM functions - manipulate data for graph ingestion
# ============================================================================


def _optional_bool(value: Any) -> bool | None:
    """
    Convert a Proxmox 0/1 flag to a boolean, keeping None when it is unset.

    :param value: Flag as returned by the API
    :return: The flag as a boolean, or None
    """
    if value is None:
        return None
    try:
        return bool(int(value))
    except (TypeError, ValueError):
        return None


def _as_dict(value: Any) -> dict[str, Any]:
    """
    Return the value when it is a dict, otherwise an empty dict.

    The HA manager status is not typed in the API schema, so a field of an
    unexpected type is ignored instead of stopping the HA sync.

    :param value: Value from the API
    :return: The value, or an empty dict
    """
    return value if isinstance(value, dict) else {}


def transform_ha_group_data(
    groups: list[dict[str, Any]],
    cluster_id: str,
) -> list[dict[str, Any]]:
    """
    Transform HA group data into standard format.

    Per Cartography guidelines:
    - Use data['field'] for required fields (will raise KeyError if missing)
    - Use data.get('field') for optional fields

    :param groups: Raw HA group data from API
    :param cluster_id: Parent cluster ID
    :return: List of transformed HA group dicts
    """
    transformed_groups = []

    for group in groups:
        # Required field - use direct access
        group_name = group["group"]

        transformed_groups.append(
            {
                "id": cluster_scoped_id(cluster_id, group_name),
                "group": group_name,
                "cluster_id": cluster_id,
                "nodes": group.get("nodes"),
                "restricted": group.get("restricted", False),
                "nofailback": group.get("nofailback", False),
                "comment": group.get("comment"),
            }
        )

    return transformed_groups


def _parse_guest_vmid(sid: str) -> int | None:
    """
    Return the numeric VM ID of an HA service ID that names a guest.

    :param sid: HA service ID, such as vm:100 or ct:200
    :return: The VM ID, or None when the service is not a VM or container
    """
    kind, _, vmid = sid.partition(":")
    if kind in ("vm", "ct") and vmid.isdigit():
        return int(vmid)
    return None


def transform_ha_resource_data(
    resources: list[dict[str, Any]],
    cluster_id: str,
) -> list[dict[str, Any]]:
    """
    Transform HA resource data into standard format.

    :param resources: Raw HA resource data from API
    :param cluster_id: Parent cluster ID
    :return: List of transformed HA resource dicts
    """
    transformed_resources = []

    for resource in resources:
        # Required field - service ID (format: vm:100, ct:200)
        sid = resource["sid"]

        transformed_resources.append(
            {
                "id": cluster_scoped_id(cluster_id, sid),
                "sid": sid,
                "cluster_id": cluster_id,
                "state": resource.get("state"),
                "group": resource.get("group"),
                "group_id": (
                    cluster_scoped_id(cluster_id, resource["group"])
                    if resource.get("group")
                    else None
                ),
                "max_restart": resource.get("max_restart"),
                "max_relocate": resource.get("max_relocate"),
                "comment": resource.get("comment"),
                "type": resource.get("type"),
                "failback": _optional_bool(resource.get("failback")),
                "auto_rebalance": _optional_bool(resource.get("auto-rebalance")),
                "vmid": _parse_guest_vmid(sid),
            }
        )

    return transformed_resources


def _split_list(value: Any) -> list[str]:
    """
    Split an HA rule list property into its items.

    The API returns lists such as resources and nodes as comma-separated
    strings; a dict or list keyed by item is accepted too.

    :param value: Raw property value
    :return: List of non-empty items
    """
    if not value:
        return []
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return [str(item) for item in value]


def _format_node_list(value: Any) -> str | None:
    """
    Return the node list of an HA rule in the node[:priority],... form.

    :param value: Raw nodes property, a string or a dict of node -> priority
    :return: The node list string, or None when the rule has no nodes
    """
    if not value:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        entries = []
        for node, settings in value.items():
            priority = (
                settings.get("priority") if isinstance(settings, dict) else settings
            )
            entries.append(node if priority is None else f"{node}:{priority}")
        return ",".join(entries)
    return ",".join(str(node) for node in value)


def transform_ha_rule_data(
    rules: list[dict[str, Any]],
    cluster_id: str,
) -> list[dict[str, Any]]:
    """
    Transform HA rule data into standard format.

    :param rules: Raw HA rule data from API
    :param cluster_id: Parent cluster ID
    :return: List of transformed HA rule dicts
    """
    transformed_rules = []

    for rule in rules:
        # Required fields - use direct access
        rule_id = rule["rule"]
        rule_type = rule["type"]
        is_node_affinity = rule_type == "node-affinity"
        resources = _split_list(rule.get("resources"))
        nodes = _format_node_list(rule.get("nodes"))
        node_names = [entry.partition(":")[0] for entry in _split_list(nodes)]

        transformed_rules.append(
            {
                "id": cluster_scoped_id(cluster_id, rule_id),
                "rule": rule_id,
                "cluster_id": cluster_id,
                "type": rule_type,
                "resources": resources,
                "nodes": nodes,
                # Node affinity rules default to positive affinity and are
                # non-strict unless set. Resource affinity rules always set
                # affinity and have no strict option.
                "affinity": rule.get(
                    "affinity",
                    "positive" if is_node_affinity else None,
                ),
                "strict": (
                    bool(int(rule.get("strict", 0))) if is_node_affinity else None
                ),
                "disable": bool(int(rule.get("disable", 0))),
                "comment": rule.get("comment"),
                "resource_ids": [
                    cluster_scoped_id(cluster_id, sid) for sid in resources
                ],
                "node_ids": [cluster_scoped_id(cluster_id, n) for n in node_names],
            }
        )

    return transformed_rules


def transform_ha_status_data(
    status: list[dict[str, Any]],
    manager_status: dict[str, Any],
    cluster_id: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """
    Transform the HA status into the HA manager and one LRM per node.

    :param status: Entries of GET /cluster/ha/status/current
    :param manager_status: Response of GET /cluster/ha/status/manager_status
    :param cluster_id: Parent cluster ID
    :return: Tuple of (HA manager dicts, LRM dicts). There is no HA manager
        when the status is empty.
    """
    crm_status = _as_dict(manager_status.get("manager_status"))
    lrm_status = _as_dict(manager_status.get("lrm_status"))
    node_status = _as_dict(crm_status.get("node_status"))

    manager: dict[str, Any] = {
        "id": cluster_scoped_id(cluster_id, "ha-manager"),
        "cluster_id": cluster_id,
        "quorate": None,
        "master_node": crm_status.get("master_node"),
        "master_status": None,
        "armed_state": None,
        "resource_mode": None,
    }
    lrms = []

    for entry in status:
        entry_type = entry.get("type")
        if entry_type == "quorum":
            manager["quorate"] = _optional_bool(entry.get("quorate"))
        elif entry_type == "master":
            manager["master_node"] = entry.get("node") or manager["master_node"]
            manager["master_status"] = entry.get("status")
        elif entry_type == "fencing":
            manager["armed_state"] = entry.get("armed-state")
            manager["resource_mode"] = entry.get("resource_mode")
        elif entry_type == "lrm" and entry.get("node"):
            node = entry["node"]
            node_lrm = _as_dict(lrm_status.get(node))
            lrms.append(
                {
                    "id": cluster_scoped_id(cluster_id, f"lrm:{node}"),
                    "cluster_id": cluster_id,
                    "node": node,
                    "node_id": cluster_scoped_id(cluster_id, node),
                    "status": entry.get("status"),
                    "state": node_lrm.get("state"),
                    "mode": node_lrm.get("mode"),
                    "crm_node_state": node_status.get(node),
                }
            )

    manager["master_node_id"] = (
        cluster_scoped_id(cluster_id, manager["master_node"])
        if manager["master_node"]
        else None
    )
    managers = [manager] if status else []
    return managers, lrms


# ============================================================================
# LOAD functions - ingest data to Neo4j using modern data model
# ============================================================================


def load_ha_groups(
    neo4j_session: neo4j.Session,
    groups: list[dict[str, Any]],
    cluster_id: str,
    update_tag: int,
) -> None:
    """
    Load HA group data into Neo4j using modern data model.

    :param neo4j_session: Neo4j session
    :param groups: List of transformed HA group dicts
    :param cluster_id: Parent cluster ID
    :param update_tag: Sync timestamp
    """
    load(
        neo4j_session,
        ProxmoxHAGroupSchema(),
        groups,
        lastupdated=update_tag,
        CLUSTER_ID=cluster_id,
    )


def load_ha_resources(
    neo4j_session: neo4j.Session,
    resources: list[dict[str, Any]],
    cluster_id: str,
    update_tag: int,
) -> None:
    """
    Load HA resource data into Neo4j using modern data model.

    :param neo4j_session: Neo4j session
    :param resources: List of transformed HA resource dicts
    :param cluster_id: Parent cluster ID
    :param update_tag: Sync timestamp
    """
    load(
        neo4j_session,
        ProxmoxHAResourceSchema(),
        resources,
        lastupdated=update_tag,
        CLUSTER_ID=cluster_id,
    )


def load_ha_rules(
    neo4j_session: neo4j.Session,
    rules: list[dict[str, Any]],
    cluster_id: str,
    update_tag: int,
) -> None:
    """
    Load HA rule data into Neo4j using modern data model.

    :param neo4j_session: Neo4j session
    :param rules: List of transformed HA rule dicts
    :param cluster_id: Parent cluster ID
    :param update_tag: Sync timestamp
    """
    load(
        neo4j_session,
        ProxmoxHARuleSchema(),
        rules,
        lastupdated=update_tag,
        CLUSTER_ID=cluster_id,
    )


def load_ha_status(
    neo4j_session: neo4j.Session,
    managers: list[dict[str, Any]],
    lrms: list[dict[str, Any]],
    cluster_id: str,
    update_tag: int,
) -> None:
    """
    Load the HA manager and LRM data into Neo4j using modern data model.

    :param neo4j_session: Neo4j session
    :param managers: List of transformed HA manager dicts
    :param lrms: List of transformed LRM dicts
    :param cluster_id: Parent cluster ID
    :param update_tag: Sync timestamp
    """
    load(
        neo4j_session,
        ProxmoxHAManagerSchema(),
        managers,
        lastupdated=update_tag,
        CLUSTER_ID=cluster_id,
    )
    load(
        neo4j_session,
        ProxmoxHALRMSchema(),
        lrms,
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
    Sync HA groups, resources, rules, and the HA manager status.

    HA groups exist until a Proxmox VE 9 cluster migrates them to HA rules.
    HA rules exist on Proxmox VE 9 only.

    Follows Cartography's Get → Transform → Load pattern.

    :param neo4j_session: Neo4j session
    :param proxmox_client: Proxmox API client
    :param cluster_id: Parent cluster ID
    :param update_tag: Sync timestamp
    :param common_job_parameters: Common parameters
    """
    logger.info("Syncing Proxmox HA groups, resources, rules, and status")

    # GET - retrieve data from API
    try:
        groups = get_ha_groups(proxmox_client)
    except ResourceException as e:
        if not is_ha_groups_migrated_error(e):
            raise
        logger.info(
            "Proxmox HA groups have been migrated to HA rules, skipping HA groups",
        )
        groups = []
    resources = get_ha_resources(proxmox_client)
    rules = get_ha_rules(proxmox_client)
    status = get_ha_status(proxmox_client)
    manager_status = get_ha_manager_status(proxmox_client)

    # TRANSFORM - manipulate data for ingestion
    transformed_groups = transform_ha_group_data(groups, cluster_id)
    transformed_resources = transform_ha_resource_data(resources, cluster_id)
    transformed_rules = transform_ha_rule_data(rules, cluster_id)
    managers, lrms = transform_ha_status_data(status, manager_status, cluster_id)

    # LOAD - ingest to Neo4j
    if transformed_groups:
        load_ha_groups(neo4j_session, transformed_groups, cluster_id, update_tag)

    if transformed_resources:
        load_ha_resources(neo4j_session, transformed_resources, cluster_id, update_tag)

    load_ha_rules(neo4j_session, transformed_rules, cluster_id, update_tag)
    load_ha_status(neo4j_session, managers, lrms, cluster_id, update_tag)

    logger.info(
        "Synced %d HA groups, %d HA resources, %d HA rules, and %d HA LRMs",
        len(transformed_groups),
        len(transformed_resources),
        len(transformed_rules),
        len(lrms),
    )
