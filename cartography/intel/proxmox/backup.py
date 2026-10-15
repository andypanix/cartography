"""
Sync Proxmox backup jobs.

Follows Cartography's Get → Transform → Load pattern.
"""

import logging
from typing import Any

import neo4j

from cartography.client.core.tx import load
from cartography.models.proxmox.backup import ProxmoxBackupJobSchema
from cartography.util import timeit

logger = logging.getLogger(__name__)


# ============================================================================
# GET functions - retrieve data from Proxmox API
# ============================================================================


@timeit
def get_backup_jobs(proxmox_client: Any) -> list[dict[str, Any]]:
    """
    Get all backup jobs in the cluster.

    :param proxmox_client: Proxmox API client
    :return: List of backup job dicts
    :raises: Exception if API call fails
    """
    return proxmox_client.cluster.backup.get()


# ============================================================================
# TRANSFORM functions - manipulate data for graph ingestion
# ============================================================================


def _parse_backup_vmids(vmid_field: str | int | None) -> list[int]:
    """
    Return the VM IDs a backup job lists explicitly.

    The vmid field holds one ID ("100"), a comma-separated list ("100,101"),
    "all", or a pool reference ("pool:name"). Only explicit IDs map to guests:
    "all" and pool references select guests at run time.

    :param vmid_field: Raw vmid field of the backup job
    :return: List of VM IDs, empty when the job does not list guests explicitly
    """
    if vmid_field is None:
        return []
    vmids = str(vmid_field)
    if vmids == "all" or vmids.startswith("pool:"):
        return []
    return [int(vmid.strip()) for vmid in vmids.split(",") if vmid.strip().isdigit()]


def transform_backup_job_data(
    jobs: list[dict[str, Any]],
    cluster_id: str,
) -> list[dict[str, Any]]:
    """
    Transform backup job data into standard format.

    Per Cartography guidelines:
    - Use data['field'] for required fields (will raise KeyError if missing)
    - Use data.get('field') for optional fields

    :param jobs: Raw backup job data from API
    :param cluster_id: Parent cluster ID
    :return: List of transformed backup job dicts
    """
    transformed_jobs = []

    for job in jobs:
        # Required field - use direct access
        job_id = job["id"]

        # Parse prune settings if they exist. The Proxmox API returns a map like:
        # {"keep-last": "2", "keep-weekly": "4", ...}
        # Neo4j properties cannot store maps, so we flatten into individual primitive properties.
        prune_cfg = job.get("prune-backups") or {}

        def _convert(value: Any) -> Any:
            # Convert numeric strings to int; leave others (None or non-digit strings) as-is
            if isinstance(value, str) and value.isdigit():
                try:
                    return int(value)
                except ValueError:
                    return value
            return value

        prune_keep_last = _convert(prune_cfg.get("keep-last"))
        prune_keep_hourly = _convert(prune_cfg.get("keep-hourly"))
        prune_keep_daily = _convert(prune_cfg.get("keep-daily"))
        prune_keep_weekly = _convert(prune_cfg.get("keep-weekly"))
        prune_keep_monthly = _convert(prune_cfg.get("keep-monthly"))
        prune_keep_yearly = _convert(prune_cfg.get("keep-yearly"))

        transformed_jobs.append(
            {
                "id": job_id,
                "job_id": job_id,
                "cluster_id": cluster_id,
                "schedule": job.get("schedule"),
                "storage": job.get("storage"),
                "enabled": job.get("enabled", True),
                "mode": job.get("mode", "snapshot"),
                "compression": job.get("compress"),
                "mailnotification": job.get("mailnotification"),
                "mailto": job.get("mailto"),
                "notes": job.get("notes"),
                "prune_keep_last": prune_keep_last,
                "prune_keep_hourly": prune_keep_hourly,
                "prune_keep_daily": prune_keep_daily,
                "prune_keep_weekly": prune_keep_weekly,
                "prune_keep_monthly": prune_keep_monthly,
                "prune_keep_yearly": prune_keep_yearly,
                "repeat_missed": job.get("repeat-missed", False),
                "vmids": _parse_backup_vmids(job.get("vmid")),
            }
        )

    return transformed_jobs


# ============================================================================
# LOAD functions - ingest data to Neo4j using modern data model
# ============================================================================


def load_backup_jobs(
    neo4j_session: neo4j.Session,
    jobs: list[dict[str, Any]],
    cluster_id: str,
    update_tag: int,
) -> None:
    """
    Load backup job data into Neo4j using modern data model.

    :param neo4j_session: Neo4j session
    :param jobs: List of transformed backup job dicts
    :param cluster_id: Parent cluster ID
    :param update_tag: Sync timestamp
    """
    load(
        neo4j_session,
        ProxmoxBackupJobSchema(),
        jobs,
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
    Sync backup job data.

    Follows Cartography's Get → Transform → Load pattern.

    :param neo4j_session: Neo4j session
    :param proxmox_client: Proxmox API client
    :param cluster_id: Parent cluster ID
    :param update_tag: Sync timestamp
    :param common_job_parameters: Common parameters
    """
    logger.info("Syncing Proxmox backup jobs")

    # GET - retrieve data from API
    jobs = get_backup_jobs(proxmox_client)

    if not jobs:
        logger.info("No backup jobs found")
        return

    # TRANSFORM - manipulate data for ingestion
    transformed_jobs = transform_backup_job_data(jobs, cluster_id)

    # LOAD - ingest to Neo4j
    load_backup_jobs(neo4j_session, transformed_jobs, cluster_id, update_tag)

    logger.info(
        "Synced %d backup jobs covering %d explicitly listed guests",
        len(transformed_jobs),
        sum(len(job["vmids"]) for job in transformed_jobs),
    )
