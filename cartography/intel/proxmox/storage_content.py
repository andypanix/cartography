"""
Sync the content of Proxmox storage: backup archives, ISO images, and
container templates.

Guest disk volumes (content types images and rootdir) are not ingested: the
compute sync already models them as ProxmoxDisk nodes linked to their storage.
Storage that only holds guest volumes is not listed at all, which keeps the
number of API calls down.

Follows Cartography's Get → Transform → Load pattern.
"""

import logging
from typing import Any

import neo4j

from cartography.client.core.tx import load
from cartography.graph.job import GraphJob
from cartography.intel.proxmox.util import cluster_scoped_id
from cartography.intel.proxmox.util import proxmox_api_retry
from cartography.models.proxmox.storage_content import ProxmoxBackupArchiveSchema
from cartography.models.proxmox.storage_content import ProxmoxStorageTemplateSchema
from cartography.util import timeit

logger = logging.getLogger(__name__)

BACKUP_CONTENT = "backup"
TEMPLATE_CONTENT = frozenset({"iso", "vztmpl"})
LISTED_CONTENT = TEMPLATE_CONTENT | {BACKUP_CONTENT}

# ============================================================================
# GET functions
# ============================================================================


@timeit
@proxmox_api_retry
def get_storage_content(
    proxmox_client: Any,
    node_name: str,
    storage_name: str,
) -> list[dict[str, Any]]:
    """
    List the volumes of a storage as seen from a node.

    :param proxmox_client: Proxmox API client
    :param node_name: Node name
    :param storage_name: Storage name
    :return: List of volume dicts
    """
    return proxmox_client.nodes(node_name).storage(storage_name).content.get()


# ============================================================================
# TRANSFORM functions
# ============================================================================


def _content_types(status: dict[str, Any]) -> set[str]:
    content = status.get("content") or ""
    return {c.strip() for c in content.split(",") if c.strip()}


def plan_content_reads(
    storage_status_map: dict[str, list[dict[str, Any]]],
) -> list[tuple[str, str, bool]]:
    """
    Choose which storage to list on which node.

    Only enabled, active storage that can hold backups, ISO images, or
    container templates is listed. Shared storage is listed from the first
    node where it is active, storage local to a node from every node.

    :param storage_status_map: Map of node_name -> /nodes/{node}/storage response
    :return: List of (node_name, storage_name, shared)
    """
    reads = []
    shared_seen: set[str] = set()
    for node_name in sorted(storage_status_map):
        for status in storage_status_map[node_name]:
            storage_name = status.get("storage")
            if not storage_name:
                continue
            if not status.get("active") or status.get("enabled", 1) == 0:
                continue
            if not _content_types(status) & LISTED_CONTENT:
                continue
            shared = bool(status.get("shared"))
            if shared:
                if storage_name in shared_seen:
                    continue
                shared_seen.add(storage_name)
            reads.append((node_name, storage_name, shared))
    return reads


def _content_type(volume: dict[str, Any]) -> str | None:
    """
    Return the content type of a volume.

    The type comes from the content field when present, otherwise from the
    volume ID path, such as local:backup/..., local:iso/..., or local:vztmpl/....
    """
    if volume.get("content"):
        return volume["content"]
    _, _, path = volume.get("volid", "").partition(":")
    prefix = path.split("/", 1)[0]
    if prefix in LISTED_CONTENT:
        return prefix
    return None


def transform_storage_content(
    volumes: list[dict[str, Any]],
    node_name: str,
    storage_name: str,
    shared: bool,
    cluster_id: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """
    Split the volumes of one storage into backup archives and templates.

    :param volumes: Raw storage content response
    :param node_name: Node the content was read from
    :param storage_name: Storage name
    :param shared: Whether the storage is shared across nodes
    :param cluster_id: Parent cluster ID
    :return: Tuple of (backup archives, ISO images and container templates)
    """
    archives = []
    templates = []
    node = None if shared else node_name
    for volume in volumes:
        content = _content_type(volume)
        if content not in LISTED_CONTENT:
            continue
        volid = volume["volid"]
        common = {
            "id": cluster_scoped_id(
                cluster_id,
                volid if shared else f"{node_name}/{volid}",
            ),
            "cluster_id": cluster_id,
            "volid": volid,
            "storage": storage_name,
            "storage_id": cluster_scoped_id(cluster_id, storage_name),
            "node": node,
            "format": volume.get("format"),
            "size": volume.get("size", volume.get("approximate-size")),
            "ctime": volume.get("ctime"),
        }
        if content in TEMPLATE_CONTENT:
            templates.append({**common, "content": content})
            continue
        encrypted = volume.get("encrypted")
        verification = volume.get("verification") or {}
        archives.append(
            {
                **common,
                "vmid": volume.get("vmid"),
                "notes": volume.get("notes"),
                "protected": bool(volume.get("protected")),
                "encrypted": bool(encrypted) and str(encrypted) != "0",
                "encryption_key_fingerprint": (
                    encrypted if encrypted and str(encrypted) != "1" else None
                ),
                "verification_state": verification.get("state"),
            },
        )
    return archives, templates


# ============================================================================
# LOAD functions
# ============================================================================


def load_storage_content(
    neo4j_session: neo4j.Session,
    archives: list[dict[str, Any]],
    templates: list[dict[str, Any]],
    cluster_id: str,
    update_tag: int,
) -> None:
    load(
        neo4j_session,
        ProxmoxBackupArchiveSchema(),
        archives,
        lastupdated=update_tag,
        CLUSTER_ID=cluster_id,
    )
    load(
        neo4j_session,
        ProxmoxStorageTemplateSchema(),
        templates,
        lastupdated=update_tag,
        CLUSTER_ID=cluster_id,
    )


def cleanup(
    neo4j_session: neo4j.Session,
    common_job_parameters: dict[str, Any],
) -> None:
    """
    Remove stale backup archives and templates of the cluster.

    :param neo4j_session: Neo4j session
    :param common_job_parameters: Must include UPDATE_TAG and CLUSTER_ID
    """
    GraphJob.from_node_schema(
        ProxmoxBackupArchiveSchema(),
        common_job_parameters,
    ).run(neo4j_session)
    GraphJob.from_node_schema(
        ProxmoxStorageTemplateSchema(),
        common_job_parameters,
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
    storage_status_map: dict[str, list[dict[str, Any]]],
) -> None:
    """
    Sync backup archives, ISO images, and container templates.

    :param neo4j_session: Neo4j session
    :param proxmox_client: Proxmox API client
    :param cluster_id: Parent cluster ID
    :param update_tag: Sync timestamp
    :param common_job_parameters: Common parameters
    :param storage_status_map: Map of node_name -> storage status list from the storage sync
    """
    logger.info("Syncing Proxmox storage content")

    archives: list[dict[str, Any]] = []
    templates: list[dict[str, Any]] = []
    reads = plan_content_reads(storage_status_map)
    for node_name, storage_name, shared in reads:
        volumes = get_storage_content(proxmox_client, node_name, storage_name)
        storage_archives, storage_templates = transform_storage_content(
            volumes,
            node_name,
            storage_name,
            shared,
            cluster_id,
        )
        archives.extend(storage_archives)
        templates.extend(storage_templates)

    load_storage_content(neo4j_session, archives, templates, cluster_id, update_tag)

    logger.info(
        "Synced %d backup archives and %d ISO images and templates from %d storage listings",
        len(archives),
        len(templates),
        len(reads),
    )
