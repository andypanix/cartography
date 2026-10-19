"""
Sync Proxmox cluster resource mappings (PCI, USB, and directory mappings).

A resource mapping gives a cluster-wide name to a PCI device, a USB device, or
a host directory, with one entry per node that has it. VMs reference a mapping
by name in their configuration (hostpciN: mapping=<id>, usbN: mapping=<id>,
virtiofsN: <id>) instead of a node-local device or path.

Follows Cartography's Get → Transform → Load pattern.
"""

import logging
from typing import Any

import neo4j

from cartography.client.core.tx import load
from cartography.intel.proxmox.util import cluster_scoped_id
from cartography.intel.proxmox.util import proxmox_api_retry
from cartography.intel.proxmox.util import proxmox_optional_endpoint
from cartography.models.proxmox.mapping import ProxmoxResourceMappingSchema
from cartography.util import timeit

logger = logging.getLogger(__name__)

MAPPING_TYPES = ("pci", "usb", "dir")

# VM configuration keys that can reference a mapping, with the mapping type
# and the key of the property string that holds the mapping ID. virtiofsN
# names the directory mapping in its default key, dirid.
_GUEST_MAPPING_KEYS = (
    ("hostpci", "pci", "mapping"),
    ("usb", "usb", "mapping"),
    ("virtiofs", "dir", "dirid"),
)


# ============================================================================
# GET functions - retrieve data from Proxmox API
# ============================================================================


@timeit
@proxmox_api_retry
def get_pci_mappings(proxmox_client: Any) -> list[dict[str, Any]]:
    """
    Get the PCI resource mappings the caller can see.

    :param proxmox_client: Proxmox API client
    :return: List of PCI mapping dicts
    """
    return proxmox_client.cluster.mapping.pci.get()


@timeit
@proxmox_api_retry
def get_usb_mappings(proxmox_client: Any) -> list[dict[str, Any]]:
    """
    Get the USB resource mappings the caller can see.

    :param proxmox_client: Proxmox API client
    :return: List of USB mapping dicts
    """
    return proxmox_client.cluster.mapping.usb.get()


@timeit
@proxmox_optional_endpoint(list)
@proxmox_api_retry
def get_dir_mappings(proxmox_client: Any) -> list[dict[str, Any]]:
    """
    Get the directory resource mappings the caller can see.

    :param proxmox_client: Proxmox API client
    :return: List of directory mapping dicts
    """
    return proxmox_client.cluster.mapping.dir.get()


# ============================================================================
# TRANSFORM functions - manipulate data for graph ingestion
# ============================================================================


def parse_property_string(value: str, default_key: str) -> dict[str, str]:
    """
    Parse a Proxmox property string such as node=pve,path=0000:01:00.0.

    :param value: Comma-separated key=value pairs; a bare item is the default key
    :param default_key: Key of a value given without a key
    :return: Dict of the parsed keys and values
    """
    parsed: dict[str, str] = {}
    for item in str(value).split(","):
        item = item.strip()
        if not item:
            continue
        key, sep, val = item.partition("=")
        if sep:
            parsed[key.strip()] = val.strip()
        else:
            parsed.setdefault(default_key, item)
    return parsed


def extract_guest_mapping_refs(
    vm_config: dict[str, Any],
    guest_id: str,
) -> list[dict[str, str]]:
    """
    Find the resource mappings a QEMU VM configuration references.

    :param vm_config: Configuration of the VM, as returned by the API
    :param guest_id: Graph ID of the VM
    :return: One dict per reference, with guest_id, mapping_type and mapping_id
    """
    refs = []
    for key, value in vm_config.items():
        for prefix, mapping_type, id_key in _GUEST_MAPPING_KEYS:
            if not key.startswith(prefix) or not key[len(prefix) :].isdigit():
                continue
            # hostpciN and usbN put the host device in the default key and
            # the mapping in mapping=; virtiofsN puts the mapping first.
            default_key = "dirid" if mapping_type == "dir" else "host"
            mapping_id = parse_property_string(value, default_key).get(id_key)
            if mapping_id:
                refs.append(
                    {
                        "guest_id": guest_id,
                        "mapping_type": mapping_type,
                        "mapping_id": mapping_id,
                    },
                )
    return refs


def transform_mapping_data(
    mappings: list[dict[str, Any]],
    mapping_type: str,
    cluster_id: str,
    guest_mapping_refs: list[dict[str, str]],
) -> list[dict[str, Any]]:
    """
    Transform resource mappings of one type into standard format.

    :param mappings: Raw mapping data from the API
    :param mapping_type: pci, usb, or dir
    :param cluster_id: Parent cluster ID
    :param guest_mapping_refs: Mapping references found in VM configurations
    :return: List of transformed mapping dicts
    """
    guests_by_mapping: dict[str, set[str]] = {}
    for ref in guest_mapping_refs:
        if ref["mapping_type"] == mapping_type:
            guests_by_mapping.setdefault(ref["mapping_id"], set()).add(
                ref["guest_id"],
            )

    transformed = []
    for mapping in mappings:
        mapping_id = mapping["id"]
        entries = mapping.get("map") or []
        if isinstance(entries, str):
            entries = [entries]
        nodes = sorted(
            {
                node
                for node in (
                    parse_property_string(entry, "node").get("node")
                    for entry in entries
                )
                if node
            },
        )
        transformed.append(
            {
                "id": cluster_scoped_id(cluster_id, f"{mapping_type}/{mapping_id}"),
                "mapping_id": mapping_id,
                "type": mapping_type,
                "cluster_id": cluster_id,
                "description": mapping.get("description"),
                "map": list(entries),
                "nodes": nodes,
                "node_ids": [cluster_scoped_id(cluster_id, n) for n in nodes],
                "guest_ids": sorted(guests_by_mapping.get(mapping_id, ())),
            },
        )
    return transformed


# ============================================================================
# LOAD functions - ingest data to Neo4j using modern data model
# ============================================================================


def load_mappings(
    neo4j_session: neo4j.Session,
    mappings: list[dict[str, Any]],
    cluster_id: str,
    update_tag: int,
) -> None:
    """
    Load resource mappings into Neo4j.

    :param neo4j_session: Neo4j session
    :param mappings: List of transformed mapping dicts
    :param cluster_id: Parent cluster ID
    :param update_tag: Sync timestamp
    """
    load(
        neo4j_session,
        ProxmoxResourceMappingSchema(),
        mappings,
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
    guest_mapping_refs: list[dict[str, str]] | None = None,
) -> None:
    """
    Sync PCI, USB, and directory resource mappings.

    The list endpoints only return the mappings the caller has Mapping.Audit,
    Mapping.Use, or Mapping.Modify on, so a token without them gets no
    mappings rather than an error.

    :param neo4j_session: Neo4j session
    :param proxmox_client: Proxmox API client
    :param cluster_id: Parent cluster ID
    :param update_tag: Sync timestamp
    :param common_job_parameters: Common parameters
    :param guest_mapping_refs: Mapping references returned by compute.sync
    """
    logger.info("Syncing Proxmox resource mappings")
    refs = guest_mapping_refs or []

    raw_by_type = {
        "pci": get_pci_mappings(proxmox_client),
        "usb": get_usb_mappings(proxmox_client),
        "dir": get_dir_mappings(proxmox_client),
    }

    transformed: list[dict[str, Any]] = []
    for mapping_type in MAPPING_TYPES:
        transformed.extend(
            transform_mapping_data(
                raw_by_type[mapping_type],
                mapping_type,
                cluster_id,
                refs,
            ),
        )

    if transformed:
        load_mappings(neo4j_session, transformed, cluster_id, update_tag)

    logger.info("Synced %d Proxmox resource mappings", len(transformed))
