"""
Sync Proxmox resource pools.

Follows Cartography's Get → Transform → Load pattern.
"""

import logging
from typing import Any

import neo4j

from cartography.client.core.tx import load
from cartography.intel.proxmox.util import cluster_scoped_id
from cartography.intel.proxmox.util import proxmox_api_retry
from cartography.models.proxmox.pool import ProxmoxPoolSchema
from cartography.util import timeit

logger = logging.getLogger(__name__)


# ============================================================================
# GET functions - retrieve data from Proxmox API
# ============================================================================


@timeit
@proxmox_api_retry
def get_pools(proxmox_client: Any) -> list[dict[str, Any]]:
    """
    Get all resource pools in the cluster.

    :param proxmox_client: Proxmox API client
    :return: List of pool dicts
    :raises: Exception if API call fails
    """
    return proxmox_client.pools.get()


@timeit
@proxmox_api_retry
def get_pool_details(proxmox_client: Any, poolid: str) -> dict[str, Any]:
    """
    Get detailed information about a specific pool.

    :param proxmox_client: Proxmox API client
    :param poolid: Pool ID
    :return: Pool details dict
    :raises: Exception if API call fails
    """
    return proxmox_client.pools(poolid).get()


# ============================================================================
# TRANSFORM functions - manipulate data for graph ingestion
# ============================================================================


def _pool_member_ids(
    members: list[dict[str, Any]],
    cluster_id: str,
) -> tuple[list[str], list[str]]:
    """
    Split pool members into guest IDs and storage IDs.

    Guest IDs use the cluster_id/node/type/vmid form of ProxmoxVM IDs, so a
    member only matches the guest on its own node and cluster.

    :param members: Members of one pool, as returned by the pool details API
    :param cluster_id: Parent cluster ID, used to prefix graph IDs
    :return: Tuple of (guest IDs, storage IDs)
    """
    vm_ids = []
    storage_ids = []
    for member in members:
        member_type = member.get("type")
        if member_type in ("qemu", "lxc"):
            node = member.get("node")
            vmid = member.get("vmid")
            if node and vmid is not None:
                vm_ids.append(
                    cluster_scoped_id(cluster_id, f"{node}/{member_type}/{vmid}"),
                )
        elif member_type == "storage" and member.get("storage"):
            storage_ids.append(cluster_scoped_id(cluster_id, member["storage"]))
    return vm_ids, storage_ids


def transform_pool_data(
    pools: list[dict[str, Any]],
    cluster_id: str,
    pool_details: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """
    Transform pool data into standard format.

    Per Cartography guidelines:
    - Use data['field'] for required fields (will raise KeyError if missing)
    - Use data.get('field') for optional fields

    :param pools: Raw pool data from API
    :param cluster_id: Parent cluster ID
    :param pool_details: Map of pool ID -> pool details, which list the members
    :return: List of transformed pool dicts
    """
    transformed_pools = []
    pool_details = pool_details or {}

    for pool in pools:
        # Required field - use direct access
        poolid = pool["poolid"]
        members = pool_details.get(poolid, {}).get("members", [])
        vm_ids, storage_ids = _pool_member_ids(members, cluster_id)

        transformed_pools.append(
            {
                "id": cluster_scoped_id(cluster_id, poolid),
                "poolid": poolid,
                "comment": pool.get("comment"),
                "cluster_id": cluster_id,
                "vm_ids": vm_ids,
                "storage_ids": storage_ids,
            }
        )

    return transformed_pools


# ============================================================================
# LOAD functions - ingest data to Neo4j using modern data model
# ============================================================================


def load_pools(
    neo4j_session: neo4j.Session,
    pools: list[dict[str, Any]],
    cluster_id: str,
    update_tag: int,
) -> None:
    """
    Load pool data into Neo4j using modern data model.

    :param neo4j_session: Neo4j session
    :param pools: List of transformed pool dicts
    :param cluster_id: Parent cluster ID
    :param update_tag: Sync timestamp
    """
    load(
        neo4j_session,
        ProxmoxPoolSchema(),
        pools,
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
    Sync pool data.

    Follows Cartography's Get → Transform → Load pattern.

    :param neo4j_session: Neo4j session
    :param proxmox_client: Proxmox API client
    :param cluster_id: Parent cluster ID
    :param update_tag: Sync timestamp
    :param common_job_parameters: Common parameters
    """
    logger.info("Syncing Proxmox resource pools")

    # GET - retrieve data from API
    pools = get_pools(proxmox_client)

    pool_details = {
        pool["poolid"]: get_pool_details(proxmox_client, pool["poolid"])
        for pool in pools
    }

    # TRANSFORM - manipulate data for ingestion
    transformed_pools = transform_pool_data(pools, cluster_id, pool_details)

    # LOAD - ingest to Neo4j
    load_pools(neo4j_session, transformed_pools, cluster_id, update_tag)

    logger.info(
        "Synced %d resource pools with %d members",
        len(transformed_pools),
        sum(
            len(pool["vm_ids"]) + len(pool["storage_ids"]) for pool in transformed_pools
        ),
    )
