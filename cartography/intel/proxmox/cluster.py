"""
Sync Proxmox clusters and nodes.

Follows Cartography's Get → Transform → Load pattern.
"""

import logging
from typing import Any
from typing import Dict
from typing import List

import neo4j

from cartography.client.core.tx import load
from cartography.graph.job import GraphJob
from cartography.intel.proxmox.util import cluster_scoped_id
from cartography.intel.proxmox.util import proxmox_api_retry
from cartography.models.proxmox.cluster import ProxmoxClusterSchema
from cartography.models.proxmox.cluster import ProxmoxNodeNetworkInterfaceSchema
from cartography.models.proxmox.cluster import ProxmoxNodeSchema
from cartography.util import timeit

logger = logging.getLogger(__name__)


# ============================================================================
# GET functions - retrieve data from Proxmox API
# Per docs: "should be 'dumb'... raise an exception if not able to complete"
# ============================================================================


@timeit
@proxmox_api_retry
def get_cluster_status(proxmox_client: Any) -> List[Dict[str, Any]]:
    """
    Get cluster status information.

    :param proxmox_client: Proxmox API client
    :return: Cluster status list
    :raises: Exception if API call fails
    """
    return proxmox_client.cluster.status.get()


@timeit
@proxmox_api_retry
def get_nodes(proxmox_client: Any) -> List[Dict[str, Any]]:
    """
    Get all nodes in the cluster.

    :param proxmox_client: Proxmox API client
    :return: List of node dicts
    :raises: Exception if API call fails
    """
    return proxmox_client.nodes.get()


@timeit
@proxmox_api_retry
def get_node_status(proxmox_client: Any, node_name: str) -> Dict[str, Any]:
    """
    Get detailed status for a specific node.

    :param proxmox_client: Proxmox API client
    :param node_name: Name of the node
    :return: Node status dict
    :raises: Exception if API call fails
    """
    return proxmox_client.nodes(node_name).status.get()


@timeit
@proxmox_api_retry
def get_node_network(proxmox_client: Any, node_name: str) -> List[Dict[str, Any]]:
    """
    Get network interface configuration for a specific node.

    :param proxmox_client: Proxmox API client
    :param node_name: Name of the node
    :return: List of network interface dicts
    :raises: Exception if API call fails
    """
    return proxmox_client.nodes(node_name).network.get()


@timeit
@proxmox_api_retry
def get_cluster_options(proxmox_client: Any) -> Dict[str, Any]:
    """
    Get cluster-wide configuration options.

    :param proxmox_client: Proxmox API client
    :return: Cluster options dict
    :raises: Exception if API call fails
    """
    return proxmox_client.cluster.options.get()


@timeit
@proxmox_api_retry
def get_corosync_totem(proxmox_client: Any) -> Dict[str, Any] | None:
    """
    Get the corosync totem protocol settings.

    A host that is not part of a cluster has no corosync.conf and answers
    with null instead of an error.

    :param proxmox_client: Proxmox API client
    :return: Totem section of corosync.conf, or None on a standalone host
    :raises: Exception if API call fails
    """
    return proxmox_client.cluster.config.totem.get()


@timeit
@proxmox_api_retry
def get_corosync_nodes(proxmox_client: Any) -> List[Dict[str, Any]]:
    """
    Get the corosync node list.

    :param proxmox_client: Proxmox API client
    :return: Node entries of corosync.conf, empty on a standalone host
    :raises: Exception if API call fails
    """
    return proxmox_client.cluster.config.nodes.get()


@timeit
@proxmox_api_retry
def get_qdevice_status(proxmox_client: Any) -> Dict[str, Any]:
    """
    Get the status of the corosync QDevice.

    :param proxmox_client: Proxmox API client
    :return: QDevice status fields, empty when no QDevice is configured
    :raises: Exception if API call fails
    """
    return proxmox_client.cluster.config.qdevice.get()


# ============================================================================
# TRANSFORM functions - manipulate data for graph ingestion
# Per docs: Use data['field'] for required, data.get('field') for optional
# ============================================================================


def transform_cluster_data(
    cluster_status: List[Dict[str, Any]],
    proxmox_host: str,
) -> Dict[str, Any]:
    """
    Transform cluster status data into standard format.

    Per Cartography guidelines:
    - Use data['field'] for required fields (will raise KeyError if missing)
    - Use data.get('field') for optional fields

    :param cluster_status: Raw cluster status from API
    :param proxmox_host: Proxmox hostname for synthetic ID
    :return: Transformed cluster data
    """
    cluster_info = None
    for item in cluster_status:
        # Required field - use direct access
        if item["type"] == "cluster":
            cluster_info = item
            break

    if not cluster_info:
        # Create synthetic cluster ID from hostname
        cluster_id = proxmox_host.replace(".", "-")
        nodes_total = len([i for i in cluster_status if i["type"] == "node"])
        nodes_online = len(
            [i for i in cluster_status if i["type"] == "node" and i.get("online")]
        )
        return {
            "id": cluster_id,
            "name": cluster_id,
            "version": "unknown",
            "quorate": True,
            "nodes_online": nodes_online,
            "nodes_total": nodes_total,
            "cluster_id": None,
        }

    # Per docs: "ID should uniquely identify the node... use API-provided fields for IDs"
    nodes_total = cluster_info.get(
        "nodes", len([i for i in cluster_status if i["type"] == "node"])
    )
    nodes_online = len(
        [i for i in cluster_status if i["type"] == "node" and i.get("online")]
    )

    return {
        "id": cluster_info["name"],  # Required field - direct access
        "name": cluster_info["name"],  # Required
        "version": cluster_info.get("version", "unknown"),  # Optional with default
        "quorate": bool(
            cluster_info.get("quorate", True)
        ),  # Optional with default, convert to bool
        "nodes_online": nodes_online,
        "nodes_total": nodes_total,
        "cluster_id": cluster_info.get("id"),  # Internal cluster ID from API
    }


def _option_map(value: Any, default_key: str | None = None) -> Dict[str, Any]:
    """
    Read a datacenter option that holds a property string.

    The API returns these options already parsed into an object, such as
    {"type": "secure", "network": "10.0.0.0/24"} for migration. A plain
    string, such as "type=secure,network=10.0.0.0/24" or just "secure" for
    the default key, is parsed the same way.

    :param value: Option value from /cluster/options
    :param default_key: Key a bare value without "=" belongs to
    :return: Map of option keys to values, empty when the option is not set
    """
    if isinstance(value, dict):
        return value
    if not isinstance(value, str) or not value:
        return {}
    result: Dict[str, Any] = {}
    for part in value.split(","):
        key, sep, item = part.partition("=")
        if sep:
            result[key.strip()] = item.strip()
        elif default_key:
            result[default_key] = key.strip()
    return result


def _option_int(value: Any) -> int | None:
    """
    Convert a numeric datacenter option value, which can arrive as a string, to int.
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        try:
            return int(float(value))
        except ValueError:
            return None
    return None


def transform_cluster_options(cluster_options: Dict[str, Any]) -> Dict[str, Any]:
    """
    Transform cluster options into additional metadata fields.

    migration, bwlimit and next-id are property strings that the API returns
    as objects; only their documented keys become scalar properties.

    :param cluster_options: Raw cluster options from API
    :return: Dict of transformed cluster option fields
    """
    if not cluster_options:
        return {}

    migration = _option_map(cluster_options.get("migration"), default_key="type")
    bwlimit = _option_map(cluster_options.get("bwlimit"))
    next_id = _option_map(cluster_options.get("next-id"))

    return {
        # Migration settings
        "migration_type": migration.get("type"),
        "migration_network": migration.get("network"),
        # Bandwidth limit for migrations in KiB/s
        "migration_bandwidth_limit": _option_int(bwlimit.get("migration")),
        # Console settings
        "console": cluster_options.get("console"),
        # Email/notification settings
        "email_from": cluster_options.get("email_from"),
        "http_proxy": cluster_options.get("http_proxy"),
        # Keyboard layout
        "keyboard": cluster_options.get("keyboard"),
        # Language
        "language": cluster_options.get("language"),
        # MAC address prefix
        "mac_prefix": cluster_options.get("mac_prefix"),
        # Maximum workers
        "max_workers": cluster_options.get("max_workers"),
        # Next VMID settings
        "next_id_lower": _option_int(next_id.get("lower")),
        "next_id_upper": _option_int(next_id.get("upper")),
    }


def _to_int(value: Any) -> Any:
    """
    Convert a numeric corosync.conf value to int.

    corosync.conf values reach the API as strings; values that are not
    plain integers are returned unchanged.
    """
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return value


def transform_corosync_totem(totem: Dict[str, Any] | None) -> Dict[str, Any]:
    """
    Transform the corosync totem settings into cluster properties.

    :param totem: Totem section from /cluster/config/totem, None when not clustered
    :return: Dict of totem_* cluster fields, empty when there is no totem section
    """
    if not totem:
        return {}

    # Proxmox keys the interface sections by link number (ring number on
    # configurations written before corosync 3).
    interfaces = totem.get("interface") or {}
    link_numbers = sorted(_to_int(k) for k in interfaces) if interfaces else None

    return {
        "totem_cluster_name": totem.get("cluster_name"),
        "totem_config_version": _to_int(totem.get("config_version")),
        "totem_ip_version": totem.get("ip_version"),
        "totem_link_mode": totem.get("link_mode"),
        "totem_link_numbers": link_numbers,
        "totem_secauth": totem.get("secauth"),
        "totem_version": _to_int(totem.get("version")),
    }


def transform_qdevice_status(qdevice: Dict[str, Any] | None) -> Dict[str, Any]:
    """
    Transform the QDevice status into cluster properties.

    :param qdevice: Status from /cluster/config/qdevice, empty when no QDevice runs
    :return: Dict of qdevice_* cluster fields, empty when there is no QDevice
    """
    if not qdevice:
        return {}

    return {
        "qdevice_state": qdevice.get("State"),
        "qdevice_model": qdevice.get("Model"),
        "qdevice_qnetd_host": qdevice.get("QNetd host"),
        "qdevice_algorithm": qdevice.get("Algorithm"),
        "qdevice_tie_breaker": qdevice.get("Tie-breaker"),
    }


def transform_corosync_nodes(
    corosync_nodes: List[Dict[str, Any]],
) -> Dict[str, Dict[str, Any]]:
    """
    Transform the corosync node list into node fields keyed by node name.

    :param corosync_nodes: Entries from /cluster/config/nodes
    :return: Map of node name to corosync_* node fields
    """
    result: Dict[str, Dict[str, Any]] = {}
    for entry in corosync_nodes:
        # The API sets "node" to the name, or to ring0_addr when the entry has no name.
        node_name = entry["node"]
        rings = sorted(
            (int(key[len("ring") : -len("_addr")]), value)
            for key, value in entry.items()
            if key.startswith("ring")
            and key.endswith("_addr")
            and key[len("ring") : -len("_addr")].isdigit()
        )
        result[node_name] = {
            "corosync_node_id": _to_int(entry.get("nodeid")),
            "corosync_quorum_votes": _to_int(entry.get("quorum_votes")),
            "corosync_ring_addresses": [addr for _, addr in rings] or None,
        }
    return result


def transform_node_data(
    nodes: List[Dict[str, Any]],
    cluster_id: str,
    corosync_nodes: Dict[str, Dict[str, Any]] | None = None,
) -> List[Dict[str, Any]]:
    """
    Transform node data into standard format.

    :param nodes: Raw node data from API
    :param cluster_id: Parent cluster ID
    :param corosync_nodes: corosync_* fields keyed by node name, from transform_corosync_nodes
    :return: List of transformed node dicts
    """
    transformed_nodes = []
    corosync_nodes = corosync_nodes or {}

    for node in nodes:
        corosync = corosync_nodes.get(node["node"], {})
        # Use direct access for required fields, .get() for optional
        transformed_nodes.append(
            {
                "id": cluster_scoped_id(cluster_id, node["node"]),
                "name": node["node"],  # Required
                "cluster_id": cluster_id,  # Required
                "hostname": node["node"],  # Use node name as hostname
                "ip": node.get("ip"),  # Optional
                "status": node.get("status", "unknown"),  # Optional with default
                "uptime": node.get("uptime", 0),  # Optional with default
                "cpu_count": node.get("maxcpu", 0),  # Optional
                "cpu_usage": node.get("cpu", 0.0),  # Optional
                "memory_total": node.get("maxmem", 0),  # Optional
                "memory_used": node.get("mem", 0),  # Optional
                "disk_total": node.get("maxdisk", 0),  # Optional
                "disk_used": node.get("disk", 0),  # Optional
                "level": node.get("level"),  # Optional
                # Additional system info
                "kversion": node.get("kversion"),  # Kernel version
                # Convert loadavg array to comma-separated string
                "loadavg": (
                    ",".join(str(x) for x in node.get("loadavg", []))
                    if node.get("loadavg")
                    else None
                ),
                "wait": node.get("wait"),  # I/O wait time
                # Swap information
                "swap_total": node.get("maxswap"),  # Total swap
                "swap_used": node.get("swap"),  # Used swap
                "swap_free": (
                    node.get("maxswap", 0) - node.get("swap", 0)
                    if node.get("maxswap") and node.get("swap")
                    else None
                ),
                # Additional system info
                "pveversion": node.get("pveversion"),  # PVE version string
                "cpuinfo": node.get("cpuinfo"),  # CPU model
                "idle": node.get("idle"),  # Idle percentage
                # Corosync membership, empty on a standalone host
                "corosync_node_id": corosync.get("corosync_node_id"),
                "corosync_quorum_votes": corosync.get("corosync_quorum_votes"),
                "corosync_ring_addresses": corosync.get("corosync_ring_addresses"),
            }
        )

    return transformed_nodes


def transform_node_network_data(
    network_interfaces: List[Dict[str, Any]],
    node_name: str,
    cluster_id: str,
) -> List[Dict[str, Any]]:
    """
    Transform node network interface data into standard format.

    :param network_interfaces: Raw network interface data from API
    :param node_name: Node name
    :param cluster_id: Parent cluster ID
    :return: List of transformed network interface dicts
    """
    transformed_interfaces = []

    for iface in network_interfaces:
        # Required field
        iface_name = iface["iface"]
        iface_id = cluster_scoped_id(cluster_id, f"{node_name}:{iface_name}")

        transformed_interfaces.append(
            {
                "id": iface_id,
                "name": iface_name,
                "cluster_id": cluster_id,
                "node_name": node_name,
                "node_id": cluster_scoped_id(cluster_id, node_name),
                "type": iface.get("type"),  # bridge, bond, eth, vlan, etc.
                "address": iface.get("address"),
                "netmask": iface.get("netmask"),
                "gateway": iface.get("gateway"),
                "address6": iface.get("address6"),
                "netmask6": iface.get("netmask6"),
                "gateway6": iface.get("gateway6"),
                "bridge_ports": iface.get("bridge_ports"),
                "bond_slaves": iface.get("slaves"),  # API uses 'slaves' key
                "active": iface.get("active", False),
                "autostart": iface.get("autostart", False),
                "mtu": iface.get("mtu"),
                # Additional bond configuration
                "bond_mode": iface.get("bond_mode"),
                "bond_xmit_hash_policy": iface.get("bond_xmit_hash_policy"),
                # Additional network configuration
                "cidr": iface.get("cidr"),
                "cidr6": iface.get("cidr6"),
                "method": iface.get("method"),
                "method6": iface.get("method6"),
                "comments": iface.get("comments"),
            }
        )

    return transformed_interfaces


# ============================================================================
# LOAD functions - ingest data to Neo4j using modern data model
# Per AGENTS.md: Use load() function with data model schemas
# ============================================================================


def load_cluster(
    neo4j_session: neo4j.Session, cluster_data: Dict[str, Any], update_tag: int
) -> None:
    """
    Load cluster data into Neo4j using modern data model.

    :param neo4j_session: Neo4j session
    :param cluster_data: Transformed cluster data
    :param update_tag: Sync timestamp
    """
    load(
        neo4j_session,
        ProxmoxClusterSchema(),
        [cluster_data],
        lastupdated=update_tag,
    )


def load_nodes(
    neo4j_session: neo4j.Session,
    nodes: List[Dict[str, Any]],
    cluster_id: str,
    update_tag: int,
) -> None:
    """
    Load node data into Neo4j using modern data model.

    :param neo4j_session: Neo4j session
    :param nodes: List of transformed node dicts
    :param cluster_id: Parent cluster ID
    :param update_tag: Sync timestamp
    """
    load(
        neo4j_session,
        ProxmoxNodeSchema(),
        nodes,
        lastupdated=update_tag,
        CLUSTER_ID=cluster_id,
    )


def load_node_networks(
    neo4j_session: neo4j.Session,
    network_interfaces: List[Dict[str, Any]],
    cluster_id: str,
    update_tag: int,
) -> None:
    """
    Load node network interface data into Neo4j using modern data model.

    :param neo4j_session: Neo4j session
    :param network_interfaces: List of transformed network interface dicts
    :param cluster_id: Parent cluster ID
    :param update_tag: Sync timestamp
    """
    if not network_interfaces:
        return

    load(
        neo4j_session,
        ProxmoxNodeNetworkInterfaceSchema(),
        network_interfaces,
        lastupdated=update_tag,
        CLUSTER_ID=cluster_id,
    )


# ============================================================================
# SYNC function - orchestrates Get → Transform → Load
# Per docs: "sync should call get, then load, and finally cleanup"
# ============================================================================


@timeit
def sync(
    neo4j_session: neo4j.Session,
    proxmox_client: Any,
    proxmox_host: str,
    update_tag: int,
    common_job_parameters: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Sync cluster and node data.

    Follows Cartography's Get → Transform → Load pattern.
    Cleanup is handled in separate cleanup job.

    :param neo4j_session: Neo4j session
    :param proxmox_client: Proxmox API client
    :param proxmox_host: Proxmox hostname
    :param update_tag: Sync timestamp
    :param common_job_parameters: Common parameters
    :return: Cluster data dict with cluster_id
    """
    logger.info("Syncing Proxmox cluster and nodes")

    # GET - retrieve data from API
    cluster_status = get_cluster_status(proxmox_client)
    nodes = get_nodes(proxmox_client)
    cluster_options = get_cluster_options(proxmox_client)
    # A standalone host has no corosync.conf: the totem endpoint answers null.
    totem = get_corosync_totem(proxmox_client)
    if totem:
        corosync_nodes = get_corosync_nodes(proxmox_client)
        qdevice = get_qdevice_status(proxmox_client)
    else:
        logger.info(
            "Proxmox host %s is not clustered (no corosync configuration), "
            "skipping corosync settings",
            proxmox_host,
        )
        corosync_nodes = []
        qdevice = {}

    # TRANSFORM - manipulate data for ingestion
    cluster_data = transform_cluster_data(cluster_status, proxmox_host)

    # Merge additional cluster metadata
    cluster_data.update(transform_cluster_options(cluster_options))
    cluster_data.update(transform_corosync_totem(totem))
    cluster_data.update(transform_qdevice_status(qdevice))

    transformed_nodes = transform_node_data(
        nodes,
        cluster_data["id"],
        transform_corosync_nodes(corosync_nodes),
    )

    # LOAD - ingest to Neo4j
    load_cluster(neo4j_session, cluster_data, update_tag)
    load_nodes(neo4j_session, transformed_nodes, cluster_data["id"], update_tag)

    # Sync node network interfaces
    all_node_networks = []
    for node in nodes:
        node_name = node["node"]
        # GET network config for this node
        network_interfaces = get_node_network(proxmox_client, node_name)
        # TRANSFORM network data
        transformed_networks = transform_node_network_data(
            network_interfaces,
            node_name,
            cluster_data["id"],
        )
        all_node_networks.extend(transformed_networks)

    # LOAD node network interfaces
    if all_node_networks:
        load_node_networks(
            neo4j_session, all_node_networks, cluster_data["id"], update_tag
        )
        logger.info(
            f"Synced {len(all_node_networks)} network interfaces across {len(nodes)} nodes"
        )

    # CLEANUP - remove stale data
    # Add CLUSTER_ID to parameters for cleanup jobs
    cleanup_params = {**common_job_parameters, "CLUSTER_ID": cluster_data["id"]}
    cleanup(neo4j_session, cleanup_params)

    logger.info(
        f"Synced cluster {cluster_data['id']} with {len(transformed_nodes)} nodes"
    )

    return {"cluster_id": cluster_data["id"]}


def cleanup(
    neo4j_session: neo4j.Session, common_job_parameters: Dict[str, Any]
) -> None:
    """
    Remove stale cluster, node, and network interface data.

    :param neo4j_session: Neo4j session
    :param common_job_parameters: Common parameters including UPDATE_TAG and CLUSTER_ID
    """
    # Cleanup nodes
    GraphJob.from_node_schema(ProxmoxNodeSchema(), common_job_parameters).run(
        neo4j_session
    )

    # Cleanup node network interfaces
    GraphJob.from_node_schema(
        ProxmoxNodeNetworkInterfaceSchema(), common_job_parameters
    ).run(neo4j_session)
