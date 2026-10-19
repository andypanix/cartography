"""
Integration tests for syncing several Proxmox clusters into one graph.

Proxmox names (node pve, storage local, user root@pam, vmid 100, ...) are only
unique inside one cluster, so every non-cluster node ID carries the cluster ID.
"""

from contextlib import ExitStack
from typing import Any
from unittest.mock import MagicMock
from unittest.mock import patch

import cartography.intel.proxmox
import cartography.intel.proxmox.access
import cartography.intel.proxmox.backup
import cartography.intel.proxmox.certificate
import cartography.intel.proxmox.cluster
import cartography.intel.proxmox.compute
import cartography.intel.proxmox.firewall
import cartography.intel.proxmox.guests
import cartography.intel.proxmox.ha
import cartography.intel.proxmox.pool
import cartography.intel.proxmox.storage
from cartography.config import Config
from tests.integration.util import check_nodes
from tests.integration.util import check_rels

CLUSTER_A = "cluster-a"
CLUSTER_B = "cluster-b"
CLUSTERS = (CLUSTER_A, CLUSTER_B)

# Graph ID of each resource inside a cluster, without the cluster prefix.
# Both clusters use the same natural names.
SCOPED_IDS = {
    "ProxmoxNode": "pve",
    "ProxmoxNodeNetworkInterface": "pve:vmbr0",
    "ProxmoxVM": "pve/qemu/100",
    "ProxmoxDisk": "pve/qemu/100:scsi0",
    "ProxmoxNetworkInterface": "pve/qemu/100:net0",
    "ProxmoxStorage": "local",
    "ProxmoxPool": "prod",
    "ProxmoxBackupJob": "nightly",
    "ProxmoxHAGroup": "ha1",
    "ProxmoxHAResource": "vm:100",
    "ProxmoxHARule": "rule1",
    "ProxmoxHAManager": "ha-manager",
    "ProxmoxHALRM": "lrm:pve",
    "ProxmoxUser": "root@pam",
    "ProxmoxGroup": "admins",
    "ProxmoxRole": "Administrator",
    "ProxmoxACL": "/vms/100:root@pam:Administrator",
    "ProxmoxRealm": "pam",
    "ProxmoxRealmSyncJob": "pam-sync",
    "ProxmoxAPIToken": "root@pam!ci",
    "ProxmoxTFAFactor": "root@pam/totp-1",
    "ProxmoxFirewallRule": "vm:100:0",
    "ProxmoxFirewallIPSet": "vm:100:trusted",
    "ProxmoxFirewallAlias": "vm:100:backend",
    "ProxmoxFirewallSecurityGroup": "group:web",
    "ProxmoxCertificate": "pve:pveproxy-ssl.pem",
    "ProxmoxSnapshot": "pve/qemu/100/snapshot/base",
    "ProxmoxCustomCPUModel": "avx",
}


def _id(cluster_id: str, label: str) -> str:
    return f"{cluster_id}/{SCOPED_IDS[label]}"


def _api_data(cluster_id: str, with_storage: bool = True) -> list[tuple[Any, str, Any]]:
    """Mocked API responses of one cluster, as (module, getter, return value)."""
    cluster = cartography.intel.proxmox.cluster
    compute = cartography.intel.proxmox.compute
    storage = cartography.intel.proxmox.storage
    access = cartography.intel.proxmox.access
    firewall = cartography.intel.proxmox.firewall
    return [
        (
            cluster,
            "get_cluster_status",
            [
                {"type": "cluster", "name": cluster_id, "quorate": 1, "nodes": 1},
                {"type": "node", "name": "pve", "online": 1},
            ],
        ),
        (cluster, "get_nodes", [{"node": "pve", "status": "online"}]),
        (cluster, "get_cluster_options", {}),
        (
            cluster,
            "get_corosync_totem",
            {"cluster_name": cluster_id, "config_version": "1"},
        ),
        (
            cluster,
            "get_corosync_nodes",
            [{"node": "pve", "name": "pve", "nodeid": "1", "ring0_addr": "10.0.0.1"}],
        ),
        (cluster, "get_qdevice_status", {}),
        (cluster, "get_node_network", [{"iface": "vmbr0", "type": "bridge"}]),
        (
            compute,
            "get_vms_for_node",
            [
                {
                    "vmid": 100,
                    "name": f"{cluster_id}-vm",
                    "type": "qemu",
                    "node": "pve",
                    "status": "stopped",
                },
            ],
        ),
        (compute, "get_containers_for_node", []),
        (
            compute,
            "get_vm_config",
            {
                "scsi0": "local:vm-100-disk-0,size=8G",
                "net0": "virtio=BC:24:11:00:00:01,bridge=vmbr0",
                "cpu": "custom-avx",
            },
        ),
        (
            cartography.intel.proxmox.guests,
            "get_guest_resources",
            [{"type": "qemu", "vmid": 100, "node": "pve", "pool": "prod"}],
        ),
        (
            cartography.intel.proxmox.guests,
            "get_custom_cpu_models",
            [{"cputype": "custom-avx", "reported-model": "kvm64"}],
        ),
        (
            cartography.intel.proxmox.guests,
            "get_guest_snapshots",
            [{"name": "base", "snaptime": 1700000000}],
        ),
        (
            storage,
            "get_storage",
            [{"storage": "local", "type": "dir"}] if with_storage else [],
        ),
        (storage, "get_storage_status", []),
        (cartography.intel.proxmox.pool, "get_pools", [{"poolid": "prod"}]),
        (
            cartography.intel.proxmox.pool,
            "get_pool_details",
            {"members": [{"type": "qemu", "node": "pve", "vmid": 100}]},
        ),
        (
            cartography.intel.proxmox.backup,
            "get_backup_jobs",
            [{"id": "nightly", "vmid": "100", "storage": "local"}],
        ),
        (cartography.intel.proxmox.ha, "get_ha_groups", [{"group": "ha1"}]),
        (
            cartography.intel.proxmox.ha,
            "get_ha_resources",
            [{"sid": "vm:100", "group": "ha1", "state": "started"}],
        ),
        (
            cartography.intel.proxmox.ha,
            "get_ha_rules",
            [
                {
                    "rule": "rule1",
                    "type": "node-affinity",
                    "resources": "vm:100",
                    "nodes": "pve:2",
                },
            ],
        ),
        (
            cartography.intel.proxmox.ha,
            "get_ha_status",
            [
                {"id": "quorum", "type": "quorum", "node": "pve", "quorate": 1},
                {"id": "master", "type": "master", "node": "pve", "status": "pve"},
                {"id": "lrm:pve", "type": "lrm", "node": "pve", "status": "active"},
            ],
        ),
        (cartography.intel.proxmox.ha, "get_ha_manager_status", {}),
        (
            access,
            "get_users",
            [
                {
                    "userid": "root@pam",
                    "email": f"root@{cluster_id}.example.com",
                    "tokens": [{"tokenid": "ci", "privsep": 1}],
                },
            ],
        ),
        (access, "get_realms", [{"realm": "pam", "type": "pam"}]),
        (access, "get_realm_details", {}),
        (
            access,
            "get_realm_sync_jobs",
            [{"id": "pam-sync", "realm": "pam", "enabled": 1, "schedule": "daily"}],
        ),
        (
            access,
            "get_tfa",
            [
                {
                    "userid": "root@pam",
                    "entries": [{"id": "totp-1", "type": "totp", "created": 1}],
                },
            ],
        ),
        (access, "get_groups", [{"groupid": "admins"}]),
        (access, "get_group_members", {"admins": ["root@pam"]}),
        (access, "get_roles", [{"roleid": "Administrator", "special": 1}]),
        (
            access,
            "get_acls",
            [{"path": "/vms/100", "roleid": "Administrator", "ugid": "root@pam"}],
        ),
        # The only rule is a guest rule, so the APPLIES_TO_VM matcher (vmid and
        # cluster_id) is checked across clusters that share vmid 100. Its
        # source and dest name the guest IP set and alias, which both clusters
        # define with the same names.
        (firewall, "get_cluster_firewall_rules", []),
        (firewall, "get_cluster_ipsets", []),
        (firewall, "get_node_firewall_rules", []),
        (
            firewall,
            "get_vm_firewall_rules",
            [
                {
                    "pos": 0,
                    "type": "in",
                    "action": "ACCEPT",
                    "dport": "22",
                    "source": "+trusted",
                    "dest": "backend",
                },
            ],
        ),
        (firewall, "get_container_firewall_rules", []),
        (firewall, "get_cluster_firewall_options", {"enable": 1}),
        (firewall, "get_node_firewall_options", {}),
        (firewall, "get_guest_firewall_options", {"enable": 1}),
        (firewall, "get_security_groups", [{"group": "web"}]),
        (firewall, "get_security_group_rules", []),
        (firewall, "get_cluster_aliases", []),
        (firewall, "get_guest_aliases", [{"name": "backend", "cidr": "10.0.0.5"}]),
        (firewall, "get_guest_ipsets", [{"name": "trusted"}]),
        (firewall, "get_guest_ipset_cidrs", [{"cidr": "10.0.0.0/8"}]),
        (
            cartography.intel.proxmox.certificate,
            "get_node_certificates",
            [{"filename": "pveproxy-ssl.pem", "fingerprint": f"fp-{cluster_id}"}],
        ),
    ]


def _sync_cluster(
    neo4j_session,
    cluster_id: str,
    update_tag: int,
    with_storage: bool = True,
) -> None:
    """Run start_proxmox_ingestion against one mocked cluster."""
    proxmox = MagicMock()
    proxmox.nodes.get.return_value = [{"node": "pve"}]
    config = Config(
        neo4j_uri="bolt://localhost:7687",
        update_tag=update_tag,
        proxmox_host=f"{cluster_id}.example.com",
    )
    with ExitStack() as stack:
        stack.enter_context(
            patch.object(
                cartography.intel.proxmox,
                "_get_proxmox_client",
                return_value=proxmox,
            ),
        )
        for module, getter, data in _api_data(cluster_id, with_storage):
            stack.enter_context(patch.object(module, getter, return_value=data))
        cartography.intel.proxmox.start_proxmox_ingestion(neo4j_session, config)


def _resource_rels(neo4j_session, label: str) -> set[tuple[str, str]]:
    return check_rels(
        neo4j_session,
        "ProxmoxCluster",
        "id",
        label,
        "id",
        "RESOURCE",
        rel_direction_right=True,
    )


def test_two_clusters_with_identical_names_stay_separate(neo4j_session):
    """
    Two clusters that use the same node, storage, user, vmid and ACL names get
    their own nodes and edges, and the cleanup of one cluster leaves the other
    cluster's data alone.
    """
    neo4j_session.run("MATCH (n) DETACH DELETE n")

    # Act - sync both clusters into the same graph
    for cluster_id in CLUSTERS:
        _sync_cluster(neo4j_session, cluster_id, 1)

    # Assert - each cluster has its own copy of every resource, attached to it
    # by its RESOURCE edge, and keeps its natural name and cluster_id
    for label in SCOPED_IDS:
        expected = {(c, _id(c, label)) for c in CLUSTERS}
        assert _resource_rels(neo4j_session, label) == expected, label
        assert check_nodes(neo4j_session, label, ["id", "cluster_id"]) == {
            (_id(c, label), c) for c in CLUSTERS
        }, label
    assert check_nodes(neo4j_session, "ProxmoxNode", ["id", "name"]) == {
        (_id(c, "ProxmoxNode"), "pve") for c in CLUSTERS
    }
    assert check_nodes(neo4j_session, "ProxmoxStorage", ["id", "name"]) == {
        (_id(c, "ProxmoxStorage"), "local") for c in CLUSTERS
    }
    assert check_nodes(neo4j_session, "ProxmoxUser", ["id", "userid", "email"]) == {
        (_id(c, "ProxmoxUser"), "root@pam", f"root@{c}.example.com") for c in CLUSTERS
    }
    assert check_nodes(neo4j_session, "ProxmoxVM", ["id", "vmid", "name"]) == {
        (_id(c, "ProxmoxVM"), 100, f"{c}-vm") for c in CLUSTERS
    }

    # Assert - edges between resources never cross clusters
    cluster_edges = (
        ("ProxmoxNode", "HOSTS_VM", "ProxmoxVM"),
        ("ProxmoxNode", "HAS_NETWORK_INTERFACE", "ProxmoxNodeNetworkInterface"),
        ("ProxmoxNode", "HAS_CERTIFICATE", "ProxmoxCertificate"),
        ("ProxmoxVM", "HAS_DISK", "ProxmoxDisk"),
        ("ProxmoxDisk", "STORED_ON", "ProxmoxStorage"),
        ("ProxmoxVM", "HAS_NETWORK_INTERFACE", "ProxmoxNetworkInterface"),
        ("ProxmoxVM", "HAS_SNAPSHOT", "ProxmoxSnapshot"),
        ("ProxmoxVM", "USES_CPU_MODEL", "ProxmoxCustomCPUModel"),
        ("ProxmoxStorage", "AVAILABLE_ON", "ProxmoxNode"),
        ("ProxmoxPool", "CONTAINS_VM", "ProxmoxVM"),
        ("ProxmoxBackupJob", "BACKS_UP", "ProxmoxVM"),
        ("ProxmoxBackupJob", "BACKS_UP_TO", "ProxmoxStorage"),
        ("ProxmoxHAResource", "MEMBER_OF_HA_GROUP", "ProxmoxHAGroup"),
        ("ProxmoxHAResource", "PROTECTS", "ProxmoxVM"),
        ("ProxmoxHARule", "APPLIES_TO_HA_RESOURCE", "ProxmoxHAResource"),
        ("ProxmoxHARule", "APPLIES_TO_NODE", "ProxmoxNode"),
        ("ProxmoxHAManager", "CRM_MASTER", "ProxmoxNode"),
        ("ProxmoxHALRM", "RUNS_ON", "ProxmoxNode"),
        ("ProxmoxUser", "MEMBER_OF_GROUP", "ProxmoxGroup"),
        ("ProxmoxACL", "GRANTS_ROLE", "ProxmoxRole"),
        ("ProxmoxACL", "APPLIES_TO_USER", "ProxmoxUser"),
        ("ProxmoxUser", "IN_REALM", "ProxmoxRealm"),
        ("ProxmoxRealmSyncJob", "SYNCS", "ProxmoxRealm"),
        ("ProxmoxUser", "HAS_API_TOKEN", "ProxmoxAPIToken"),
        ("ProxmoxUser", "HAS_TFA_FACTOR", "ProxmoxTFAFactor"),
        ("ProxmoxACL", "GRANTS_ACCESS_TO", "ProxmoxVM"),
        ("ProxmoxUser", "HAS_PERMISSION", "ProxmoxVM"),
        ("ProxmoxFirewallRule", "APPLIES_TO_VM", "ProxmoxVM"),
        ("ProxmoxFirewallRule", "HAS_SOURCE", "ProxmoxFirewallIPSet"),
        ("ProxmoxFirewallRule", "HAS_DESTINATION", "ProxmoxFirewallAlias"),
        ("ProxmoxVM", "HAS_FIREWALL_IPSET", "ProxmoxFirewallIPSet"),
        ("ProxmoxVM", "HAS_FIREWALL_ALIAS", "ProxmoxFirewallAlias"),
    )
    for source, rel, target in cluster_edges:
        assert check_rels(
            neo4j_session,
            source,
            "id",
            target,
            "id",
            rel,
            rel_direction_right=True,
        ) == {(_id(c, source), _id(c, target)) for c in CLUSTERS}, rel

    # Act - re-sync cluster A with a later update tag and without its storage
    _sync_cluster(neo4j_session, CLUSTER_A, 2, with_storage=False)

    # Assert - only cluster A's stale storage is deleted; cluster B's copy,
    # synced earlier with the same name, survives untouched
    assert check_nodes(neo4j_session, "ProxmoxStorage", ["id", "lastupdated"]) == {
        (_id(CLUSTER_B, "ProxmoxStorage"), 1),
    }
    assert _resource_rels(neo4j_session, "ProxmoxStorage") == {
        (CLUSTER_B, _id(CLUSTER_B, "ProxmoxStorage")),
    }

    # Assert - every other resource keeps one node per cluster, with cluster A's
    # refreshed and cluster B's left as they were
    for label in SCOPED_IDS:
        if label == "ProxmoxStorage":
            continue
        assert check_nodes(neo4j_session, label, ["id", "lastupdated"]) == {
            (_id(CLUSTER_A, label), 2),
            (_id(CLUSTER_B, label), 1),
        }, label
    assert check_rels(
        neo4j_session,
        "ProxmoxUser",
        "id",
        "ProxmoxVM",
        "id",
        "HAS_PERMISSION",
        rel_direction_right=True,
    ) == {(_id(c, "ProxmoxUser"), _id(c, "ProxmoxVM")) for c in CLUSTERS}
