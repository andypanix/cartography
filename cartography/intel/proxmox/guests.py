"""
Sync per-guest details of Proxmox VMs and LXC containers.

compute.sync lists the guests and reads their configuration. This module adds
what other endpoints return about each guest: cluster-wide HA state and pool,
snapshots, cloud-init values, container IP addresses, and the extra QEMU guest
agent data (filesystems, logged-in users, time zone). It also syncs the
cluster's custom CPU models, which VMs reference from their CPU type.

The per-guest status endpoint (/nodes/{node}/{type}/{vmid}/status/current) is
not read: everything it returns that the graph needs is already available from
the per-node list (qmpstatus, running machine and QEMU version, lock, tags),
from /cluster/resources (HA state), or from the guest configuration (agent).
"""

import base64
import hashlib
import logging
import re
from dataclasses import dataclass
from dataclasses import field
from typing import Any
from urllib.parse import unquote

import neo4j
import requests
from proxmoxer.core import ResourceException

from cartography.client.core.tx import load
from cartography.intel.proxmox.util import cluster_scoped_id
from cartography.intel.proxmox.util import proxmox_api_retry
from cartography.intel.proxmox.util import proxmox_optional_endpoint
from cartography.models.proxmox.guests import ProxmoxCustomCPUModelSchema
from cartography.models.proxmox.guests import ProxmoxGuestFilesystemSchema
from cartography.models.proxmox.guests import ProxmoxSnapshotSchema
from cartography.util import timeit

logger = logging.getLogger(__name__)

# Name of the pseudo snapshot that stands for the current guest state.
CURRENT_SNAPSHOT_NAME = "current"
CUSTOM_CPU_PREFIX = "custom-"
_IPCONFIG_KEY = re.compile(r"^ipconfig\d+$")
_CLOUDINIT_DRIVE_KEY = re.compile(r"^(ide|sata|scsi)\d+$")


# ============================================================================
# GET functions
# ============================================================================


@timeit
@proxmox_api_retry
def get_guest_resources(proxmox_client: Any) -> list[dict[str, Any]]:
    """
    Get the cluster-wide resource entries of every VM and container.

    :param proxmox_client: Proxmox API client
    :return: List of resource dicts with node, vmid, hastate, pool and tags
    """
    return proxmox_client.cluster.resources.get(type="vm")


@timeit
@proxmox_optional_endpoint(list)
@proxmox_api_retry
def get_custom_cpu_models(proxmox_client: Any) -> list[dict[str, Any]]:
    """
    Get the custom CPU models defined in the cluster. Proxmox VE 9 only.

    :param proxmox_client: Proxmox API client
    :return: List of custom CPU model dicts, empty on Proxmox VE 8
    """
    return proxmox_client.cluster.qemu("custom-cpu-models").get()


@timeit
@proxmox_api_retry
def get_guest_snapshots(
    proxmox_client: Any, node_name: str, vmid: int, vm_type: str
) -> list[dict[str, Any]]:
    """
    Get the snapshots of a VM or container.

    :param proxmox_client: Proxmox API client
    :param node_name: Node name
    :param vmid: VM ID
    :param vm_type: 'qemu' or 'lxc'
    :return: List of snapshot dicts, including the 'current' pseudo snapshot
    """
    if vm_type == "qemu":
        return proxmox_client.nodes(node_name).qemu(vmid).snapshot.get()
    return proxmox_client.nodes(node_name).lxc(vmid).snapshot.get()


@timeit
@proxmox_api_retry
def get_vm_cloudinit(
    proxmox_client: Any, node_name: str, vmid: int
) -> list[dict[str, Any]]:
    """
    Get the cloud-init values of a VM.

    :param proxmox_client: Proxmox API client
    :param node_name: Node name
    :param vmid: VM ID
    :return: List of {key, value, pending, delete} dicts
    """
    return proxmox_client.nodes(node_name).qemu(vmid).cloudinit.get()


@timeit
@proxmox_api_retry
def get_container_interfaces(
    proxmox_client: Any, node_name: str, vmid: int
) -> list[dict[str, Any]]:
    """
    Get the network interfaces and IP addresses of a running container.

    :param proxmox_client: Proxmox API client
    :param node_name: Node name
    :param vmid: Container ID
    :return: List of interface dicts
    """
    return proxmox_client.nodes(node_name).lxc(vmid).interfaces.get()


@timeit
@proxmox_api_retry
def get_guest_agent_command(
    proxmox_client: Any, node_name: str, vmid: int, command: str
) -> Any:
    """
    Run a read-only QEMU guest agent command and return its result.

    :param proxmox_client: Proxmox API client
    :param node_name: Node name
    :param vmid: VM ID
    :param command: Agent command, such as get-fsinfo
    :return: The 'result' field of the response, or None when it is missing
    """
    response = proxmox_client.nodes(node_name).qemu(vmid).agent(command).get()
    if isinstance(response, dict):
        return response.get("result")
    return None


# ============================================================================
# TRANSFORM functions
# ============================================================================


def index_guest_resources(resources: list[dict[str, Any]]) -> dict[int, dict]:
    """
    Index cluster resource entries of guests by VM ID.

    :param resources: Entries returned by /cluster/resources?type=vm
    :return: Dict of VM ID to resource entry
    """
    indexed: dict[int, dict] = {}
    for resource in resources:
        if resource.get("type") not in ("qemu", "lxc"):
            continue
        try:
            indexed[int(resource["vmid"])] = resource
        except (KeyError, TypeError, ValueError):
            continue
    return indexed


def custom_cpu_model_name(cpu: Any) -> str | None:
    """
    Get the custom CPU model name a VM CPU setting refers to.

    :param cpu: Value of the 'cpu' VM config key, such as custom-avx,flags=+aes
    :return: Model name without the custom- prefix, or None for built-in types
    """
    if not isinstance(cpu, str) or not cpu:
        return None
    cputype = None
    for part in cpu.split(","):
        if "=" not in part:
            cputype = part
        elif part.startswith("cputype="):
            cputype = part.split("=", 1)[1]
    if cputype and cputype.startswith(CUSTOM_CPU_PREFIX):
        return cputype[len(CUSTOM_CPU_PREFIX) :] or None
    return None


def ssh_key_fingerprint(line: str) -> str | None:
    """
    Compute the OpenSSH SHA256 fingerprint of one public key line.

    :param line: authorized_keys line, such as 'ssh-ed25519 AAAA... comment'
    :return: Fingerprint in the form SHA256:<base64>, or None if no key is found
    """
    tokens = line.split()
    for previous, token in zip(tokens, tokens[1:]):
        try:
            blob = base64.b64decode(token, validate=True)
        except ValueError:
            continue
        key_type = previous.encode()
        if blob[4 : 4 + len(key_type)] == key_type:
            digest = hashlib.sha256(blob).digest()
            return "SHA256:" + base64.b64encode(digest).decode().rstrip("=")
    return None


def transform_cloudinit(entries: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Turn cloud-init values into VM properties.

    Only the current value of each key is used, never the pending one. The
    password is reduced to whether one is set, and public SSH keys to their
    count and fingerprints.

    :param entries: List of {key, value, pending, delete} dicts
    :return: Dict of cloudinit_* VM properties
    """
    values = {
        entry["key"]: entry["value"]
        for entry in entries
        if entry.get("key") and entry.get("value") not in (None, "")
    }
    ssh_lines = [
        line.strip()
        for line in unquote(str(values.get("sshkeys", ""))).splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    fingerprints = [
        fp for fp in (ssh_key_fingerprint(line) for line in ssh_lines) if fp
    ]
    ipconfig_keys = sorted(
        (key for key in values if _IPCONFIG_KEY.match(key)),
        key=lambda key: int(key[len("ipconfig") :]),
    )
    ipconfig = [f"{key}={values[key]}" for key in ipconfig_keys]
    upgrade = values.get("ciupgrade")
    return {
        "cloudinit_user": values.get("ciuser"),
        "cloudinit_type": values.get("citype"),
        "cloudinit_custom": values.get("cicustom"),
        "cloudinit_upgrade": None if upgrade is None else str(upgrade) == "1",
        "cloudinit_nameserver": values.get("nameserver"),
        "cloudinit_searchdomain": values.get("searchdomain"),
        "cloudinit_ipconfig": ipconfig or None,
        "cloudinit_password_set": "cipassword" in values,
        "cloudinit_ssh_key_count": len(ssh_lines),
        "cloudinit_ssh_key_fingerprints": fingerprints or None,
    }


def has_cloudinit_drive(vm_config: dict[str, Any]) -> bool:
    """
    Check if a VM configuration attaches a cloud-init drive.

    :param vm_config: VM configuration dict
    :return: True if an ide, sata or scsi slot holds a cloud-init volume
    """
    return any(
        _CLOUDINIT_DRIVE_KEY.match(key)
        and isinstance(value, str)
        and "cloudinit" in value.split(",")[0]
        for key, value in vm_config.items()
    )


def transform_snapshots(
    snapshots: list[dict[str, Any]],
    vm_path: str,
    cluster_id: str,
) -> list[dict[str, Any]]:
    """
    Transform the snapshots of one guest, parents first.

    The 'current' pseudo snapshot is dropped. Snapshots are ordered so every
    parent precedes its children, which lets one load link each snapshot to
    its parent.

    :param snapshots: Snapshot list from the API
    :param vm_path: Guest ID inside the cluster, such as node1/qemu/100
    :param cluster_id: Parent cluster ID
    :return: List of snapshot dicts
    """
    by_name = {
        s["name"]: s
        for s in snapshots
        if s.get("name") and s["name"] != CURRENT_SNAPSHOT_NAME
    }

    def snapshot_id(name: str) -> str:
        return cluster_scoped_id(cluster_id, f"{vm_path}/snapshot/{name}")

    ordered: list[dict[str, Any]] = []
    seen: set[str] = set()

    def visit(name: str, chain: set[str]) -> None:
        if name in seen or name in chain:
            return
        parent = by_name[name].get("parent")
        if isinstance(parent, str) and parent in by_name:
            visit(parent, chain | {name})
        seen.add(name)
        ordered.append(by_name[name])

    for name in sorted(by_name):
        visit(name, set())

    vmid = int(vm_path.split("/")[-1])
    result = []
    for snap in ordered:
        parent = snap.get("parent") or None
        vmstate = snap.get("vmstate")
        result.append(
            {
                "id": snapshot_id(snap["name"]),
                "name": snap["name"],
                "cluster_id": cluster_id,
                "vmid": vmid,
                "vm_id": cluster_scoped_id(cluster_id, vm_path),
                "description": snap.get("description"),
                "snaptime": snap.get("snaptime"),
                "vmstate": None if vmstate is None else bool(vmstate),
                "parent": parent,
                "parent_id": (
                    snapshot_id(parent)
                    if isinstance(parent, str) and parent in by_name
                    else None
                ),
            }
        )
    return result


# Container interfaces name the address family like ip(8); the guest agent
# names it ipv4 or ipv6.
_CONTAINER_ADDRESS_TYPES = {"inet": "ipv4", "inet6": "ipv6"}


def _normalize_container_address(address: dict[str, Any]) -> dict[str, Any]:
    """
    Convert one container interface address to the guest agent address format.

    :param address: Entry of ip-addresses from /nodes/{node}/lxc/{vmid}/interfaces
    :return: Address with ip-address, an integer prefix and ip-address-type ipv4 or ipv6
    """
    ip_type = str(address.get("ip-address-type") or "").lower()
    prefix = address.get("prefix")
    if isinstance(prefix, str) and prefix.isdigit():
        prefix = int(prefix)
    return {
        "ip-address": address.get("ip-address"),
        "prefix": prefix,
        "ip-address-type": _CONTAINER_ADDRESS_TYPES.get(ip_type, ip_type),
    }


def normalize_container_interfaces(
    interfaces: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Convert container interfaces to the guest agent interface format.

    Proxmox VE 9 returns hardware-address and ip-addresses like the guest
    agent, but with the address type as inet or inet6 and the prefix as a
    string; both are converted to the guest agent form (ipv4 or ipv6, integer
    prefix). Older versions return only hwaddr, inet and inet6, which are
    mapped to the same fields.

    :param interfaces: Interface list from /nodes/{node}/lxc/{vmid}/interfaces
    :return: Interfaces with hardware-address, name and ip-addresses
    """
    normalized = []
    for iface in interfaces:
        addresses = [
            _normalize_container_address(address)
            for address in iface.get("ip-addresses") or []
        ]
        if not addresses:
            addresses = []
            for key, ip_type in (("inet", "ipv4"), ("inet6", "ipv6")):
                for cidr in str(iface.get(key) or "").split():
                    address, _, prefix = cidr.partition("/")
                    if address and prefix.isdigit():
                        addresses.append(
                            {
                                "ip-address": address,
                                "prefix": int(prefix),
                                "ip-address-type": ip_type,
                            }
                        )
        normalized.append(
            {
                "name": iface.get("name"),
                "hardware-address": iface.get("hardware-address")
                or iface.get("hwaddr")
                or "",
                "ip-addresses": addresses,
            }
        )
    return normalized


def transform_filesystems(
    filesystems: list[dict[str, Any]],
    vm_path: str,
    cluster_id: str,
) -> list[dict[str, Any]]:
    """
    Transform the guest agent get-fsinfo result of one VM.

    :param filesystems: List of GuestFilesystemInfo dicts
    :param vm_path: VM ID inside the cluster, such as node1/qemu/100
    :param cluster_id: Parent cluster ID
    :return: One dict per mount point
    """
    vmid = int(vm_path.split("/")[-1])
    result: dict[str, dict[str, Any]] = {}
    for fs in filesystems:
        mountpoint = fs.get("mountpoint")
        if not mountpoint or mountpoint in result:
            continue
        serials = sorted(
            {d["serial"] for d in fs.get("disk") or [] if d.get("serial")},
        )
        result[mountpoint] = {
            "id": cluster_scoped_id(cluster_id, f"{vm_path}:fs:{mountpoint}"),
            "mountpoint": mountpoint,
            "cluster_id": cluster_id,
            "vmid": vmid,
            "vm_id": cluster_scoped_id(cluster_id, vm_path),
            "name": fs.get("name"),
            "type": fs.get("type"),
            "total_bytes": fs.get("total-bytes"),
            "used_bytes": fs.get("used-bytes"),
            "disk_serials": serials or None,
        }
    return list(result.values())


def transform_guest_users(users: list[dict[str, Any]]) -> list[str] | None:
    """
    Turn the guest agent get-users result into a sorted list of user names.

    :param users: List of GuestUser dicts
    :return: Unique domain\\user or user names, or None when nobody is logged in
    """
    names = {
        f"{u['domain']}\\{u['user']}" if u.get("domain") else u["user"]
        for u in users
        if u.get("user")
    }
    return sorted(names) or None


def transform_custom_cpu_models(
    models: list[dict[str, Any]], cluster_id: str
) -> list[dict[str, Any]]:
    """
    Transform custom CPU models.

    :param models: Model list from /cluster/qemu/custom-cpu-models
    :param cluster_id: Parent cluster ID
    :return: List of model dicts
    """
    result = []
    for model in models:
        name = str(model.get("cputype") or "")
        if name.startswith(CUSTOM_CPU_PREFIX):
            name = name[len(CUSTOM_CPU_PREFIX) :]
        if not name:
            continue
        hidden = model.get("hidden")
        result.append(
            {
                "id": cluster_scoped_id(cluster_id, name),
                "name": name,
                "cluster_id": cluster_id,
                "reported_model": model.get("reported-model"),
                "flags": model.get("flags"),
                "hidden": None if hidden is None else bool(hidden),
                "phys_bits": model.get("phys-bits"),
                "guest_phys_bits": model.get("guest-phys-bits"),
                "hv_vendor_id": model.get("hv-vendor-id"),
                "level": model.get("level"),
            }
        )
    return result


GUEST_DETAIL_PROPERTIES = (
    "hastate",
    "pool",
    "qmpstatus",
    "running_machine",
    "running_qemu",
    "custom_cpu_model",
    "custom_cpu_model_id",
    "cloudinit_user",
    "cloudinit_type",
    "cloudinit_custom",
    "cloudinit_upgrade",
    "cloudinit_nameserver",
    "cloudinit_searchdomain",
    "cloudinit_ipconfig",
    "cloudinit_password_set",
    "cloudinit_ssh_key_count",
    "cloudinit_ssh_key_fingerprints",
    "guest_timezone",
    "guest_timezone_offset",
    "guest_users",
)


def guest_detail_properties(vm: dict[str, Any]) -> dict[str, Any]:
    """
    Select the VM properties this module adds, for transform_vm_data.

    :param vm: Guest dict enriched by collect_guest_details
    :return: Dict of every guest detail property, None when unknown
    """
    return {key: vm.get(key) for key in GUEST_DETAIL_PROPERTIES}


# ============================================================================
# Per-guest collection, called by compute.sync
# ============================================================================


@dataclass
class GuestDetails:
    """Records of one guest collected by collect_guest_details."""

    snapshots: list[dict[str, Any]] = field(default_factory=list)
    filesystems: list[dict[str, Any]] = field(default_factory=list)
    # Container interfaces in the guest agent format, for
    # compute.enrich_interfaces_with_guest_data.
    container_interfaces: list[dict[str, Any]] = field(default_factory=list)


def _agent_command(proxmox_client: Any, node_name: str, vmid: int, command: str) -> Any:
    # The guest agent may not support a command (old agent versions, commands
    # blocked in the agent configuration) or stop answering mid-sync. That is
    # expected for some VMs, so skip that piece of data instead of failing.
    try:
        return get_guest_agent_command(proxmox_client, node_name, vmid, command)
    except (ResourceException, requests.exceptions.RequestException) as e:
        logger.debug(
            "QEMU guest agent command %s failed for VM %s on node %s: %s",
            command,
            vmid,
            node_name,
            e,
        )
        return None


def collect_guest_details(
    proxmox_client: Any,
    vm: dict[str, Any],
    vm_config: dict[str, Any],
    cluster_id: str,
    guest_resources: dict[int, dict[str, Any]],
    enable_guest_agent: bool,
) -> GuestDetails:
    """
    Read the per-guest details of one VM or container.

    Sets the guest detail properties on vm and returns the guest's snapshots,
    filesystems, and container interfaces with their IP addresses.

    :param proxmox_client: Proxmox API client
    :param vm: Guest dict from the per-node list, modified in place
    :param vm_config: Guest configuration
    :param cluster_id: Parent cluster ID
    :param guest_resources: Cluster resource entries indexed by VM ID
    :param enable_guest_agent: Whether guest agent data collection is enabled
    :return: Snapshots, filesystems and container interfaces of the guest
    """
    node_name = vm["node"]
    vmid = vm["vmid"]
    vm_type = vm["type"]
    vm_path = f"{node_name}/{vm_type}/{vmid}"
    running = vm.get("status") == "running"

    for key in GUEST_DETAIL_PROPERTIES:
        vm.setdefault(key, None)

    resource = guest_resources.get(int(vmid), {})
    vm["hastate"] = resource.get("hastate")
    vm["pool"] = resource.get("pool")
    vm["running_machine"] = vm.get("running-machine")
    vm["running_qemu"] = vm.get("running-qemu")

    model = custom_cpu_model_name(vm_config.get("cpu"))
    vm["custom_cpu_model"] = model
    vm["custom_cpu_model_id"] = cluster_scoped_id(cluster_id, model) if model else None

    details = GuestDetails(
        snapshots=transform_snapshots(
            get_guest_snapshots(proxmox_client, node_name, vmid, vm_type),
            vm_path,
            cluster_id,
        ),
    )

    if vm_type == "qemu" and has_cloudinit_drive(vm_config):
        vm.update(
            transform_cloudinit(get_vm_cloudinit(proxmox_client, node_name, vmid))
        )

    if vm_type == "lxc" and running:
        details.container_interfaces = normalize_container_interfaces(
            get_container_interfaces(proxmox_client, node_name, vmid),
        )

    # Only query the extra agent commands when the agent already answered the
    # basic ones in compute.get_guest_agent_info.
    if enable_guest_agent and vm_type == "qemu" and vm.get("agent_enabled"):
        filesystems = _agent_command(proxmox_client, node_name, vmid, "get-fsinfo")
        if isinstance(filesystems, list):
            details.filesystems = transform_filesystems(
                filesystems, vm_path, cluster_id
            )
        users = _agent_command(proxmox_client, node_name, vmid, "get-users")
        if isinstance(users, list):
            vm["guest_users"] = transform_guest_users(users)
        timezone = _agent_command(proxmox_client, node_name, vmid, "get-timezone")
        if isinstance(timezone, dict):
            vm["guest_timezone"] = timezone.get("zone")
            vm["guest_timezone_offset"] = timezone.get("offset")

    return details


# ============================================================================
# LOAD functions
# ============================================================================


def load_snapshots(
    neo4j_session: neo4j.Session,
    snapshots: list[dict[str, Any]],
    cluster_id: str,
    update_tag: int,
) -> None:
    """
    Load guest snapshots.

    :param neo4j_session: Neo4j session
    :param snapshots: Snapshot dicts, every parent before its children
    :param cluster_id: Parent cluster ID
    :param update_tag: Sync timestamp
    """
    load(
        neo4j_session,
        ProxmoxSnapshotSchema(),
        snapshots,
        lastupdated=update_tag,
        CLUSTER_ID=cluster_id,
    )


def load_filesystems(
    neo4j_session: neo4j.Session,
    filesystems: list[dict[str, Any]],
    cluster_id: str,
    update_tag: int,
) -> None:
    """
    Load filesystems reported by the QEMU guest agent.

    :param neo4j_session: Neo4j session
    :param filesystems: Filesystem dicts
    :param cluster_id: Parent cluster ID
    :param update_tag: Sync timestamp
    """
    load(
        neo4j_session,
        ProxmoxGuestFilesystemSchema(),
        filesystems,
        lastupdated=update_tag,
        CLUSTER_ID=cluster_id,
    )


# ============================================================================
# SYNC functions
# ============================================================================


@timeit
def sync_custom_cpu_models(
    neo4j_session: neo4j.Session,
    proxmox_client: Any,
    cluster_id: str,
    update_tag: int,
) -> None:
    """
    Sync custom CPU models. Run it before compute.sync so VMs can link to them.

    :param neo4j_session: Neo4j session
    :param proxmox_client: Proxmox API client
    :param cluster_id: Parent cluster ID
    :param update_tag: Sync timestamp
    """
    models = transform_custom_cpu_models(
        get_custom_cpu_models(proxmox_client), cluster_id
    )
    load(
        neo4j_session,
        ProxmoxCustomCPUModelSchema(),
        models,
        lastupdated=update_tag,
        CLUSTER_ID=cluster_id,
    )
    logger.info("Synced %d Proxmox custom CPU models", len(models))
