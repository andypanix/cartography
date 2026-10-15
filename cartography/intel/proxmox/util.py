"""
Helpers shared by the Proxmox sync modules.
"""

from typing import Any

# Proxmox resource names (node, storage, user, role, VM ID, ...) are only
# unique inside one cluster. Every non-cluster node ID is prefixed with the
# cluster ID so several clusters can share one graph. The cluster ID is the
# cluster name (letters, digits and dashes) or the API hostname with dots
# replaced by dashes, so it never contains "/" and the first "/" of an ID
# always ends the cluster prefix.
CLUSTER_ID_SEPARATOR = "/"


def cluster_scoped_id(cluster_id: str, natural_id: Any) -> str:
    """
    Build the graph ID of a Proxmox resource that is unique only in its cluster.

    :param cluster_id: ID of the cluster that owns the resource
    :param natural_id: Resource ID inside the cluster, such as pve or local
    :return: ID in the form cluster_id/natural_id
    """
    return f"{cluster_id}{CLUSTER_ID_SEPARATOR}{natural_id}"
