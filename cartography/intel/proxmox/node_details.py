"""
Sync hardware, software and system details of each online Proxmox node.

Covers local disks with their SMART health, ZFS pools, LVM volume groups and
thin pools, managed directory storages, key package versions, APT repositories,
the support subscription, node options, DNS, time zone, system services and
PCI devices.

Follows Cartography's Get → Transform → Load pattern.
"""

import logging
import re
from typing import Any
from urllib.parse import unquote
from urllib.parse import urlsplit
from urllib.parse import urlunsplit

import neo4j
import requests
from proxmoxer.core import ResourceException

from cartography.client.core.tx import load
from cartography.graph.job import GraphJob
from cartography.intel.proxmox import cluster
from cartography.intel.proxmox.util import cluster_scoped_id
from cartography.intel.proxmox.util import proxmox_api_retry
from cartography.models.core.nodes import CartographyNodeSchema
from cartography.models.proxmox.node_software import ProxmoxAPTRepositorySchema
from cartography.models.proxmox.node_software import ProxmoxPackageSchema
from cartography.models.proxmox.node_software import ProxmoxSubscriptionSchema
from cartography.models.proxmox.node_storage import ProxmoxLVMThinPoolSchema
from cartography.models.proxmox.node_storage import ProxmoxLVMVolumeGroupSchema
from cartography.models.proxmox.node_storage import ProxmoxManagedDirectorySchema
from cartography.models.proxmox.node_storage import ProxmoxPhysicalDiskSchema
from cartography.models.proxmox.node_storage import ProxmoxZFSPoolSchema
from cartography.models.proxmox.node_system import ProxmoxNodeConfigSchema
from cartography.models.proxmox.node_system import ProxmoxPCIDeviceSchema
from cartography.models.proxmox.node_system import ProxmoxServiceSchema
from cartography.util import timeit

logger = logging.getLogger(__name__)

# Schemas in load order: disks first so pools, volume groups and directories
# can link to them, volume groups before the thin pools they contain.
NODE_DETAIL_SCHEMAS: tuple[CartographyNodeSchema, ...] = (
    ProxmoxPhysicalDiskSchema(),
    ProxmoxZFSPoolSchema(),
    ProxmoxLVMVolumeGroupSchema(),
    ProxmoxLVMThinPoolSchema(),
    ProxmoxManagedDirectorySchema(),
    ProxmoxPackageSchema(),
    ProxmoxAPTRepositorySchema(),
    ProxmoxSubscriptionSchema(),
    ProxmoxNodeConfigSchema(),
    ProxmoxServiceSchema(),
    ProxmoxPCIDeviceSchema(),
)

# ATA SMART attribute IDs. Proxmox derives the SSD wearout from the first wear
# attribute the disk reports; these are the ones its vendor table uses.
SMART_ATTR_REALLOCATED_SECTORS = 5
SMART_ATTR_POWER_ON_HOURS = 9
SMART_ATTR_TEMPERATURE = (194, 190)
SMART_ATTR_WEAR = (233, 177, 231, 202)

# Lines of the smartctl text output that Proxmox returns for NVMe and SAS disks.
SMART_TEXT_PATTERNS = {
    "power_on_hours": (
        re.compile(r"^Power On Hours:\s+([\d,.]+)", re.MULTILINE),
        re.compile(r"^Accumulated power on time, hours:minutes\s+(\d+)", re.MULTILINE),
    ),
    "percentage_used": (
        re.compile(r"^Percentage Used:\s+(\d+)%", re.MULTILINE),
        re.compile(r"^Percentage used endurance indicator:\s+(\d+)%", re.MULTILINE),
    ),
    "temperature": (
        re.compile(r"^Temperature:\s+(\d+) Celsius", re.MULTILINE),
        re.compile(r"^Current Drive Temperature:\s+(\d+) C", re.MULTILINE),
    ),
    "reallocated_sectors": (
        re.compile(r"^Elements in grown defect list:\s+(\d+)", re.MULTILINE),
    ),
}

STANDARD_REPO_ENTERPRISE = "enterprise"
STANDARD_REPO_NO_SUBSCRIPTION = "no-subscription"
STANDARD_REPO_TEST = "test"

# Errors of one API call that skip one device or node instead of the whole sync:
# HTTP errors (such as a 500 from smartctl, a 595 for an unreachable node or a
# 403 from a custom role) and connection errors that outlast the retries.
PROXMOX_API_ERRORS = (ResourceException, requests.exceptions.RequestException)

# Query parameters of an APT repository URI that can carry a credential.
URI_SECRET_QUERY_PARAM = re.compile(
    r"token|key|pass|secret|auth|sig|credential|session",
    re.IGNORECASE,
)
# userinfo in a URI embedded in free text, such as an APT parse error.
URI_USERINFO_IN_TEXT = re.compile(r"(?P<scheme>[A-Za-z][A-Za-z0-9+.-]*://)[^/\s@]+@")


# ============================================================================
# GET functions - retrieve data from Proxmox API
# ============================================================================


@timeit
@proxmox_api_retry
def get_node_disks(proxmox_client: Any, node_name: str) -> list[dict[str, Any]]:
    """
    List the local disks of a node.

    :param proxmox_client: Proxmox API client
    :param node_name: Node name
    :return: List of disk dicts
    """
    return proxmox_client.nodes(node_name).disks.list.get()


@timeit
@proxmox_api_retry
def get_disk_smart(proxmox_client: Any, node_name: str, devpath: str) -> dict[str, Any]:
    """
    Get the SMART data of one disk.

    :param proxmox_client: Proxmox API client
    :param node_name: Node name
    :param devpath: Device path of the disk, such as /dev/sda
    :return: SMART data dict
    """
    return proxmox_client.nodes(node_name).disks.smart.get(disk=devpath)


@timeit
@proxmox_api_retry
def get_zfs_pools(proxmox_client: Any, node_name: str) -> list[dict[str, Any]]:
    """
    List the ZFS pools of a node.

    :param proxmox_client: Proxmox API client
    :param node_name: Node name
    :return: List of pool dicts
    """
    return proxmox_client.nodes(node_name).disks.zfs.get()


@timeit
@proxmox_api_retry
def get_zfs_pool_details(
    proxmox_client: Any,
    node_name: str,
    pool_name: str,
) -> dict[str, Any]:
    """
    Get the state, errors and vdev tree of one ZFS pool.

    :param proxmox_client: Proxmox API client
    :param node_name: Node name
    :param pool_name: ZFS pool name
    :return: Pool details dict
    """
    return proxmox_client.nodes(node_name).disks.zfs(pool_name).get()


@timeit
@proxmox_api_retry
def get_lvm_volume_groups(proxmox_client: Any, node_name: str) -> dict[str, Any]:
    """
    List the LVM volume groups of a node with their physical volumes.

    :param proxmox_client: Proxmox API client
    :param node_name: Node name
    :return: Tree dict whose children are the volume groups
    """
    return proxmox_client.nodes(node_name).disks.lvm.get()


@timeit
@proxmox_api_retry
def get_lvm_thin_pools(proxmox_client: Any, node_name: str) -> list[dict[str, Any]]:
    """
    List the LVM thin pools of a node.

    :param proxmox_client: Proxmox API client
    :param node_name: Node name
    :return: List of thin pool dicts
    """
    return proxmox_client.nodes(node_name).disks.lvmthin.get()


@timeit
@proxmox_api_retry
def get_managed_directories(
    proxmox_client: Any,
    node_name: str,
) -> list[dict[str, Any]]:
    """
    List the directory storages that Proxmox created and mounts on a node.

    :param proxmox_client: Proxmox API client
    :param node_name: Node name
    :return: List of directory dicts
    """
    return proxmox_client.nodes(node_name).disks.directory.get()


@timeit
@proxmox_api_retry
def get_package_versions(proxmox_client: Any, node_name: str) -> list[dict[str, Any]]:
    """
    Get the versions of the important Proxmox packages of a node.

    :param proxmox_client: Proxmox API client
    :param node_name: Node name
    :return: List of package dicts
    """
    return proxmox_client.nodes(node_name).apt.versions.get()


@timeit
@proxmox_api_retry
def get_apt_repositories(proxmox_client: Any, node_name: str) -> dict[str, Any]:
    """
    Get the parsed APT repository configuration of a node.

    :param proxmox_client: Proxmox API client
    :param node_name: Node name
    :return: Repository information dict
    """
    return proxmox_client.nodes(node_name).apt.repositories.get()


@timeit
@proxmox_api_retry
def get_subscription(proxmox_client: Any, node_name: str) -> dict[str, Any]:
    """
    Get the subscription status of a node.

    :param proxmox_client: Proxmox API client
    :param node_name: Node name
    :return: Subscription dict
    """
    return proxmox_client.nodes(node_name).subscription.get()


@timeit
@proxmox_api_retry
def get_node_config(proxmox_client: Any, node_name: str) -> dict[str, Any]:
    """
    Get the node configuration options.

    :param proxmox_client: Proxmox API client
    :param node_name: Node name
    :return: Node configuration dict
    """
    return proxmox_client.nodes(node_name).config.get()


@timeit
@proxmox_api_retry
def get_node_dns(proxmox_client: Any, node_name: str) -> dict[str, Any]:
    """
    Get the DNS settings of a node.

    :param proxmox_client: Proxmox API client
    :param node_name: Node name
    :return: DNS settings dict
    """
    return proxmox_client.nodes(node_name).dns.get()


@timeit
@proxmox_api_retry
def get_node_time(proxmox_client: Any, node_name: str) -> dict[str, Any]:
    """
    Get the time and time zone settings of a node.

    :param proxmox_client: Proxmox API client
    :param node_name: Node name
    :return: Time settings dict
    """
    return proxmox_client.nodes(node_name).time.get()


@timeit
@proxmox_api_retry
def get_node_services(proxmox_client: Any, node_name: str) -> list[dict[str, Any]]:
    """
    List the Proxmox system services of a node.

    :param proxmox_client: Proxmox API client
    :param node_name: Node name
    :return: List of service dicts
    """
    return proxmox_client.nodes(node_name).services.get()


@timeit
@proxmox_api_retry
def get_pci_devices(proxmox_client: Any, node_name: str) -> list[dict[str, Any]]:
    """
    List the PCI devices of a node, without the classes Proxmox filters by default.

    :param proxmox_client: Proxmox API client
    :param node_name: Node name
    :return: List of PCI device dicts
    """
    return proxmox_client.nodes(node_name).hardware.pci.get()


@timeit
@proxmox_api_retry
def get_pci_mdev_types(
    proxmox_client: Any,
    node_name: str,
    pci_id: str,
) -> list[dict[str, Any]]:
    """
    List the mediated device types of a PCI device.

    :param proxmox_client: Proxmox API client
    :param node_name: Node name
    :param pci_id: PCI address of the device
    :return: List of mdev type dicts
    """
    return proxmox_client.nodes(node_name).hardware.pci(pci_id).mdev.get()


# ============================================================================
# TRANSFORM helpers
# ============================================================================


def strip_uri_credentials(uri: Any) -> Any:
    """
    Remove credentials from a repository URI.

    Drops the userinfo (user:password@) and the query parameters whose name
    suggests a credential, such as token, key, auth or signature.

    :param uri: Repository URI, such as https://user:token@repo.example.com/debian
    :return: URI without credentials; non-string values are returned unchanged
    """
    if not isinstance(uri, str):
        return uri
    try:
        parts = urlsplit(uri)
    except ValueError:
        return URI_USERINFO_IN_TEXT.sub(r"\g<scheme>", uri)
    netloc = parts.netloc.rpartition("@")[2]
    # Split by hand to keep the encoding of the parameters that stay.
    query = "&".join(
        param
        for param in parts.query.split("&")
        if param and not URI_SECRET_QUERY_PARAM.search(unquote(param.split("=")[0]))
    )
    return urlunsplit((parts.scheme, netloc, parts.path, query, parts.fragment))


def _strip_text_credentials(text: Any) -> Any:
    """Remove the userinfo of URIs embedded in free text."""
    if not isinstance(text, str):
        return text
    return URI_USERINFO_IN_TEXT.sub(r"\g<scheme>", text)


def _leading_int(value: Any) -> int | None:
    """Return the integer at the start of a SMART raw value such as '35 (Min/Max 20/45)'."""
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    match = re.match(r"\s*(\d+)", str(value))
    return int(match.group(1)) if match else None


def _parse_property_string(value: Any, default_key: str) -> dict[str, str]:
    """
    Parse a Proxmox property string such as 'mac=aa:bb,bind-interface=eth0'.

    A part without '=' is the value of the default key.
    """
    result: dict[str, str] = {}
    if not value or not isinstance(value, str):
        return result
    for part in value.split(","):
        part = part.strip()
        if not part:
            continue
        key, sep, val = part.partition("=")
        if sep:
            result[key.strip()] = val.strip()
        else:
            result[default_key] = part
    return result


def _disk_name(device: str) -> str:
    """Return the last path element of a device, such as sda for /dev/sda."""
    return device.rstrip("/").rsplit("/", 1)[-1]


def match_device_to_disk(device: Any, disks: list[dict[str, Any]]) -> str | None:
    """
    Find the physical disk a device name refers to.

    The device can be the disk itself or one of its partitions, named by kernel
    name (sda, /dev/sda3, nvme0n1p2) or by a /dev/disk/by-id name built from the
    disk WWN (wwn-0x5000c500a1b2c3d4, nvme-eui.0025...) or serial
    (ata-MODEL_SERIAL-part3).

    :param device: Device name as ZFS, LVM or the mount table reports it
    :param disks: Transformed disks of the same node
    :return: Graph ID of the matching disk, or None
    """
    if not device or not isinstance(device, str):
        return None
    name = re.sub(r"-part\d+$", "", _disk_name(device))
    if not name:
        return None

    for disk in disks:
        if name == disk["name"]:
            return disk["id"]

    for disk in disks:
        disk_name = disk["name"]
        # nvme0n1p2 and mmcblk0p1 separate the partition number with "p" when
        # the disk name ends with a digit; sda3 does not.
        suffix = r"p\d+" if disk_name[-1:].isdigit() else r"\d+"
        if re.fullmatch(re.escape(disk_name) + suffix, name):
            return disk["id"]

    _, sep, by_id_rest = name.partition("-")
    if not sep:
        return None
    for disk in disks:
        wwn = disk.get("wwn")
        if wwn and by_id_rest == wwn:
            return disk["id"]
    for disk in disks:
        serial = disk.get("serial")
        if serial and re.search(r"_" + re.escape(serial) + r"(_\d+)?$", name):
            return disk["id"]
    return None


def _match_disk_ids(devices: list[str], disks: list[dict[str, Any]]) -> list[str]:
    ids: list[str] = []
    for device in devices:
        disk_id = match_device_to_disk(device, disks)
        if disk_id and disk_id not in ids:
            ids.append(disk_id)
    return ids


def parse_smart_data(smart: dict[str, Any]) -> dict[str, Any]:
    """
    Keep a small set of SMART values: health, power-on hours, wear, reallocated
    sectors and temperature.

    ATA disks return an attribute table. NVMe and SAS disks return the smartctl
    text output, which is searched for the matching lines.

    :param smart: Response of the disk SMART endpoint
    :return: Dict of SMART properties, None where the disk reports no value
    """
    result: dict[str, Any] = {
        "smart_type": smart.get("type"),
        "smart_health": smart.get("health"),
        "power_on_hours": None,
        "percentage_used": None,
        "reallocated_sectors": None,
        "temperature": None,
    }

    attributes: dict[int, dict[str, Any]] = {}
    for attr in smart.get("attributes") or []:
        attr_id = _leading_int(attr.get("id"))
        if attr_id is not None and attr_id not in attributes:
            attributes[attr_id] = attr

    if attributes:
        if SMART_ATTR_POWER_ON_HOURS in attributes:
            result["power_on_hours"] = _leading_int(
                attributes[SMART_ATTR_POWER_ON_HOURS].get("raw"),
            )
        if SMART_ATTR_REALLOCATED_SECTORS in attributes:
            result["reallocated_sectors"] = _leading_int(
                attributes[SMART_ATTR_REALLOCATED_SECTORS].get("raw"),
            )
        for attr_id in SMART_ATTR_TEMPERATURE:
            if attr_id in attributes:
                result["temperature"] = _leading_int(attributes[attr_id].get("raw"))
                break
        for attr_id in SMART_ATTR_WEAR:
            if attr_id in attributes:
                attr = attributes[attr_id]
                normalized = _leading_int(attr.get("normalized", attr.get("value")))
                if normalized is not None:
                    result["percentage_used"] = max(0, 100 - normalized)
                break

    text = smart.get("text")
    if isinstance(text, str) and text:
        for key, patterns in SMART_TEXT_PATTERNS.items():
            if result[key] is not None:
                continue
            for pattern in patterns:
                match = pattern.search(text)
                if match:
                    digits = re.sub(r"[,.]", "", match.group(1))
                    result[key] = int(digits) if digits else None
                    break

    return result


# ============================================================================
# TRANSFORM functions - storage
# ============================================================================


def transform_disks(
    disks: list[dict[str, Any]],
    smart_by_devpath: dict[str, dict[str, Any]],
    node_name: str,
    cluster_id: str,
) -> list[dict[str, Any]]:
    """
    Transform the disk list of a node, merging the SMART values of each disk.

    :param disks: Response of the disk list endpoint
    :param smart_by_devpath: SMART responses keyed by device path
    :param node_name: Node name
    :param cluster_id: Parent cluster ID
    :return: List of transformed disk dicts
    """
    node_id = cluster_scoped_id(cluster_id, node_name)
    result = []
    for disk in disks:
        devpath = disk["devpath"]
        item = {
            "id": cluster_scoped_id(cluster_id, f"{node_name}:{devpath}"),
            "cluster_id": cluster_id,
            "node_name": node_name,
            "node_id": node_id,
            "devpath": devpath,
            "name": _disk_name(devpath),
            "model": disk.get("model"),
            "vendor": disk.get("vendor"),
            "serial": disk.get("serial"),
            "wwn": disk.get("wwn"),
            "size": disk.get("size"),
            # Returned by the API although its schema does not list it.
            "type": disk.get("type"),
            "health": disk.get("health"),
            "used": disk.get("used"),
            "gpt": bool(disk["gpt"]) if disk.get("gpt") is not None else None,
            "mounted": (
                bool(disk["mounted"]) if disk.get("mounted") is not None else None
            ),
            "osdid": disk.get("osdid"),
            "osdid_list": disk.get("osdid-list"),
        }
        item.update(parse_smart_data(smart_by_devpath.get(devpath) or {}))
        result.append(item)
    return result


def _zfs_leaf_devices(children: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Return the leaf vdevs of a ZFS pool configuration tree.

    The top level holds the pool itself and sections such as logs, cache and
    spares, so only entries below it count as devices.
    """
    leaves: list[dict[str, Any]] = []

    def walk(entries: list[dict[str, Any]], depth: int) -> None:
        for entry in entries:
            sub = entry.get("children") or []
            if sub:
                walk(sub, depth + 1)
            elif depth > 0 and entry.get("name"):
                leaves.append(entry)

    walk(children or [], 0)
    return leaves


def transform_zfs_pools(
    pools: list[dict[str, Any]],
    details_by_name: dict[str, dict[str, Any]],
    disks: list[dict[str, Any]],
    node_name: str,
    cluster_id: str,
) -> list[dict[str, Any]]:
    """
    Transform the ZFS pools of a node, with their state and member disks.

    :param pools: Response of the ZFS pool list endpoint
    :param details_by_name: Pool detail responses keyed by pool name
    :param disks: Transformed disks of the same node
    :param node_name: Node name
    :param cluster_id: Parent cluster ID
    :return: List of transformed pool dicts
    """
    node_id = cluster_scoped_id(cluster_id, node_name)
    result = []
    for pool in pools:
        name = pool["name"]
        details = details_by_name.get(name) or {}
        leaves = _zfs_leaf_devices(details.get("children") or [])
        members = [leaf["name"] for leaf in leaves]
        result.append(
            {
                "id": cluster_scoped_id(cluster_id, f"{node_name}:zfs:{name}"),
                "cluster_id": cluster_id,
                "node_name": node_name,
                "node_id": node_id,
                "name": name,
                "size": pool.get("size"),
                "alloc": pool.get("alloc"),
                "free": pool.get("free"),
                "frag": pool.get("frag"),
                "dedup": pool.get("dedup"),
                "health": pool.get("health"),
                "state": details.get("state"),
                "status": details.get("status"),
                "action": details.get("action"),
                "scan": details.get("scan"),
                "errors": details.get("errors"),
                "member_devices": members,
                "degraded_devices": [
                    leaf["name"]
                    for leaf in leaves
                    if leaf.get("state") and leaf["state"] != "ONLINE"
                ],
                "disk_ids": _match_disk_ids(members, disks),
            },
        )
    return result


def transform_lvm_volume_groups(
    lvm: dict[str, Any],
    disks: list[dict[str, Any]],
    node_name: str,
    cluster_id: str,
) -> list[dict[str, Any]]:
    """
    Transform the LVM volume groups of a node and match their physical volumes to disks.

    :param lvm: Response of the LVM endpoint, a tree whose children are volume groups
    :param disks: Transformed disks of the same node
    :param node_name: Node name
    :param cluster_id: Parent cluster ID
    :return: List of transformed volume group dicts
    """
    node_id = cluster_scoped_id(cluster_id, node_name)
    result = []
    for vg in (lvm or {}).get("children") or []:
        name = vg["name"]
        pvs = [pv["name"] for pv in vg.get("children") or [] if pv.get("name")]
        result.append(
            {
                "id": cluster_scoped_id(cluster_id, f"{node_name}:lvm:{name}"),
                "cluster_id": cluster_id,
                "node_name": node_name,
                "node_id": node_id,
                "name": name,
                "size": vg.get("size"),
                "free": vg.get("free"),
                "physical_volumes": pvs,
                "disk_ids": _match_disk_ids(pvs, disks),
            },
        )
    return result


def transform_lvm_thin_pools(
    thin_pools: list[dict[str, Any]],
    node_name: str,
    cluster_id: str,
) -> list[dict[str, Any]]:
    """
    Transform the LVM thin pools of a node.

    :param thin_pools: Response of the LVM thin pool endpoint
    :param node_name: Node name
    :param cluster_id: Parent cluster ID
    :return: List of transformed thin pool dicts
    """
    node_id = cluster_scoped_id(cluster_id, node_name)
    result = []
    for pool in thin_pools:
        lv = pool["lv"]
        vg = pool["vg"]
        result.append(
            {
                "id": cluster_scoped_id(cluster_id, f"{node_name}:lvmthin:{vg}/{lv}"),
                "cluster_id": cluster_id,
                "node_name": node_name,
                "node_id": node_id,
                "name": lv,
                "volume_group": vg,
                "volume_group_id": cluster_scoped_id(
                    cluster_id,
                    f"{node_name}:lvm:{vg}",
                ),
                "lv_size": pool.get("lv_size"),
                "used": pool.get("used"),
                "metadata_size": pool.get("metadata_size"),
                "metadata_used": pool.get("metadata_used"),
            },
        )
    return result


def transform_managed_directories(
    directories: list[dict[str, Any]],
    disks: list[dict[str, Any]],
    node_name: str,
    cluster_id: str,
) -> list[dict[str, Any]]:
    """
    Transform the managed directory storages of a node.

    :param directories: Response of the directory endpoint
    :param disks: Transformed disks of the same node
    :param node_name: Node name
    :param cluster_id: Parent cluster ID
    :return: List of transformed directory dicts
    """
    node_id = cluster_scoped_id(cluster_id, node_name)
    result = []
    for directory in directories:
        path = directory["path"]
        device = directory.get("device")
        result.append(
            {
                "id": cluster_scoped_id(cluster_id, f"{node_name}:directory:{path}"),
                "cluster_id": cluster_id,
                "node_name": node_name,
                "node_id": node_id,
                "path": path,
                "device": device,
                "type": directory.get("type"),
                "options": directory.get("options"),
                "unitfile": directory.get("unitfile"),
                "disk_ids": _match_disk_ids([device] if device else [], disks),
            },
        )
    return result


# ============================================================================
# TRANSFORM functions - software
# ============================================================================


def transform_packages(
    packages: list[dict[str, Any]],
    node_name: str,
    cluster_id: str,
) -> list[dict[str, Any]]:
    """
    Transform the key package versions of a node.

    :param packages: Response of the APT versions endpoint
    :param node_name: Node name
    :param cluster_id: Parent cluster ID
    :return: List of transformed package dicts
    """
    node_id = cluster_scoped_id(cluster_id, node_name)
    result = []
    for package in packages:
        name = package["Package"]
        result.append(
            {
                "id": cluster_scoped_id(cluster_id, f"{node_name}:package:{name}"),
                "cluster_id": cluster_id,
                "node_name": node_name,
                "node_id": node_id,
                "name": name,
                "version": package.get("Version"),
                "old_version": package.get("OldVersion"),
                "current_state": package.get("CurrentState"),
                "origin": package.get("Origin"),
                "arch": package.get("Arch"),
                "section": package.get("Section"),
                "priority": package.get("Priority"),
                "title": package.get("Title"),
                "running_kernel": package.get("RunningKernel"),
                "manager_version": package.get("ManagerVersion"),
            },
        )
    return result


def transform_apt_repositories(
    repo_info: dict[str, Any],
    node_name: str,
    cluster_id: str,
) -> list[dict[str, Any]]:
    """
    Transform the APT repositories configured on a node.

    Credentials embedded in the repository URIs are removed.

    :param repo_info: Response of the APT repositories endpoint
    :param node_name: Node name
    :param cluster_id: Parent cluster ID
    :return: List of transformed repository dicts
    """
    node_id = cluster_scoped_id(cluster_id, node_name)
    result = []
    for repo_file in (repo_info or {}).get("files") or []:
        path = repo_file["path"]
        for index, repo in enumerate(repo_file.get("repositories") or []):
            result.append(
                {
                    "id": cluster_scoped_id(
                        cluster_id,
                        f"{node_name}:apt:{path}:{index}",
                    ),
                    "cluster_id": cluster_id,
                    "node_name": node_name,
                    "node_id": node_id,
                    "path": path,
                    "index": index,
                    "file_type": repo.get("FileType", repo_file.get("file-type")),
                    "enabled": (
                        bool(repo["Enabled"])
                        if repo.get("Enabled") is not None
                        else None
                    ),
                    "types": repo.get("Types"),
                    "uris": (
                        [strip_uri_credentials(uri) for uri in repo["URIs"]]
                        if isinstance(repo.get("URIs"), list)
                        else strip_uri_credentials(repo.get("URIs"))
                    ),
                    "suites": repo.get("Suites"),
                    "components": repo.get("Components"),
                    "comment": _strip_text_credentials(repo.get("Comment")),
                },
            )
    return result


def transform_apt_repository_summary(repo_info: dict[str, Any]) -> dict[str, Any]:
    """
    Summarize which Proxmox standard repositories a node uses, and the parse errors.

    :param repo_info: Response of the APT repositories endpoint
    :return: Dict of node configuration properties
    """
    status_by_handle: dict[str, bool | None] = {}
    for repo in (repo_info or {}).get("standard-repos") or []:
        handle = repo.get("handle")
        if not handle:
            continue
        status = repo.get("status")
        status_by_handle[handle] = bool(status) if status is not None else None

    return {
        "enterprise_repo_enabled": status_by_handle.get(STANDARD_REPO_ENTERPRISE),
        "no_subscription_repo_enabled": status_by_handle.get(
            STANDARD_REPO_NO_SUBSCRIPTION,
        ),
        "test_repo_enabled": status_by_handle.get(STANDARD_REPO_TEST),
        "enabled_standard_repos": sorted(
            handle for handle, status in status_by_handle.items() if status
        ),
        "apt_repository_errors": [
            _strip_text_credentials(f"{error.get('path')}: {error.get('error')}")
            for error in (repo_info or {}).get("errors") or []
        ],
    }


def transform_subscription(
    subscription: dict[str, Any],
    node_name: str,
    cluster_id: str,
) -> dict[str, Any]:
    """
    Transform the subscription of a node.

    The key is reduced to its last four characters; the signature and server ID
    are dropped.

    :param subscription: Response of the subscription endpoint
    :param node_name: Node name
    :param cluster_id: Parent cluster ID
    :return: Transformed subscription dict
    """
    key = subscription.get("key")
    key_suffix = key[-4:] if isinstance(key, str) and len(key) > 4 else None
    return {
        "id": cluster_scoped_id(cluster_id, f"{node_name}:subscription"),
        "cluster_id": cluster_id,
        "node_name": node_name,
        "node_id": cluster_scoped_id(cluster_id, node_name),
        "status": subscription.get("status"),
        "level": subscription.get("level"),
        "productname": subscription.get("productname"),
        "regdate": subscription.get("regdate"),
        "nextduedate": subscription.get("nextduedate"),
        "checktime": subscription.get("checktime"),
        "sockets": subscription.get("sockets"),
        "message": subscription.get("message"),
        "key_suffix": key_suffix,
    }


# ============================================================================
# TRANSFORM functions - system
# ============================================================================


def _acme_domains(config: dict[str, Any]) -> list[str]:
    domains: list[str] = []
    acme = _parse_property_string(config.get("acme"), "domains")
    for domain in (acme.get("domains") or "").split(";"):
        domain = domain.strip()
        if domain and domain not in domains:
            domains.append(domain)
    for key in sorted(k for k in config if re.fullmatch(r"acmedomain\d+", k)):
        plugin_domain = _parse_property_string(config[key], "domain").get("domain")
        if plugin_domain and plugin_domain not in domains:
            domains.append(plugin_domain)
    return domains


def transform_node_config(
    config: dict[str, Any],
    dns: dict[str, Any],
    time_settings: dict[str, Any],
    repo_info: dict[str, Any],
    node_name: str,
    cluster_id: str,
) -> dict[str, Any]:
    """
    Combine the node options, DNS, time zone and APT repository usage of a node.

    :param config: Response of the node config endpoint
    :param dns: Response of the node DNS endpoint
    :param time_settings: Response of the node time endpoint
    :param repo_info: Response of the APT repositories endpoint
    :param node_name: Node name
    :param cluster_id: Parent cluster ID
    :return: Transformed node configuration dict
    """
    config = config or {}
    dns = dns or {}
    wakeonlan = _parse_property_string(config.get("wakeonlan"), "mac")
    acme = _parse_property_string(config.get("acme"), "domains")
    item = {
        "id": cluster_scoped_id(cluster_id, f"{node_name}:config"),
        "cluster_id": cluster_id,
        "node_name": node_name,
        "node_id": cluster_scoped_id(cluster_id, node_name),
        "description": config.get("description"),
        "location": config.get("location"),
        "wakeonlan_mac": wakeonlan.get("mac"),
        "wakeonlan_bind_interface": wakeonlan.get("bind-interface"),
        "wakeonlan_broadcast_address": wakeonlan.get("broadcast-address"),
        "ballooning_target": config.get("ballooning-target"),
        "startall_onboot_delay": config.get("startall-onboot-delay"),
        "acme_account": acme.get("account"),
        "acme_domains": _acme_domains(config),
        "dns_servers": [dns[key] for key in ("dns1", "dns2", "dns3") if dns.get(key)],
        "dns_search": dns.get("search"),
        "timezone": (time_settings or {}).get("timezone"),
    }
    item.update(transform_apt_repository_summary(repo_info))
    return item


def transform_services(
    services: list[dict[str, Any]],
    node_name: str,
    cluster_id: str,
) -> list[dict[str, Any]]:
    """
    Transform the system services of a node.

    :param services: Response of the services endpoint
    :param node_name: Node name
    :param cluster_id: Parent cluster ID
    :return: List of transformed service dicts
    """
    node_id = cluster_scoped_id(cluster_id, node_name)
    result = []
    for service in services:
        name = service.get("name") or service["service"]
        result.append(
            {
                "id": cluster_scoped_id(cluster_id, f"{node_name}:service:{name}"),
                "cluster_id": cluster_id,
                "node_name": node_name,
                "node_id": node_id,
                "name": name,
                "service": service.get("service"),
                "description": service.get("desc"),
                "state": service.get("state"),
                "active_state": service.get("active-state"),
                "unit_state": service.get("unit-state"),
            },
        )
    return result


def transform_pci_devices(
    devices: list[dict[str, Any]],
    mdev_types_by_id: dict[str, list[dict[str, Any]]],
    node_name: str,
    cluster_id: str,
) -> list[dict[str, Any]]:
    """
    Transform the PCI devices of a node, with the mdev types of capable devices.

    :param devices: Response of the PCI device endpoint
    :param mdev_types_by_id: mdev type responses keyed by PCI address
    :param node_name: Node name
    :param cluster_id: Parent cluster ID
    :return: List of transformed PCI device dicts
    """
    node_id = cluster_scoped_id(cluster_id, node_name)
    result = []
    for device in devices:
        pci_id = device["id"]
        mdev_types = mdev_types_by_id.get(pci_id)
        result.append(
            {
                "id": cluster_scoped_id(cluster_id, f"{node_name}:pci:{pci_id}"),
                "cluster_id": cluster_id,
                "node_name": node_name,
                "node_id": node_id,
                "pci_id": pci_id,
                "pci_class": device.get("class"),
                "vendor": device.get("vendor"),
                "vendor_name": device.get("vendor_name"),
                "device": device.get("device"),
                "device_name": device.get("device_name"),
                "subsystem_vendor": device.get("subsystem_vendor"),
                "subsystem_vendor_name": device.get("subsystem_vendor_name"),
                "subsystem_device": device.get("subsystem_device"),
                "subsystem_device_name": device.get("subsystem_device_name"),
                "iommu_group": device.get("iommugroup"),
                "mdev": bool(device.get("mdev")),
                "mdev_types": (
                    [t["type"] for t in mdev_types if t.get("type")]
                    if mdev_types is not None
                    else None
                ),
                "mdev_available": (
                    sum(_leading_int(t.get("available")) or 0 for t in mdev_types)
                    if mdev_types is not None
                    else None
                ),
            },
        )
    return result


# ============================================================================
# LOAD and CLEANUP
# ============================================================================


def load_node_details(
    neo4j_session: neo4j.Session,
    data_by_label: dict[str, list[dict[str, Any]]],
    cluster_id: str,
    update_tag: int,
) -> None:
    """
    Load every node detail type, in dependency order.

    :param neo4j_session: Neo4j session
    :param data_by_label: Transformed records keyed by node label
    :param cluster_id: Parent cluster ID
    :param update_tag: Sync timestamp
    """
    for schema in NODE_DETAIL_SCHEMAS:
        data = data_by_label.get(schema.label) or []
        if not data:
            continue
        load(
            neo4j_session,
            schema,
            data,
            lastupdated=update_tag,
            CLUSTER_ID=cluster_id,
        )


def cleanup(
    neo4j_session: neo4j.Session,
    common_job_parameters: dict[str, Any],
) -> None:
    """
    Remove node details that were not seen in this sync.

    :param neo4j_session: Neo4j session
    :param common_job_parameters: Common parameters including UPDATE_TAG and CLUSTER_ID
    """
    for schema in NODE_DETAIL_SCHEMAS:
        GraphJob.from_node_schema(schema, common_job_parameters).run(neo4j_session)


# ============================================================================
# SYNC
# ============================================================================


def _get_smart_or_empty(
    proxmox_client: Any,
    node_name: str,
    devpath: str,
) -> dict[str, Any]:
    """
    Get the SMART data of one disk, or an empty dict when it cannot be read.

    smartctl fails on devices it cannot open, such as RAID virtual disks, and
    Proxmox answers with an HTTP error. The disk is still synced, without SMART
    values.
    """
    try:
        return get_disk_smart(proxmox_client, node_name, devpath)
    except PROXMOX_API_ERRORS as e:
        logger.warning(
            "Could not read SMART data of disk %s on Proxmox node %s, "
            "syncing it without SMART values: %s",
            devpath,
            node_name,
            e,
        )
        return {}


def _get_mdev_types_or_none(
    proxmox_client: Any,
    node_name: str,
    pci_id: str,
) -> list[dict[str, Any]] | None:
    """
    Get the mdev types of one PCI device, or None when they cannot be read.

    The device is still synced, without mdev types.
    """
    try:
        return get_pci_mdev_types(proxmox_client, node_name, pci_id)
    except PROXMOX_API_ERRORS as e:
        logger.warning(
            "Could not read mediated device types of PCI device %s on Proxmox "
            "node %s, syncing it without them: %s",
            pci_id,
            node_name,
            e,
        )
        return None


def _collect_node(
    proxmox_client: Any,
    node_name: str,
    cluster_id: str,
) -> dict[str, list[dict[str, Any]]]:
    """
    Read and transform every detail of one node.

    :return: Transformed records keyed by node label
    """
    data_by_label: dict[str, list[dict[str, Any]]] = {
        schema.label: [] for schema in NODE_DETAIL_SCHEMAS
    }
    # Storage
    raw_disks = get_node_disks(proxmox_client, node_name)
    smart_by_devpath = {
        disk["devpath"]: _get_smart_or_empty(proxmox_client, node_name, disk["devpath"])
        for disk in raw_disks
    }
    disks = transform_disks(raw_disks, smart_by_devpath, node_name, cluster_id)
    data_by_label["ProxmoxPhysicalDisk"].extend(disks)

    pools = get_zfs_pools(proxmox_client, node_name)
    details_by_name = {
        pool["name"]: get_zfs_pool_details(proxmox_client, node_name, pool["name"])
        for pool in pools
    }
    data_by_label["ProxmoxZFSPool"].extend(
        transform_zfs_pools(pools, details_by_name, disks, node_name, cluster_id),
    )
    data_by_label["ProxmoxLVMVolumeGroup"].extend(
        transform_lvm_volume_groups(
            get_lvm_volume_groups(proxmox_client, node_name),
            disks,
            node_name,
            cluster_id,
        ),
    )
    data_by_label["ProxmoxLVMThinPool"].extend(
        transform_lvm_thin_pools(
            get_lvm_thin_pools(proxmox_client, node_name),
            node_name,
            cluster_id,
        ),
    )
    data_by_label["ProxmoxManagedDirectory"].extend(
        transform_managed_directories(
            get_managed_directories(proxmox_client, node_name),
            disks,
            node_name,
            cluster_id,
        ),
    )

    # Software
    data_by_label["ProxmoxPackage"].extend(
        transform_packages(
            get_package_versions(proxmox_client, node_name),
            node_name,
            cluster_id,
        ),
    )
    repo_info = get_apt_repositories(proxmox_client, node_name)
    data_by_label["ProxmoxAPTRepository"].extend(
        transform_apt_repositories(repo_info, node_name, cluster_id),
    )
    data_by_label["ProxmoxSubscription"].append(
        transform_subscription(
            get_subscription(proxmox_client, node_name),
            node_name,
            cluster_id,
        ),
    )

    # System
    data_by_label["ProxmoxNodeConfig"].append(
        transform_node_config(
            get_node_config(proxmox_client, node_name),
            get_node_dns(proxmox_client, node_name),
            get_node_time(proxmox_client, node_name),
            repo_info,
            node_name,
            cluster_id,
        ),
    )
    data_by_label["ProxmoxService"].extend(
        transform_services(
            get_node_services(proxmox_client, node_name),
            node_name,
            cluster_id,
        ),
    )
    pci_devices = get_pci_devices(proxmox_client, node_name)
    mdev_types_by_id: dict[str, list[dict[str, Any]]] = {}
    for device in pci_devices:
        if not device.get("mdev"):
            continue
        mdev_types = _get_mdev_types_or_none(proxmox_client, node_name, device["id"])
        if mdev_types is not None:
            mdev_types_by_id[device["id"]] = mdev_types
    data_by_label["ProxmoxPCIDevice"].extend(
        transform_pci_devices(pci_devices, mdev_types_by_id, node_name, cluster_id),
    )
    return data_by_label


@timeit
def sync(
    neo4j_session: neo4j.Session,
    proxmox_client: Any,
    cluster_id: str,
    update_tag: int,
    common_job_parameters: dict[str, Any],
) -> None:
    """
    Sync hardware, software and system details of every online node.

    Offline nodes are skipped, so their details are removed by the cleanup
    until they are back online.

    A node whose details cannot be read (for example a 595 when it is
    unreachable, or a 403 from a custom role) is logged and skipped, and the
    other nodes are still synced. The cleanup then does not run for this sync,
    so the failed node keeps the details of its last successful sync; stale
    details of the other nodes are removed by the next sync in which every
    online node succeeds. A SMART or mdev error on one device does not fail
    the node: the device is synced without those values.

    :param neo4j_session: Neo4j session
    :param proxmox_client: Proxmox API client
    :param cluster_id: Parent cluster ID
    :param update_tag: Sync timestamp
    :param common_job_parameters: Common parameters including UPDATE_TAG and CLUSTER_ID
    """
    logger.info("Syncing Proxmox node hardware, software and system details")

    nodes = cluster.get_nodes(proxmox_client)
    online_nodes = [n["node"] for n in nodes if n.get("status") == "online"]
    skipped = len(nodes) - len(online_nodes)
    if skipped:
        logger.info("Skipping details of %d Proxmox nodes that are not online", skipped)

    data_by_label: dict[str, list[dict[str, Any]]] = {
        schema.label: [] for schema in NODE_DETAIL_SCHEMAS
    }
    failed_nodes: list[str] = []
    for node_name in online_nodes:
        try:
            node_data = _collect_node(proxmox_client, node_name, cluster_id)
        except PROXMOX_API_ERRORS as e:
            # Nothing of a failed node is loaded, so its previous details stay
            # untouched instead of being partly overwritten.
            logger.warning(
                "Could not read details of Proxmox node %s, skipping it: %s",
                node_name,
                e,
            )
            failed_nodes.append(node_name)
            continue
        for label, records in node_data.items():
            data_by_label[label].extend(records)

    load_node_details(neo4j_session, data_by_label, cluster_id, update_tag)
    if failed_nodes:
        # The cleanup is scoped to the cluster, so it would also delete the
        # previous details of the failed nodes. Skip it for this sync.
        logger.warning(
            "Skipping cleanup of Proxmox node details because %d nodes failed: %s",
            len(failed_nodes),
            ", ".join(failed_nodes),
        )
    else:
        cleanup(neo4j_session, common_job_parameters)

    logger.info(
        "Synced details of %d Proxmox nodes: %s",
        len(online_nodes) - len(failed_nodes),
        ", ".join(f"{len(v)} {k}" for k, v in data_by_label.items()),
    )
