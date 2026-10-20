"""
Sync the hyper-converged Ceph cluster of a Proxmox VE cluster.

Follows Cartography's Get → Transform → Load pattern.

Most per-node Ceph endpoints of Proxmox VE (monitors, managers, metadata
servers, OSD tree, pools, CRUSH rules, file systems) answer with cluster-wide
data, so they are read from one node only. OSD metadata and LVM details are
local to the node that holds the OSD and are read from that node.

The CRUSH map is read as decompiled text from the same node and parsed by
ceph_crush. A CRUSH map that cannot be read or parsed is logged and skipped,
the rest of Ceph is still synced, and the existing CRUSH buckets, CRUSH rule
details and device classes are kept.
"""

import logging
from dataclasses import dataclass
from typing import Any
from typing import Callable
from typing import TypeVar

import neo4j
import requests
from proxmoxer.core import ResourceException

from cartography.client.core.tx import load
from cartography.client.core.tx import read_list_of_dicts_tx
from cartography.graph.job import GraphJob
from cartography.intel.proxmox import cluster
from cartography.intel.proxmox import storage
from cartography.intel.proxmox.ceph_crush import CrushMap
from cartography.intel.proxmox.ceph_crush import CrushMapParseError
from cartography.intel.proxmox.ceph_crush import parse_crush_map
from cartography.intel.proxmox.ceph_crush import transform_crush_buckets
from cartography.intel.proxmox.ceph_crush import transform_crush_rule_details
from cartography.intel.proxmox.util import cluster_scoped_id
from cartography.intel.proxmox.util import proxmox_api_retry
from cartography.intel.proxmox.util import proxmox_optional_endpoint
from cartography.models.proxmox.ceph import ProxmoxCephClusterSchema
from cartography.models.proxmox.ceph import ProxmoxCephCrushBucketSchema
from cartography.models.proxmox.ceph import ProxmoxCephCrushRuleSchema
from cartography.models.proxmox.ceph import ProxmoxCephFilesystemSchema
from cartography.models.proxmox.ceph import ProxmoxCephManagerSchema
from cartography.models.proxmox.ceph import ProxmoxCephMetadataServerSchema
from cartography.models.proxmox.ceph import ProxmoxCephMonitorSchema
from cartography.models.proxmox.ceph import ProxmoxCephOSDSchema
from cartography.models.proxmox.ceph import ProxmoxCephPoolSchema
from cartography.util import timeit

logger = logging.getLogger(__name__)

T = TypeVar("T")

# pve-manager (PVE/Ceph/Tools.pm) dies with one of these messages, sent as an
# HTTP 500, when Ceph is not installed or not set up on the queried node:
# "binary not installed: ...", "pveceph configuration not initialized - ...",
# "ceph not fully configured - missing ...".
CEPH_NOT_PRESENT_MESSAGES = (
    "binary not installed",
    "configuration not initialized",
    "ceph not fully configured",
)

# Default pool of an RBD storage without a pool option (PVE::Storage::RBDPlugin).
DEFAULT_RBD_POOL = "rbd"


def is_ceph_not_present(exc: Exception) -> bool:
    """
    Check if a Proxmox API error means Ceph is not installed or not initialized.

    :param exc: The exception raised by the Proxmox API client
    :return: True for a 500 response whose message says Ceph is missing
    """
    if not isinstance(exc, ResourceException) or exc.status_code != 500:
        return False
    message = str(exc).lower()
    return any(m in message for m in CEPH_NOT_PRESENT_MESSAGES)


# ============================================================================
# GET functions
# ============================================================================


@timeit
@proxmox_api_retry
def get_ceph_status(proxmox_client: Any) -> dict[str, Any]:
    """
    Get the Ceph cluster status (raw `ceph status` output).

    :param proxmox_client: Proxmox API client
    :return: Ceph status dict, with fsid and health
    """
    return proxmox_client.cluster.ceph.status.get()


@timeit
@proxmox_api_retry
def get_ceph_node_status(proxmox_client: Any, node_name: str) -> dict[str, Any]:
    """
    Get the Ceph cluster status through one node.

    The answer is cluster-wide, but the node checks for Ceph locally.

    :param proxmox_client: Proxmox API client
    :param node_name: Node to query
    :return: Ceph status dict, with fsid and health
    """
    return proxmox_client.nodes(node_name).ceph.status.get()


@timeit
@proxmox_api_retry
def get_ceph_metadata(proxmox_client: Any, scope: str = "all") -> dict[str, Any]:
    """
    Get the metadata of every Ceph daemon and the Ceph version of every node.

    :param proxmox_client: Proxmox API client
    :param scope: "all", or "versions" for the per-node versions only, which
        also works on a node without Ceph
    :return: Dict with mon, mgr, mds, osd, and node entries
    """
    return proxmox_client.cluster.ceph.metadata.get(scope=scope)


@timeit
@proxmox_api_retry
def get_ceph_flags(proxmox_client: Any) -> list[dict[str, Any]]:
    """
    Get the cluster-wide OSD flags and whether each one is set.

    :param proxmox_client: Proxmox API client
    :return: List of flag dicts with name and value
    """
    return proxmox_client.cluster.ceph.flags.get()


@timeit
@proxmox_optional_endpoint(list)
@proxmox_api_retry
def get_ceph_health_mutes(proxmox_client: Any) -> list[dict[str, Any]]:
    """
    Get the muted Ceph health checks. Proxmox VE 9 only.

    :param proxmox_client: Proxmox API client
    :return: List of muted check dicts, empty on Proxmox VE 8
    """
    return proxmox_client.cluster.ceph("health-mute").get()


@timeit
@proxmox_api_retry
def get_ceph_monitors(proxmox_client: Any, node_name: str) -> list[dict[str, Any]]:
    """
    Get every Ceph monitor of the cluster.

    :param proxmox_client: Proxmox API client
    :param node_name: Node to query, any node with Ceph installed
    :return: List of monitor dicts
    """
    return proxmox_client.nodes(node_name).ceph.mon.get()


@timeit
@proxmox_api_retry
def get_ceph_managers(proxmox_client: Any, node_name: str) -> list[dict[str, Any]]:
    """
    Get every Ceph manager of the cluster.

    :param proxmox_client: Proxmox API client
    :param node_name: Node to query, any node with Ceph installed
    :return: List of manager dicts
    """
    return proxmox_client.nodes(node_name).ceph.mgr.get()


@timeit
@proxmox_api_retry
def get_ceph_metadata_servers(
    proxmox_client: Any,
    node_name: str,
) -> list[dict[str, Any]]:
    """
    Get every Ceph metadata server of the cluster.

    :param proxmox_client: Proxmox API client
    :param node_name: Node to query, any node with Ceph installed
    :return: List of metadata server dicts
    """
    return proxmox_client.nodes(node_name).ceph.mds.get()


@timeit
@proxmox_api_retry
def get_ceph_osd_tree(proxmox_client: Any, node_name: str) -> dict[str, Any]:
    """
    Get the OSD tree of the cluster.

    :param proxmox_client: Proxmox API client
    :param node_name: Node to query, any node with Ceph installed
    :return: Dict with the root CRUSH bucket and the set OSD flags
    """
    return proxmox_client.nodes(node_name).ceph.osd.get()


@timeit
@proxmox_api_retry
def get_ceph_osd_metadata(
    proxmox_client: Any,
    node_name: str,
    osd_id: int,
) -> dict[str, Any]:
    """
    Get the details of one OSD.

    :param proxmox_client: Proxmox API client
    :param node_name: Node that holds the OSD
    :param osd_id: Numeric OSD ID
    :return: Dict with osd and devices entries
    """
    return proxmox_client.nodes(node_name).ceph.osd(osd_id).metadata.get()


@timeit
@proxmox_api_retry
def get_ceph_osd_lv_info(
    proxmox_client: Any,
    node_name: str,
    osd_id: int,
) -> dict[str, Any]:
    """
    Get the LVM logical volume that holds the block device of one OSD.

    :param proxmox_client: Proxmox API client
    :param node_name: Node that holds the OSD
    :param osd_id: Numeric OSD ID
    :return: Dict with the logical volume details
    """
    return proxmox_client.nodes(node_name).ceph.osd(osd_id)("lv-info").get()


@timeit
@proxmox_api_retry
def get_ceph_pools(proxmox_client: Any, node_name: str) -> list[dict[str, Any]]:
    """
    Get every Ceph pool and its settings.

    :param proxmox_client: Proxmox API client
    :param node_name: Node to query, any node with Ceph installed
    :return: List of pool dicts
    """
    return proxmox_client.nodes(node_name).ceph.pool.get()


@timeit
@proxmox_api_retry
def get_ceph_pool_status(
    proxmox_client: Any,
    node_name: str,
    pool_name: str,
) -> dict[str, Any]:
    """
    Get the current settings and protection flags of one Ceph pool.

    :param proxmox_client: Proxmox API client
    :param node_name: Node to query, any node with Ceph installed
    :param pool_name: Pool name
    :return: Pool status dict
    """
    return proxmox_client.nodes(node_name).ceph.pool(pool_name).status.get()


@timeit
@proxmox_api_retry
def get_ceph_rules(proxmox_client: Any, node_name: str) -> list[dict[str, Any]]:
    """
    Get every CRUSH rule of the cluster.

    :param proxmox_client: Proxmox API client
    :param node_name: Node to query, any node with Ceph installed
    :return: List of rule dicts with a name
    """
    return proxmox_client.nodes(node_name).ceph.rules.get()


@timeit
@proxmox_api_retry
def get_ceph_crush_map(proxmox_client: Any, node_name: str) -> str:
    """
    Get the CRUSH map of the cluster, decompiled to text by crushtool.

    :param proxmox_client: Proxmox API client
    :param node_name: Node to query, any node with Ceph installed
    :return: Decompiled CRUSH map text
    """
    return proxmox_client.nodes(node_name).ceph.crush.get()


@timeit
@proxmox_api_retry
def get_ceph_filesystems(proxmox_client: Any, node_name: str) -> list[dict[str, Any]]:
    """
    Get every CephFS file system of the cluster.

    :param proxmox_client: Proxmox API client
    :param node_name: Node to query, any node with Ceph installed
    :return: List of file system dicts
    """
    return proxmox_client.nodes(node_name).ceph.fs.get()


# ============================================================================
# TRANSFORM functions
# ============================================================================


def _optional_bool(value: Any) -> bool | None:
    return None if value is None else bool(value)


def _daemon_id(cluster_id: str, kind: str, name: Any) -> str:
    return cluster_scoped_id(cluster_id, f"{kind}.{name}")


def pool_graph_id(cluster_id: str, pool_name: str) -> str:
    return cluster_scoped_id(cluster_id, f"pool:{pool_name}")


def crush_rule_graph_id(cluster_id: str, rule_name: str) -> str:
    return cluster_scoped_id(cluster_id, f"crush_rule:{rule_name}")


def filesystem_graph_id(cluster_id: str, fs_name: str) -> str:
    return cluster_scoped_id(cluster_id, f"fs:{fs_name}")


def _collect_versions(metadata: dict[str, Any]) -> list[str]:
    versions: set[str] = set()
    for kind in ("mon", "mgr", "mds"):
        for daemon in (metadata.get(kind) or {}).values():
            if daemon.get("ceph_version_short"):
                versions.add(daemon["ceph_version_short"])
    for osd in metadata.get("osd") or []:
        if osd.get("ceph_version_short"):
            versions.add(osd["ceph_version_short"])
    for node in (metadata.get("node") or {}).values():
        version = (node.get("version") or {}).get("str")
        if version:
            versions.add(version)
    return sorted(versions)


def transform_ceph_cluster(
    status: dict[str, Any],
    metadata: dict[str, Any],
    flags: list[dict[str, Any]],
    health_mutes: list[dict[str, Any]] | None,
    cluster_id: str,
    crush: CrushMap | None = None,
) -> dict[str, Any]:
    """
    Transform the Ceph status, metadata, flags, and muted checks into one cluster record.

    :param status: Raw `ceph status` output
    :param metadata: Raw Ceph metadata
    :param flags: Raw OSD flag list
    :param health_mutes: Raw muted health check list, None when unknown
    :param cluster_id: Proxmox VE cluster ID
    :param crush: Parsed CRUSH map, None when it could not be read
    :return: Ceph cluster dict
    """
    fsid = status["fsid"]
    health = status.get("health") or {}
    return {
        "id": cluster_scoped_id(cluster_id, fsid),
        "fsid": fsid,
        "cluster_id": cluster_id,
        "health_status": health.get("status"),
        "health_checks": sorted((health.get("checks") or {}).keys()),
        "muted_health_checks": (
            None if health_mutes is None else sorted(m["code"] for m in health_mutes)
        ),
        "flags": sorted(f["name"] for f in flags if f.get("value")),
        "ceph_versions": _collect_versions(metadata),
        "crush_device_classes": crush.device_classes if crush else None,
    }


def transform_monitors(
    monitors: list[dict[str, Any]],
    cluster_id: str,
    ceph_cluster_id: str,
) -> list[dict[str, Any]]:
    """
    Transform Ceph monitors.

    :param monitors: Raw monitor list
    :param cluster_id: Proxmox VE cluster ID
    :param ceph_cluster_id: Graph ID of the Ceph cluster
    :return: List of monitor dicts
    """
    return [
        {
            "id": _daemon_id(cluster_id, "mon", mon["name"]),
            "name": mon["name"],
            "cluster_id": cluster_id,
            "ceph_cluster_id": ceph_cluster_id,
            "host": mon.get("host"),
            "node_id": (
                cluster_scoped_id(cluster_id, mon["host"]) if mon.get("host") else None
            ),
            "addr": mon.get("addr"),
            "rank": mon.get("rank"),
            "quorum": _optional_bool(mon.get("quorum")),
            "state": mon.get("state"),
            "ceph_version": mon.get("ceph_version_short"),
        }
        for mon in monitors
    ]


def transform_managers(
    managers: list[dict[str, Any]],
    cluster_id: str,
    ceph_cluster_id: str,
) -> list[dict[str, Any]]:
    """
    Transform Ceph managers.

    :param managers: Raw manager list
    :param cluster_id: Proxmox VE cluster ID
    :param ceph_cluster_id: Graph ID of the Ceph cluster
    :return: List of manager dicts
    """
    return [
        {
            "id": _daemon_id(cluster_id, "mgr", mgr["name"]),
            "name": mgr["name"],
            "cluster_id": cluster_id,
            "ceph_cluster_id": ceph_cluster_id,
            "host": mgr.get("host"),
            "node_id": (
                cluster_scoped_id(cluster_id, mgr["host"]) if mgr.get("host") else None
            ),
            "addr": mgr.get("addr"),
            "state": mgr.get("state"),
            "ceph_version": mgr.get("ceph_version_short"),
        }
        for mgr in managers
    ]


def transform_metadata_servers(
    servers: list[dict[str, Any]],
    cluster_id: str,
    ceph_cluster_id: str,
) -> list[dict[str, Any]]:
    """
    Transform Ceph metadata servers.

    :param servers: Raw metadata server list
    :param cluster_id: Proxmox VE cluster ID
    :param ceph_cluster_id: Graph ID of the Ceph cluster
    :return: List of metadata server dicts
    """
    return [
        {
            "id": _daemon_id(cluster_id, "mds", mds["name"]),
            "name": mds["name"],
            "cluster_id": cluster_id,
            "ceph_cluster_id": ceph_cluster_id,
            "host": mds.get("host"),
            "node_id": (
                cluster_scoped_id(cluster_id, mds["host"]) if mds.get("host") else None
            ),
            "addr": mds.get("addr"),
            "state": mds.get("state"),
            "rank": mds.get("rank"),
            "standby_replay": _optional_bool(mds.get("standby_replay")),
            "fs_name": mds.get("fs_name"),
            "filesystem_id": (
                filesystem_graph_id(cluster_id, mds["fs_name"])
                if mds.get("fs_name")
                else None
            ),
            "ceph_version": mds.get("ceph_version_short"),
        }
        for mds in servers
    ]


def extract_osds(osd_tree: dict[str, Any]) -> list[dict[str, Any]]:
    """
    Collect the OSD leaves of the OSD tree, each with the host bucket above it.

    :param osd_tree: Raw OSD tree, with the root CRUSH bucket under root
    :return: List of raw OSD tree entries, with host set
    """
    osds: list[dict[str, Any]] = []

    def walk(entry: dict[str, Any], host: str | None) -> None:
        if entry.get("type") == "host":
            host = entry.get("name")
        if entry.get("type") == "osd":
            osds.append({**entry, "host": entry.get("host") or host})
            return
        for child in entry.get("children") or []:
            walk(child, host)

    walk(osd_tree.get("root") or {}, None)
    return osds


def transform_osds(
    osds: list[dict[str, Any]],
    osd_details: dict[int, dict[str, Any]],
    osd_volumes: dict[int, dict[str, Any]],
    cluster_id: str,
    ceph_cluster_id: str,
) -> list[dict[str, Any]]:
    """
    Transform OSDs, merging the tree entry with the OSD metadata and LVM details.

    :param osds: OSD entries from extract_osds
    :param osd_details: Raw OSD metadata keyed by OSD ID
    :param osd_volumes: Raw OSD logical volume details keyed by OSD ID
    :param cluster_id: Proxmox VE cluster ID
    :param ceph_cluster_id: Graph ID of the Ceph cluster
    :return: List of OSD dicts
    """
    transformed = []
    for osd in osds:
        osd_id = osd["id"]
        details = osd_details.get(osd_id) or {}
        info = details.get("osd") or {}
        devices = details.get("devices") or []
        volume = osd_volumes.get(osd_id) or {}
        physical_devices: set[str] = set()
        for device in devices:
            for name in (device.get("physical_device") or "").replace(",", " ").split():
                physical_devices.add(name)
        transformed.append(
            {
                "id": _daemon_id(cluster_id, "osd", osd_id),
                "osd_id": osd_id,
                "name": osd.get("name") or f"osd.{osd_id}",
                "cluster_id": cluster_id,
                "ceph_cluster_id": ceph_cluster_id,
                "host": osd.get("host"),
                "node_id": (
                    cluster_scoped_id(cluster_id, osd["host"])
                    if osd.get("host")
                    else None
                ),
                "status": osd.get("status"),
                "is_in": _optional_bool(osd.get("in")),
                "device_class": osd.get("device_class"),
                "crush_weight": osd.get("crush_weight"),
                "objectstore": info.get("osd_objectstore"),
                "encrypted": _optional_bool(info.get("encrypted")),
                "ceph_version": info.get("version"),
                "front_addr": info.get("front_addr"),
                "back_addr": info.get("back_addr"),
                "physical_devices": sorted(physical_devices),
                "device_types": sorted({d["type"] for d in devices if d.get("type")}),
                "lv_path": volume.get("lv_path"),
                "vg_name": volume.get("vg_name"),
                "lv_uuid": volume.get("lv_uuid"),
                "lv_size": volume.get("lv_size"),
            }
        )
    return transformed


CRUSH_RULE_DETAIL_KEYS = (
    "rule_id",
    "rule_type",
    "min_size",
    "max_size",
    "take_buckets",
    "device_class",
    "device_classes",
    "failure_domain",
    "steps",
)


def transform_crush_rules(
    rules: list[dict[str, Any]],
    cluster_id: str,
    ceph_cluster_id: str,
    rule_details: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """
    Transform CRUSH rules, adding the details of the decompiled CRUSH map.

    :param rules: Raw rule list
    :param cluster_id: Proxmox VE cluster ID
    :param ceph_cluster_id: Graph ID of the Ceph cluster
    :param rule_details: Rule properties from transform_crush_rule_details,
        keyed by rule name; None when the CRUSH map could not be read
    :return: List of CRUSH rule dicts
    """
    result = []
    for rule in rules:
        details = (rule_details or {}).get(rule["name"]) or {}
        result.append(
            {
                "id": crush_rule_graph_id(cluster_id, rule["name"]),
                "name": rule["name"],
                "cluster_id": cluster_id,
                "ceph_cluster_id": ceph_cluster_id,
                **{key: details.get(key) for key in CRUSH_RULE_DETAIL_KEYS},
            }
        )
    return result


def _is_local_ceph_storage(entry: dict[str, Any], storage_type: str) -> bool:
    # Storage with monhost points to an external Ceph cluster.
    return entry.get("type") == storage_type and not entry.get("monhost")


def map_storage_to_pools(
    storage_list: list[dict[str, Any]],
) -> dict[str, list[str]]:
    """
    Map each Ceph pool name to the RBD storage entries that use it.

    :param storage_list: Raw storage definitions from /storage
    :return: Dict of pool name to storage names
    """
    pool_storage: dict[str, list[str]] = {}
    for entry in storage_list:
        if not _is_local_ceph_storage(entry, "rbd"):
            continue
        pools = {entry.get("pool") or DEFAULT_RBD_POOL}
        if entry.get("data-pool"):
            pools.add(entry["data-pool"])
        for pool in pools:
            pool_storage.setdefault(pool, []).append(entry["storage"])
    return pool_storage


def map_storage_to_filesystems(
    storage_list: list[dict[str, Any]],
    fs_names: list[str],
) -> dict[str, list[str]]:
    """
    Map each CephFS file system name to the CephFS storage entries that mount it.

    A storage without fs-name mounts the default file system; it is mapped only
    when the cluster has exactly one file system, since the default is not
    exposed by the API.

    :param storage_list: Raw storage definitions from /storage
    :param fs_names: Names of the file systems of the cluster
    :return: Dict of file system name to storage names
    """
    fs_storage: dict[str, list[str]] = {}
    for entry in storage_list:
        if not _is_local_ceph_storage(entry, "cephfs"):
            continue
        fs_name = entry.get("fs-name")
        if not fs_name and len(fs_names) == 1:
            fs_name = fs_names[0]
        if fs_name:
            fs_storage.setdefault(fs_name, []).append(entry["storage"])
    return fs_storage


def transform_pools(
    pools: list[dict[str, Any]],
    pool_statuses: dict[str, dict[str, Any]],
    pool_storage: dict[str, list[str]],
    cluster_id: str,
    ceph_cluster_id: str,
) -> list[dict[str, Any]]:
    """
    Transform Ceph pools, merging the pool list with each pool's status.

    :param pools: Raw pool list
    :param pool_statuses: Raw pool status keyed by pool name
    :param pool_storage: Storage names keyed by the pool they use
    :param cluster_id: Proxmox VE cluster ID
    :param ceph_cluster_id: Graph ID of the Ceph cluster
    :return: List of pool dicts
    """
    transformed = []
    for pool in pools:
        name = pool["pool_name"]
        status = pool_statuses.get(name) or {}
        applications = sorted(
            (pool.get("application_metadata") or {}).keys()
            or status.get("application_list")
            or []
        )
        rule_name = pool.get("crush_rule_name") or status.get("crush_rule")
        transformed.append(
            {
                "id": pool_graph_id(cluster_id, name),
                "name": name,
                "cluster_id": cluster_id,
                "ceph_cluster_id": ceph_cluster_id,
                "pool_id": pool.get("pool"),
                "type": pool.get("type"),
                "size": pool.get("size"),
                "min_size": pool.get("min_size"),
                "pg_num": pool.get("pg_num"),
                "pg_autoscale_mode": pool.get("pg_autoscale_mode"),
                "crush_rule": pool.get("crush_rule"),
                "crush_rule_name": rule_name,
                "crush_rule_id": (
                    crush_rule_graph_id(cluster_id, rule_name) if rule_name else None
                ),
                "applications": applications,
                "bytes_used": pool.get("bytes_used"),
                "percent_used": pool.get("percent_used"),
                "nodelete": _optional_bool(status.get("nodelete")),
                "nosizechange": _optional_bool(status.get("nosizechange")),
                "nopgchange": _optional_bool(status.get("nopgchange")),
                "noscrub": _optional_bool(status.get("noscrub")),
                "nodeep_scrub": _optional_bool(status.get("nodeep-scrub")),
                "storage_ids": [
                    cluster_scoped_id(cluster_id, s) for s in pool_storage.get(name, [])
                ],
            }
        )
    return transformed


def transform_filesystems(
    filesystems: list[dict[str, Any]],
    fs_storage: dict[str, list[str]],
    cluster_id: str,
    ceph_cluster_id: str,
) -> list[dict[str, Any]]:
    """
    Transform CephFS file systems.

    :param filesystems: Raw file system list
    :param fs_storage: Storage names keyed by the file system they mount
    :param cluster_id: Proxmox VE cluster ID
    :param ceph_cluster_id: Graph ID of the Ceph cluster
    :return: List of file system dicts
    """
    transformed = []
    for fs in filesystems:
        name = fs["name"]
        # data_pools lists every data pool on Proxmox VE 9; 8.4 only has data_pool.
        data_pools = fs.get("data_pools") or (
            [fs["data_pool"]] if fs.get("data_pool") else []
        )
        pools = set(data_pools)
        if fs.get("metadata_pool"):
            pools.add(fs["metadata_pool"])
        transformed.append(
            {
                "id": filesystem_graph_id(cluster_id, name),
                "name": name,
                "cluster_id": cluster_id,
                "ceph_cluster_id": ceph_cluster_id,
                "metadata_pool": fs.get("metadata_pool"),
                "data_pools": data_pools,
                "pool_ids": sorted(pool_graph_id(cluster_id, p) for p in pools),
                "storage_ids": [
                    cluster_scoped_id(cluster_id, s) for s in fs_storage.get(name, [])
                ],
            }
        )
    return transformed


# ============================================================================
# LOAD functions
# ============================================================================


def load_ceph_data(
    neo4j_session: neo4j.Session,
    schema: Any,
    data: list[dict[str, Any]],
    cluster_id: str,
    update_tag: int,
) -> None:
    """
    Load Ceph records of one node type.

    :param neo4j_session: Neo4j session
    :param schema: Node schema of the records
    :param data: Transformed records
    :param cluster_id: Proxmox VE cluster ID
    :param update_tag: Sync timestamp
    """
    load(
        neo4j_session,
        schema,
        data,
        lastupdated=update_tag,
        CLUSTER_ID=cluster_id,
    )


# ============================================================================
# SYNC helpers
# ============================================================================


def _pick_query_node(
    nodes: list[dict[str, Any]],
    metadata: dict[str, Any],
) -> str | None:
    """
    Pick the online node to read cluster-wide Ceph data from.

    Prefer a node that reports an installed Ceph version: the per-node Ceph
    endpoints fail on a node without the Ceph packages.
    """
    online = sorted(n["node"] for n in nodes if n.get("status") == "online")
    with_ceph = [n for n in online if n in (metadata.get("node") or {})]
    candidates = with_ceph or online
    return candidates[0] if candidates else None


def _get_osd_details(
    proxmox_client: Any,
    osds: list[dict[str, Any]],
    online_nodes: set[str],
) -> tuple[dict[int, dict[str, Any]], dict[int, dict[str, Any]]]:
    """
    Read the metadata and logical volume of each OSD from the node that holds it.

    OSDs on offline nodes keep only the data of the OSD tree.
    """
    details: dict[int, dict[str, Any]] = {}
    volumes: dict[int, dict[str, Any]] = {}
    for osd in osds:
        host = osd.get("host")
        if host not in online_nodes:
            logger.info(
                "Skipping details of Ceph OSD %s: node %s is not online",
                osd["id"],
                host,
            )
            continue
        try:
            details[osd["id"]] = get_ceph_osd_metadata(proxmox_client, host, osd["id"])
        except ResourceException as e:
            # The node can go offline during the sync (HTTP 595): keep the
            # data of the OSD tree instead of failing the whole sync.
            logger.warning(
                "Cannot read details of Ceph OSD %s from node %s, keeping the "
                "OSD tree data only: %s",
                osd["id"],
                host,
                e,
            )
            continue
        try:
            volumes[osd["id"]] = get_ceph_osd_lv_info(proxmox_client, host, osd["id"])
        except ResourceException as e:
            # An OSD not created with ceph-volume lvm has no logical volume:
            # pve-manager answers 500 "OSD '<id>' not found in 'ceph-volume lvm list'".
            if e.status_code != 500 or "ceph-volume lvm list" not in str(e):
                raise
            logger.info("Ceph OSD %s has no LVM volume: %s", osd["id"], e)
    return details, volumes


def _flags_from_osd_tree(osd_tree: dict[str, Any]) -> list[dict[str, Any]]:
    """
    Build the OSD flag list from the comma-joined flags of the OSD tree.
    """
    return [
        {"name": name, "value": 1}
        for name in (osd_tree.get("flags") or "").split(",")
        if name
    ]


def _find_ceph_status(
    proxmox_client: Any,
    online_nodes: list[str],
) -> tuple[dict[str, Any] | None, str | None, bool]:
    """
    Read the Ceph status through the online nodes, one at a time.

    `/cluster/ceph/status` is answered by the node that receives the request,
    which fails when that node has no Ceph monitor, even if other nodes run
    Ceph. Each node checks for Ceph locally, so try them in turn.

    :return: The status, the node that answered, and whether every online node
        confirmed that Ceph is not present (only meaningful without a status)
    """
    absent_everywhere = bool(online_nodes)
    for node in online_nodes:
        try:
            return get_ceph_node_status(proxmox_client, node), node, False
        except ResourceException as e:
            if not is_ceph_not_present(e):
                absent_everywhere = False
                logger.warning("Cannot read Ceph status from node %s: %s", node, e)
            else:
                logger.debug("Ceph is not present on node %s: %s", node, e)
    return None, None, absent_everywhere


def _read_crush_map(proxmox_client: Any, node_name: str) -> CrushMap | None:
    """
    Read and parse the CRUSH map, or return None when that fails.

    A failure is logged and only the CRUSH data is skipped: the rest of Ceph is
    still synced and the existing CRUSH buckets are kept.
    """
    try:
        text = get_ceph_crush_map(proxmox_client, node_name)
    except (ResourceException, requests.exceptions.RequestException) as e:
        logger.warning(
            "Cannot read the Ceph CRUSH map from node %s, skipping CRUSH buckets "
            "and keeping the existing ones: %s",
            node_name,
            e,
        )
        return None
    try:
        return parse_crush_map(text)
    except CrushMapParseError as e:
        logger.warning(
            "Cannot parse the Ceph CRUSH map read from node %s, skipping CRUSH "
            "buckets and keeping the existing ones: %s",
            node_name,
            e,
        )
        return None


def get_last_known_crush_details(
    neo4j_session: neo4j.Session,
    cluster_id: str,
    ceph_cluster_id: str,
) -> tuple[dict[str, dict[str, Any]], list[str] | None]:
    """
    Read the CRUSH details the graph holds from the last readable CRUSH map.

    Used when the CRUSH map cannot be read or parsed, so that the rule details
    and the device classes are loaded again with their last known values
    instead of being written as null.

    :param neo4j_session: Neo4j session
    :param cluster_id: Proxmox VE cluster ID
    :param ceph_cluster_id: Graph ID of the Ceph cluster
    :return: Rule details keyed by rule name, and the device classes of the
        Ceph cluster (None when unknown)
    """
    rows = neo4j_session.execute_read(
        read_list_of_dicts_tx,
        """
        MATCH (r:ProxmoxCephCrushRule {cluster_id: $CLUSTER_ID})
        RETURN r.name AS name, r {.*} AS properties
        """,
        CLUSTER_ID=cluster_id,
    )
    rule_details = {
        row["name"]: {key: row["properties"].get(key) for key in CRUSH_RULE_DETAIL_KEYS}
        for row in rows
    }
    clusters = neo4j_session.execute_read(
        read_list_of_dicts_tx,
        """
        MATCH (c:ProxmoxCephCluster {id: $CEPH_CLUSTER_ID})
        RETURN c.crush_device_classes AS device_classes
        """,
        CEPH_CLUSTER_ID=ceph_cluster_id,
    )
    device_classes = clusters[0]["device_classes"] if clusters else None
    return rule_details, device_classes


def _read_cluster_level(
    call: Callable[[], T], fallback: Callable[[], T], what: str
) -> T:
    """
    Run a `/cluster/ceph` call, using a fallback when the API node lacks Ceph.
    """
    try:
        return call()
    except ResourceException as e:
        if not is_ceph_not_present(e):
            raise
        logger.info("Cannot read Ceph %s through the API node: %s", what, e)
        return fallback()


# ============================================================================
# SYNC function
# ============================================================================


@dataclass(frozen=True)
class CephSyncResult:
    """
    Which Ceph data a sync read completely, to decide which cleanups can run.

    current: the Ceph data is current (synced, or Ceph confirmed absent on
    every online node), so the Ceph cleanup can run.
    crush_current: the CRUSH buckets are current too, so their cleanup can
    run; False when the CRUSH map could not be read or parsed.
    """

    current: bool
    crush_current: bool


@timeit
def sync(
    neo4j_session: neo4j.Session,
    proxmox_client: Any,
    cluster_id: str,
    update_tag: int,
    common_job_parameters: dict[str, Any],
) -> CephSyncResult:
    """
    Sync the Ceph cluster, its daemons, OSDs, pools, CRUSH rules and buckets, and file systems.

    When the API node has no Ceph, the Ceph status is read through the other
    online nodes. The Ceph sync is skipped when no online node has Ceph.

    :param neo4j_session: Neo4j session
    :param proxmox_client: Proxmox API client
    :param cluster_id: Parent cluster ID
    :param update_tag: Sync timestamp
    :param common_job_parameters: Common parameters
    :return: Whether the Ceph data and the CRUSH buckets are current. The
        Ceph data is not current when Ceph could not be read, and the CRUSH
        buckets are not current when the CRUSH map could not be read or
        parsed; the existing data must then be kept.
    """
    logger.info("Syncing Proxmox Ceph")

    # GET - detect Ceph first, with one cluster-wide call
    status_node: str | None = None
    try:
        status: dict[str, Any] | None = get_ceph_status(proxmox_client)
    except ResourceException as e:
        if not is_ceph_not_present(e):
            raise
        logger.info(
            "Ceph is not present on the API node, trying the other nodes: %s", e
        )
        status = None

    nodes = cluster.get_nodes(proxmox_client)
    online = sorted(n["node"] for n in nodes if n.get("status") == "online")
    online_nodes = set(online)

    if status is None:
        status, status_node, absent_everywhere = _find_ceph_status(
            proxmox_client, online
        )
        if status is None:
            if absent_everywhere:
                logger.info("Ceph is not installed or not initialized, skipping")
                return CephSyncResult(current=True, crush_current=True)
            logger.warning(
                "Cannot read Ceph from any online node, skipping Ceph and "
                "keeping the existing Ceph data",
            )
            return CephSyncResult(current=False, crush_current=False)

    metadata = _read_cluster_level(
        lambda: get_ceph_metadata(proxmox_client),
        lambda: get_ceph_metadata(proxmox_client, scope="versions"),
        "metadata",
    )
    health_mutes: list[dict[str, Any]] | None = _read_cluster_level(
        lambda: get_ceph_health_mutes(proxmox_client),
        lambda: None,
        "muted health checks",
    )

    query_node = status_node or _pick_query_node(nodes, metadata)
    if query_node is None:
        logger.warning(
            "No online Proxmox node to read Ceph data from, skipping Ceph and "
            "keeping the existing Ceph data",
        )
        return CephSyncResult(current=False, crush_current=False)

    monitors = get_ceph_monitors(proxmox_client, query_node)
    managers = get_ceph_managers(proxmox_client, query_node)
    metadata_servers = get_ceph_metadata_servers(proxmox_client, query_node)
    osd_tree = get_ceph_osd_tree(proxmox_client, query_node)
    flags = _read_cluster_level(
        lambda: get_ceph_flags(proxmox_client),
        lambda: _flags_from_osd_tree(osd_tree),
        "OSD flags",
    )
    rules = get_ceph_rules(proxmox_client, query_node)
    pools = get_ceph_pools(proxmox_client, query_node)
    pool_statuses = {
        p["pool_name"]: get_ceph_pool_status(proxmox_client, query_node, p["pool_name"])
        for p in pools
    }
    filesystems = get_ceph_filesystems(proxmox_client, query_node)
    crush = _read_crush_map(proxmox_client, query_node)
    osds = extract_osds(osd_tree)
    osd_details, osd_volumes = _get_osd_details(proxmox_client, osds, online_nodes)
    storage_list = storage.get_storage(proxmox_client)

    # TRANSFORM
    ceph_cluster = transform_ceph_cluster(
        status, metadata, flags, health_mutes, cluster_id, crush
    )
    ceph_cluster_id = ceph_cluster["id"]
    fs_names = [fs["name"] for fs in filesystems]
    if crush:
        rule_details = transform_crush_rule_details(crush)
    else:
        # Keep the values read from the last readable CRUSH map, as the
        # CRUSH buckets are kept by skipping their cleanup.
        rule_details, ceph_cluster["crush_device_classes"] = (
            get_last_known_crush_details(neo4j_session, cluster_id, ceph_cluster_id)
        )
    transformed_rules = transform_crush_rules(
        rules,
        cluster_id,
        ceph_cluster_id,
        rule_details,
    )
    transformed_buckets = (
        transform_crush_buckets(
            crush,
            cluster_id,
            ceph_cluster_id,
            lambda name: crush_rule_graph_id(cluster_id, name),
            lambda number: _daemon_id(cluster_id, "osd", number),
        )
        if crush
        else []
    )
    transformed_pools = transform_pools(
        pools,
        pool_statuses,
        map_storage_to_pools(storage_list),
        cluster_id,
        ceph_cluster_id,
    )
    transformed_filesystems = transform_filesystems(
        filesystems,
        map_storage_to_filesystems(storage_list, fs_names),
        cluster_id,
        ceph_cluster_id,
    )
    transformed_monitors = transform_monitors(monitors, cluster_id, ceph_cluster_id)
    transformed_managers = transform_managers(managers, cluster_id, ceph_cluster_id)
    transformed_mds = transform_metadata_servers(
        metadata_servers, cluster_id, ceph_cluster_id
    )
    transformed_osds = transform_osds(
        osds, osd_details, osd_volumes, cluster_id, ceph_cluster_id
    )

    # LOAD - targets of relationships first. CRUSH buckets come last, each
    # child bucket before its parent, because they link to OSDs, CRUSH rules,
    # and each other.
    for schema, data in (
        (ProxmoxCephClusterSchema(), [ceph_cluster]),
        (ProxmoxCephCrushRuleSchema(), transformed_rules),
        (ProxmoxCephPoolSchema(), transformed_pools),
        (ProxmoxCephFilesystemSchema(), transformed_filesystems),
        (ProxmoxCephMonitorSchema(), transformed_monitors),
        (ProxmoxCephManagerSchema(), transformed_managers),
        (ProxmoxCephMetadataServerSchema(), transformed_mds),
        (ProxmoxCephOSDSchema(), transformed_osds),
        (ProxmoxCephCrushBucketSchema(), transformed_buckets),
    ):
        load_ceph_data(neo4j_session, schema, data, cluster_id, update_tag)

    logger.info(
        "Synced Ceph cluster %s: %d monitors, %d managers, %d metadata servers, "
        "%d OSDs, %d pools, %d CRUSH rules, %d CRUSH buckets, %d file systems",
        ceph_cluster["fsid"],
        len(transformed_monitors),
        len(transformed_managers),
        len(transformed_mds),
        len(transformed_osds),
        len(transformed_pools),
        len(transformed_rules),
        len(transformed_buckets),
        len(transformed_filesystems),
    )
    return CephSyncResult(current=True, crush_current=crush is not None)


CEPH_SCHEMAS = (
    ProxmoxCephClusterSchema,
    ProxmoxCephMonitorSchema,
    ProxmoxCephManagerSchema,
    ProxmoxCephMetadataServerSchema,
    ProxmoxCephOSDSchema,
    ProxmoxCephPoolSchema,
    ProxmoxCephCrushRuleSchema,
    ProxmoxCephFilesystemSchema,
)


def cleanup(
    neo4j_session: neo4j.Session,
    common_job_parameters: dict[str, Any],
    include_crush: bool = True,
) -> None:
    """
    Remove stale Ceph nodes and relationships of the cluster.

    :param neo4j_session: Neo4j session
    :param common_job_parameters: Common parameters including UPDATE_TAG and CLUSTER_ID
    :param include_crush: Also remove stale CRUSH buckets; False when the CRUSH
        map could not be read, so the existing buckets are kept
    """
    for schema in CEPH_SCHEMAS:
        GraphJob.from_node_schema(schema(), common_job_parameters).run(neo4j_session)
    if include_crush:
        GraphJob.from_node_schema(
            ProxmoxCephCrushBucketSchema(), common_job_parameters
        ).run(neo4j_session)
    else:
        logger.warning(
            "Skipping cleanup of Ceph CRUSH buckets: the CRUSH map could not be read",
        )
