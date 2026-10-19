"""
Sync what Proxmox backups cover: the guests and disks each backup job
includes, the guests no job covers, and the vzdump defaults of each node.

Runs after the compute, storage, and backup job syncs, because it links to
the guests, disks, storage, and backup jobs they load.

Follows Cartography's Get → Transform → Load pattern.
"""

import logging
from typing import Any

import neo4j

from cartography.client.core.tx import load
from cartography.client.core.tx import load_matchlinks
from cartography.client.core.tx import read_list_of_dicts_tx
from cartography.graph.job import GraphJob
from cartography.intel.proxmox import backup
from cartography.intel.proxmox import cluster
from cartography.intel.proxmox.util import cluster_scoped_id
from cartography.intel.proxmox.util import proxmox_api_retry
from cartography.models.proxmox.backup_coverage import ProxmoxBackupDefaultsSchema
from cartography.models.proxmox.backup_coverage import ProxmoxBackupJobCoversVMMatchLink
from cartography.models.proxmox.backup_coverage import (
    ProxmoxBackupJobIncludesDiskMatchLink,
)
from cartography.models.proxmox.backup_coverage import ProxmoxVMBackupCoverageSchema
from cartography.util import timeit

logger = logging.getLogger(__name__)

# ============================================================================
# GET functions
# ============================================================================


@timeit
@proxmox_api_retry
def get_included_volumes(proxmox_client: Any, job_id: str) -> dict[str, Any]:
    """
    Get the guests a backup job selects and whether each of their volumes is included.

    :param proxmox_client: Proxmox API client
    :param job_id: Backup job ID
    :return: Tree with one child per guest and one grandchild per volume
    """
    return proxmox_client.cluster.backup(job_id).included_volumes.get()


@timeit
@proxmox_api_retry
def get_not_backed_up(proxmox_client: Any) -> list[dict[str, Any]]:
    """
    Get the guests that no backup job covers.

    :param proxmox_client: Proxmox API client
    :return: List of guests with vmid, type, and name
    """
    return proxmox_client.cluster("backup-info")("not-backed-up").get()


@timeit
@proxmox_api_retry
def get_vzdump_defaults(proxmox_client: Any, node_name: str) -> dict[str, Any]:
    """
    Get the vzdump defaults of a node.

    :param proxmox_client: Proxmox API client
    :param node_name: Node name
    :return: Defaults dict, with the keys of /etc/vzdump.conf
    """
    return proxmox_client.nodes(node_name).vzdump.defaults.get()


# ============================================================================
# TRANSFORM functions
# ============================================================================


def transform_included_volumes(
    job_id: str,
    included: dict[str, Any],
    cluster_id: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """
    Turn the included volumes tree of one backup job into guest and disk links.

    Guests of type unknown are removed but not purged, so they are skipped.
    Only volumes the job includes produce a disk link.

    :param job_id: Backup job ID as returned by the API
    :param included: Raw included_volumes response
    :param cluster_id: Parent cluster ID
    :return: Tuple of (guest links, disk links)
    """
    graph_job_id = cluster_scoped_id(cluster_id, job_id)
    guest_links = []
    disk_links = []
    for guest in included.get("children") or []:
        if guest.get("type") not in ("qemu", "lxc"):
            continue
        vmid = int(guest["id"])
        guest_links.append(
            {"job_id": graph_job_id, "vmid": vmid, "cluster_id": cluster_id},
        )
        for volume in guest.get("children") or []:
            if not volume.get("included"):
                continue
            disk_links.append(
                {
                    "job_id": graph_job_id,
                    "vmid": vmid,
                    "disk_id": volume["id"],
                    "cluster_id": cluster_id,
                },
            )
    return guest_links, disk_links


def transform_backup_coverage(
    guests: list[dict[str, Any]],
    not_backed_up: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Flag each synced guest with whether a backup job covers it.

    :param guests: Synced guests, as dicts with id and vmid
    :param not_backed_up: Raw not-backed-up response
    :return: List of dicts with id and backup_covered
    """
    uncovered = {int(guest["vmid"]) for guest in not_backed_up}
    return [
        {"id": guest["id"], "backup_covered": int(guest["vmid"]) not in uncovered}
        for guest in guests
    ]


def _parse_prune_backups(value: Any) -> dict[str, Any]:
    """
    Parse prune-backups, returned as a map or as a property string such as
    "keep-last=3,keep-weekly=2".
    """
    if isinstance(value, dict):
        raw = value
    elif isinstance(value, str):
        raw = dict(
            part.split("=", 1) for part in value.split(",") if "=" in part.strip()
        )
    else:
        return {}
    parsed: dict[str, Any] = {}
    for key, item in raw.items():
        key = key.strip()
        if isinstance(item, str) and item.strip().isdigit():
            parsed[key] = int(item.strip())
        else:
            parsed[key] = item
    return parsed


def _bool(value: Any) -> bool | None:
    if value is None:
        return None
    return str(value) in ("1", "true", "True")


def transform_vzdump_defaults(
    defaults_by_node: dict[str, dict[str, Any]],
    cluster_id: str,
) -> list[dict[str, Any]]:
    """
    Transform the vzdump defaults of each node.

    :param defaults_by_node: Map of node name -> raw vzdump defaults
    :param cluster_id: Parent cluster ID
    :return: List of transformed defaults dicts
    """
    transformed = []
    for node_name, defaults in defaults_by_node.items():
        prune = _parse_prune_backups(defaults.get("prune-backups"))
        storage = defaults.get("storage")
        exclude_path = defaults.get("exclude-path")
        if isinstance(exclude_path, str):
            exclude_path = [exclude_path]
        transformed.append(
            {
                "id": cluster_scoped_id(cluster_id, node_name),
                "cluster_id": cluster_id,
                "node": node_name,
                "node_id": cluster_scoped_id(cluster_id, node_name),
                "storage": storage,
                "storage_id": (
                    cluster_scoped_id(cluster_id, storage) if storage else None
                ),
                "mode": defaults.get("mode"),
                "compress": defaults.get("compress"),
                "bwlimit": defaults.get("bwlimit"),
                "ionice": defaults.get("ionice"),
                "protected": _bool(defaults.get("protected")),
                "remove": _bool(defaults.get("remove")),
                "mailto": defaults.get("mailto"),
                "mailnotification": defaults.get("mailnotification"),
                "notification_mode": defaults.get("notification-mode"),
                "notes_template": defaults.get("notes-template"),
                "script": defaults.get("script"),
                "tmpdir": defaults.get("tmpdir"),
                "dumpdir": defaults.get("dumpdir"),
                "exclude_path": exclude_path,
                "stdexcludes": _bool(defaults.get("stdexcludes")),
                "fleecing": defaults.get("fleecing"),
                "performance": defaults.get("performance"),
                "pbs_change_detection_mode": defaults.get("pbs-change-detection-mode"),
                "zstd": defaults.get("zstd"),
                "pigz": defaults.get("pigz"),
                "lockwait": defaults.get("lockwait"),
                "stopwait": defaults.get("stopwait"),
                "prune_keep_all": _bool(prune.get("keep-all")),
                "prune_keep_last": prune.get("keep-last"),
                "prune_keep_hourly": prune.get("keep-hourly"),
                "prune_keep_daily": prune.get("keep-daily"),
                "prune_keep_weekly": prune.get("keep-weekly"),
                "prune_keep_monthly": prune.get("keep-monthly"),
                "prune_keep_yearly": prune.get("keep-yearly"),
            },
        )
    return transformed


# ============================================================================
# LOAD functions
# ============================================================================


def get_synced_guests(
    neo4j_session: neo4j.Session,
    cluster_id: str,
    update_tag: int,
) -> list[dict[str, Any]]:
    """
    Read the guests the compute sync loaded in this run.

    :param neo4j_session: Neo4j session
    :param cluster_id: Parent cluster ID
    :param update_tag: Sync timestamp
    :return: List of dicts with id and vmid
    """
    return neo4j_session.execute_read(
        read_list_of_dicts_tx,
        """
        MATCH (:ProxmoxCluster {id: $CLUSTER_ID})-[:RESOURCE]->(vm:ProxmoxVM)
        WHERE vm.lastupdated = $UPDATE_TAG AND vm.vmid IS NOT NULL
        RETURN vm.id AS id, vm.vmid AS vmid
        """,
        CLUSTER_ID=cluster_id,
        UPDATE_TAG=update_tag,
    )


def load_backup_coverage(
    neo4j_session: neo4j.Session,
    coverage: list[dict[str, Any]],
    cluster_id: str,
    update_tag: int,
) -> None:
    load(
        neo4j_session,
        ProxmoxVMBackupCoverageSchema(),
        coverage,
        lastupdated=update_tag,
        CLUSTER_ID=cluster_id,
    )


def load_job_links(
    neo4j_session: neo4j.Session,
    guest_links: list[dict[str, Any]],
    disk_links: list[dict[str, Any]],
    cluster_id: str,
    update_tag: int,
) -> None:
    for rel_schema, links in (
        (ProxmoxBackupJobCoversVMMatchLink(), guest_links),
        (ProxmoxBackupJobIncludesDiskMatchLink(), disk_links),
    ):
        load_matchlinks(
            neo4j_session,
            rel_schema,
            links,
            lastupdated=update_tag,
            _sub_resource_label="ProxmoxCluster",
            _sub_resource_id=cluster_id,
        )


def load_vzdump_defaults(
    neo4j_session: neo4j.Session,
    defaults: list[dict[str, Any]],
    cluster_id: str,
    update_tag: int,
) -> None:
    load(
        neo4j_session,
        ProxmoxBackupDefaultsSchema(),
        defaults,
        lastupdated=update_tag,
        CLUSTER_ID=cluster_id,
    )


def cleanup(
    neo4j_session: neo4j.Session,
    common_job_parameters: dict[str, Any],
) -> None:
    """
    Remove stale backup defaults and backup job coverage links of the cluster.

    :param neo4j_session: Neo4j session
    :param common_job_parameters: Must include UPDATE_TAG and CLUSTER_ID
    """
    GraphJob.from_node_schema(
        ProxmoxBackupDefaultsSchema(),
        common_job_parameters,
    ).run(neo4j_session)
    for rel_schema in (
        ProxmoxBackupJobCoversVMMatchLink(),
        ProxmoxBackupJobIncludesDiskMatchLink(),
    ):
        GraphJob.from_matchlink(
            rel_schema,
            "ProxmoxCluster",
            common_job_parameters["CLUSTER_ID"],
            common_job_parameters["UPDATE_TAG"],
        ).run(neo4j_session)


# ============================================================================
# SYNC function
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
    Sync backup coverage: job guests and disks, uncovered guests, and node defaults.

    :param neo4j_session: Neo4j session
    :param proxmox_client: Proxmox API client
    :param cluster_id: Parent cluster ID
    :param update_tag: Sync timestamp
    :param common_job_parameters: Common parameters
    """
    logger.info("Syncing Proxmox backup coverage")

    # Guests and volumes each backup job includes, with "all" and pool
    # selections resolved by Proxmox.
    guest_links: list[dict[str, Any]] = []
    disk_links: list[dict[str, Any]] = []
    for job in backup.get_backup_jobs(proxmox_client):
        included = get_included_volumes(proxmox_client, job["id"])
        job_guests, job_disks = transform_included_volumes(
            job["id"],
            included,
            cluster_id,
        )
        guest_links.extend(job_guests)
        disk_links.extend(job_disks)
    load_job_links(neo4j_session, guest_links, disk_links, cluster_id, update_tag)

    # Guests no backup job covers
    not_backed_up = get_not_backed_up(proxmox_client)
    guests = get_synced_guests(neo4j_session, cluster_id, update_tag)
    coverage = transform_backup_coverage(guests, not_backed_up)
    load_backup_coverage(neo4j_session, coverage, cluster_id, update_tag)

    # vzdump defaults of each online node
    defaults_by_node = {
        node["node"]: get_vzdump_defaults(proxmox_client, node["node"])
        for node in cluster.get_nodes(proxmox_client)
        if node.get("status", "online") == "online"
    }
    defaults = transform_vzdump_defaults(defaults_by_node, cluster_id)
    load_vzdump_defaults(neo4j_session, defaults, cluster_id, update_tag)

    logger.info(
        "Synced backup coverage: %d job-guest links, %d job-disk links, "
        "%d guests not backed up, defaults of %d nodes",
        len(guest_links),
        len(disk_links),
        len(not_backed_up),
        len(defaults),
    )
