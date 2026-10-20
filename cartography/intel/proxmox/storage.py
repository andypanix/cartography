"""
Sync Proxmox storage resources.

Follows Cartography's Get → Transform → Load pattern.
"""

import logging
from typing import Any
from typing import Dict
from typing import List

import neo4j
import requests
from proxmoxer.core import ResourceException

from cartography.client.core.tx import load
from cartography.intel.proxmox.util import cluster_scoped_id
from cartography.intel.proxmox.util import proxmox_api_retry
from cartography.models.proxmox.storage import ProxmoxStorageSchema
from cartography.util import timeit

logger = logging.getLogger(__name__)

# Proxmox VE 9 answers HTTP 500 with this message for storage types whose
# plugin has no identity, such as NFS, CIFS or directory storage.
STORAGE_IDENTITY_NOT_IMPLEMENTED_MESSAGE = "get_identity not implemented"


def is_storage_identity_not_implemented_error(exc: Exception) -> bool:
    """
    Check if a storage identity error means the storage plugin has no identity.

    :param exc: The exception raised by the Proxmox API client
    :return: True for the HTTP 500 that storage plugins without identity return
    """
    return (
        isinstance(exc, ResourceException)
        and exc.status_code == 500
        and STORAGE_IDENTITY_NOT_IMPLEMENTED_MESSAGE in str(exc)
    )


# ============================================================================
# GET functions
# ============================================================================


@timeit
@proxmox_api_retry
def get_storage(proxmox_client: Any) -> List[Dict[str, Any]]:
    """
    Get all storage definitions from Proxmox.

    :param proxmox_client: Proxmox API client
    :return: List of storage dicts
    :raises: Exception if API call fails
    """
    return proxmox_client.storage.get()


@timeit
@proxmox_api_retry
def get_storage_status(proxmox_client: Any, node_name: str) -> List[Dict[str, Any]]:
    """
    Get storage status for a specific node.

    :param proxmox_client: Proxmox API client
    :param node_name: Node name
    :return: List of storage status dicts
    :raises: Exception if API call fails
    """
    return proxmox_client.nodes(node_name).storage.get()


@timeit
@proxmox_api_retry
def get_storage_status_detail(
    proxmox_client: Any,
    node_name: str,
    storage_name: str,
) -> Dict[str, Any]:
    """
    Read the status of one storage on one node.

    :param proxmox_client: Proxmox API client
    :param node_name: Node name
    :param storage_name: Storage name
    :return: Status dict with type, content, enabled, active, shared, and sizes
    """
    return proxmox_client.nodes(node_name).storage(storage_name).status.get()


def merge_storage_status_details(
    proxmox_client: Any,
    node_name: str,
    status_list: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Read the status endpoint of each active storage of a node and merge it in.

    pve-storage builds both responses from the same storage_info call, so the
    per-storage status returns no field the per-node list lacks. The list
    values are kept; the per-storage status only fills fields the list leaves
    unset. A storage whose status cannot be read keeps its list entry.

    :param proxmox_client: Proxmox API client
    :param node_name: Node name
    :param status_list: Response of /nodes/{node}/storage
    :return: Storage status dicts
    """
    merged = []
    for status in status_list:
        storage_name = status.get("storage")
        if not storage_name or not status.get("active"):
            merged.append(status)
            continue
        try:
            detail = get_storage_status_detail(proxmox_client, node_name, storage_name)
        except (ResourceException, requests.exceptions.RequestException) as e:
            logger.warning(
                "Could not read the status of storage %s on node %s, keeping "
                "the storage list values: %s",
                storage_name,
                node_name,
                e,
            )
            merged.append(status)
            continue
        merged.append(
            {
                **{k: v for k, v in (detail or {}).items() if v is not None},
                **{k: v for k, v in status.items() if v is not None},
            },
        )
    return merged


@timeit
@proxmox_api_retry
def get_storage_identity(
    proxmox_client: Any,
    node_name: str,
    storage_name: str,
) -> Dict[str, Any]:
    """
    Get the identity of a storage instance (Proxmox VE 9 only).

    :param proxmox_client: Proxmox API client
    :param node_name: Node to ask
    :param storage_name: Storage name
    :return: Identity dict with id and type
    """
    return proxmox_client.nodes(node_name).storage(storage_name).identity.get()


def get_shared_storage_identities(
    proxmox_client: Any,
    storage_list: List[Dict[str, Any]],
    storage_status_map: Dict[str, List[Dict[str, Any]]],
) -> Dict[str, str]:
    """
    Read the identity of each active shared storage from one node.

    Storage local to a node has one identity per node and is skipped, and so
    is storage whose plugin does not implement an identity or whose read
    fails. The reads stop at the first HTTP 501, which means the host does not
    have the endpoint, such as Proxmox VE 8.

    :param proxmox_client: Proxmox API client
    :param storage_list: Raw storage definitions from API
    :param storage_status_map: Map of node_name -> storage status list
    :return: Map of storage name -> identity
    """
    identities: Dict[str, str] = {}
    for storage in storage_list:
        if storage.get("shared", 0) != 1:
            continue
        storage_name = storage["storage"]
        node_name = next(
            (
                node
                for node, status_list in storage_status_map.items()
                if any(
                    status.get("storage") == storage_name and status.get("active")
                    for status in status_list
                )
            ),
            None,
        )
        if node_name is None:
            continue
        try:
            identity = get_storage_identity(proxmox_client, node_name, storage_name)
        except ResourceException as e:
            if e.status_code == 501:
                logger.info(
                    "Storage identity endpoint is not available on this host, "
                    "skipping: %s",
                    e,
                )
                break
            if is_storage_identity_not_implemented_error(e) or e.status_code == 404:
                logger.info(
                    "Storage %s has no identity on node %s, skipping: %s",
                    storage_name,
                    node_name,
                    e,
                )
            else:
                logger.warning(
                    "Could not read identity of storage %s on node %s, skipping: %s",
                    storage_name,
                    node_name,
                    e,
                )
            continue
        except requests.exceptions.RequestException as e:
            logger.warning(
                "Could not read identity of storage %s on node %s, skipping: %s",
                storage_name,
                node_name,
                e,
            )
            continue
        if identity.get("id"):
            identities[storage_name] = identity["id"]
    return identities


# ============================================================================
# TRANSFORM functions
# ============================================================================


def transform_storage_data(
    storage_list: List[Dict[str, Any]],
    storage_status_map: Dict[str, List[Dict[str, Any]]],
    cluster_id: str,
    identities: Dict[str, str] | None = None,
) -> List[Dict[str, Any]]:
    """
    Transform storage data into standard format.

    :param storage_list: Raw storage definitions from API
    :param storage_status_map: Map of node_name -> storage status list
    :param cluster_id: Parent cluster ID
    :param identities: Map of storage name -> storage instance identity
    :return: List of transformed storage dicts
    """
    transformed_storage = []

    for storage in storage_list:
        # Required fields
        storage_id = storage["storage"]

        # Parse content types
        content_types = []
        if storage.get("content"):
            content_types = [c.strip() for c in storage["content"].split(",")]

        # Determine which nodes have access to this storage
        nodes = []
        if storage.get("nodes"):
            # Specific nodes listed
            nodes = [n.strip() for n in storage["nodes"].split(",")]
        else:
            # All nodes have access
            nodes = list(storage_status_map.keys())

        # Try to get size information from status
        total = 0
        used = 0
        available = 0

        for node_name, status_list in storage_status_map.items():
            for status in status_list:
                if status.get("storage") == storage_id:
                    total = max(total, status.get("total", 0))
                    used = max(used, status.get("used", 0))
                    available = max(available, status.get("avail", 0))
                    break

        transformed_storage.append(
            {
                "id": cluster_scoped_id(cluster_id, storage_id),
                "name": storage_id,
                "cluster_id": cluster_id,
                "type": storage.get("type"),
                "content_types": content_types,
                "shared": storage.get("shared", 0) == 1,
                "enabled": storage.get("disable", 0) == 0,
                "total": total,
                "used": used,
                "available": available,
                "node_ids": [cluster_scoped_id(cluster_id, n) for n in nodes],
                "identity": (identities or {}).get(storage_id),
            }
        )

    return transformed_storage


# ============================================================================
# LOAD functions - using modern data model
# ============================================================================


def load_storage(
    neo4j_session: neo4j.Session,
    storage_list: List[Dict[str, Any]],
    cluster_id: str,
    update_tag: int,
) -> None:
    """
    Load storage data into Neo4j using modern data model.

    :param neo4j_session: Neo4j session
    :param storage_list: List of transformed storage dicts
    :param cluster_id: Parent cluster ID
    :param update_tag: Sync timestamp
    """
    load(
        neo4j_session,
        ProxmoxStorageSchema(),
        storage_list,
        lastupdated=update_tag,
        CLUSTER_ID=cluster_id,
    )


# ============================================================================
# SYNC function
# ============================================================================


@timeit
def sync(
    neo4j_session: neo4j.Session,
    proxmox_client: Any,
    cluster_id: str,
    update_tag: int,
    common_job_parameters: Dict[str, Any],
    detailed_reads: bool = False,
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Sync storage resources.

    :param neo4j_session: Neo4j session
    :param proxmox_client: Proxmox API client
    :param cluster_id: Parent cluster ID
    :param update_tag: Sync timestamp
    :param common_job_parameters: Common parameters
    :param detailed_reads: Also read the status endpoint of each active storage
        on each node (--proxmox-detailed-reads), which returns no field the
        per-node list lacks
    :return: Map of node_name -> storage status list, reused by the content sync
    """
    logger.info("Syncing Proxmox storage")

    # GET - retrieve data from API
    storage_list = get_storage(proxmox_client)

    # Get storage status from each node for size information
    nodes = proxmox_client.nodes.get()
    storage_status_map = {}

    for node in nodes:
        node_name = node["node"]
        storage_status = get_storage_status(proxmox_client, node_name)
        if detailed_reads:
            storage_status = merge_storage_status_details(
                proxmox_client, node_name, storage_status
            )
        storage_status_map[node_name] = storage_status

    # TRANSFORM - manipulate data for ingestion
    identities = get_shared_storage_identities(
        proxmox_client,
        storage_list,
        storage_status_map,
    )
    transformed_storage = transform_storage_data(
        storage_list, storage_status_map, cluster_id, identities
    )

    # LOAD - ingest to Neo4j
    load_storage(neo4j_session, transformed_storage, cluster_id, update_tag)

    logger.info(f"Synced {len(transformed_storage)} storage resources")
    return storage_status_map
