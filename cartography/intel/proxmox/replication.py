"""
Sync Proxmox storage replication jobs and their last run state.

Follows Cartography's Get → Transform → Load pattern.
"""

import logging
from typing import Any

import neo4j

from cartography.client.core.tx import load
from cartography.graph.job import GraphJob
from cartography.intel.proxmox import cluster
from cartography.intel.proxmox.util import cluster_scoped_id
from cartography.intel.proxmox.util import proxmox_api_retry
from cartography.models.proxmox.replication import ProxmoxReplicationJobSchema
from cartography.util import timeit

logger = logging.getLogger(__name__)

# Run state fields the node replication endpoints add to the job configuration.
REPLICATION_STATE_FIELDS = (
    "last_sync",
    "last_try",
    "next_sync",
    "duration",
    "fail_count",
    "error",
)

# ============================================================================
# GET functions
# ============================================================================


@timeit
@proxmox_api_retry
def get_cluster_replication_jobs(proxmox_client: Any) -> list[dict[str, Any]]:
    """
    Get the replication job configuration of the cluster.

    :param proxmox_client: Proxmox API client
    :return: List of replication job dicts
    """
    return proxmox_client.cluster.replication.get()


@timeit
@proxmox_api_retry
def get_node_replication_status(
    proxmox_client: Any,
    node_name: str,
) -> list[dict[str, Any]]:
    """
    Get the state of the replication jobs whose guests run on a node.

    :param proxmox_client: Proxmox API client
    :param node_name: Node name
    :return: List of job state dicts
    """
    return proxmox_client.nodes(node_name).replication.get()


@timeit
@proxmox_api_retry
def get_replication_job_status(
    proxmox_client: Any,
    node_name: str,
    job_id: str,
) -> dict[str, Any]:
    """
    Get the state of one replication job.

    :param proxmox_client: Proxmox API client
    :param node_name: Node name
    :param job_id: Replication job ID, in the form guest-jobnum
    :return: Job state dict
    """
    return proxmox_client.nodes(node_name).replication(job_id).status.get()


# ============================================================================
# TRANSFORM functions
# ============================================================================


def transform_replication_jobs(
    jobs: list[dict[str, Any]],
    states: dict[str, dict[str, Any]],
    cluster_id: str,
) -> list[dict[str, Any]]:
    """
    Transform replication jobs and merge in their run state.

    :param jobs: Raw /cluster/replication response
    :param states: Map of job ID -> state read from the node running the guest
    :param cluster_id: Parent cluster ID
    :return: List of transformed replication job dicts
    """
    transformed = []
    for job in jobs:
        job_id = job["id"]
        state = states.get(job_id, {})
        target = job.get("target")
        record = {
            "id": cluster_scoped_id(cluster_id, job_id),
            "job_id": job_id,
            "cluster_id": cluster_id,
            "guest": int(job["guest"]) if job.get("guest") is not None else None,
            "jobnum": job.get("jobnum"),
            "target": target,
            "target_node_id": cluster_scoped_id(cluster_id, target) if target else None,
            "type": job.get("type"),
            "schedule": job.get("schedule", "*/15"),
            "rate": job.get("rate"),
            "enabled": not bool(job.get("disable")),
            "comment": job.get("comment"),
            "remove_job": job.get("remove_job"),
            "source": job.get("source"),
        }
        for field in REPLICATION_STATE_FIELDS:
            record[field] = state.get(field)
        transformed.append(record)
    return transformed


# ============================================================================
# LOAD functions
# ============================================================================


def load_replication_jobs(
    neo4j_session: neo4j.Session,
    jobs: list[dict[str, Any]],
    cluster_id: str,
    update_tag: int,
) -> None:
    load(
        neo4j_session,
        ProxmoxReplicationJobSchema(),
        jobs,
        lastupdated=update_tag,
        CLUSTER_ID=cluster_id,
    )


def cleanup(
    neo4j_session: neo4j.Session,
    common_job_parameters: dict[str, Any],
) -> None:
    """
    Remove stale replication jobs of the cluster.

    :param neo4j_session: Neo4j session
    :param common_job_parameters: Must include UPDATE_TAG and CLUSTER_ID
    """
    GraphJob.from_node_schema(
        ProxmoxReplicationJobSchema(),
        common_job_parameters,
    ).run(neo4j_session)


# ============================================================================
# SYNC function
# ============================================================================


def _read_states(proxmox_client: Any) -> dict[str, dict[str, Any]]:
    """
    Read the run state of every replication job from the node running its guest.

    The node list already carries the state of each job. The per-job status
    endpoint is only called for entries that come back with nothing but an ID.
    """
    states: dict[str, dict[str, Any]] = {}
    for node in cluster.get_nodes(proxmox_client):
        if node.get("status", "online") != "online":
            continue
        node_name = node["node"]
        for entry in get_node_replication_status(proxmox_client, node_name):
            job_id = entry["id"]
            if set(entry) <= {"id"}:
                entry = get_replication_job_status(proxmox_client, node_name, job_id)
            states[job_id] = entry
    return states


@timeit
def sync(
    neo4j_session: neo4j.Session,
    proxmox_client: Any,
    cluster_id: str,
    update_tag: int,
    common_job_parameters: dict[str, Any],
) -> None:
    """
    Sync replication jobs with their last run state.

    :param neo4j_session: Neo4j session
    :param proxmox_client: Proxmox API client
    :param cluster_id: Parent cluster ID
    :param update_tag: Sync timestamp
    :param common_job_parameters: Common parameters
    """
    logger.info("Syncing Proxmox replication jobs")

    jobs = get_cluster_replication_jobs(proxmox_client)
    if not jobs:
        logger.info("No replication jobs found")
        return

    states = _read_states(proxmox_client)
    transformed = transform_replication_jobs(jobs, states, cluster_id)
    load_replication_jobs(neo4j_session, transformed, cluster_id, update_tag)

    logger.info(
        "Synced %d replication jobs, %d with failed runs",
        len(transformed),
        sum(1 for job in transformed if job["fail_count"]),
    )
