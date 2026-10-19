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
import cartography.intel.proxmox.backup_coverage
import cartography.intel.proxmox.ceph
import cartography.intel.proxmox.certificate
import cartography.intel.proxmox.cluster
import cartography.intel.proxmox.compute
import cartography.intel.proxmox.firewall
import cartography.intel.proxmox.guests
import cartography.intel.proxmox.ha
import cartography.intel.proxmox.integrations
import cartography.intel.proxmox.mapping
import cartography.intel.proxmox.node_details
import cartography.intel.proxmox.pool
import cartography.intel.proxmox.replication
import cartography.intel.proxmox.storage
import cartography.intel.proxmox.storage_content
from cartography.config import Config
from tests.integration.util import check_nodes
from tests.integration.util import check_rels

CLUSTER_A = "cluster-a"
CLUSTER_B = "cluster-b"
CLUSTERS = (CLUSTER_A, CLUSTER_B)
# Both clusters report the same Ceph fsid, as clones of one template would.
CEPH_FSID = "00000000-0000-4000-8000-000000000000"

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
    "ProxmoxResourceMapping": "pci/gpu",
    "ProxmoxNotificationTarget": "mail-to-root",
    "ProxmoxNotificationMatcher": "default-matcher",
    "ProxmoxMetricServer": "influx",
    "ProxmoxACMEAccount": "default",
    "ProxmoxPhysicalDisk": "pve:/dev/sda",
    "ProxmoxZFSPool": "pve:zfs:rpool",
    "ProxmoxLVMVolumeGroup": "pve:lvm:pve",
    "ProxmoxLVMThinPool": "pve:lvmthin:pve/data",
    "ProxmoxManagedDirectory": "pve:directory:/mnt/pve/backup",
    "ProxmoxPackage": "pve:package:pve-manager",
    "ProxmoxAPTRepository": "pve:apt:/etc/apt/sources.list:0",
    "ProxmoxSubscription": "pve:subscription",
    "ProxmoxNodeConfig": "pve:config",
    "ProxmoxService": "pve:service:pveproxy",
    "ProxmoxPCIDevice": "pve:pci:0000:01:00.0",
    "ProxmoxBackupDefaults": "pve",
    "ProxmoxBackupArchive": "pve/local:backup/vzdump-qemu-100-2026_01_01-00_00_00.vma.zst",
    "ProxmoxStorageTemplate": "pve/local:iso/debian.iso",
    "ProxmoxReplicationJob": "100-0",
    "ProxmoxCephCluster": CEPH_FSID,
    "ProxmoxCephMonitor": "mon.pve",
    "ProxmoxCephManager": "mgr.pve",
    "ProxmoxCephMetadataServer": "mds.pve",
    "ProxmoxCephOSD": "osd.0",
    "ProxmoxCephPool": "pool:rbd",
    "ProxmoxCephCrushRule": "crush_rule:replicated_rule",
    "ProxmoxCephFilesystem": "fs:cephfs",
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
    mapping = cartography.intel.proxmox.mapping
    integrations = cartography.intel.proxmox.integrations
    ceph = cartography.intel.proxmox.ceph
    return [
        (
            ceph,
            "get_ceph_status",
            {"fsid": CEPH_FSID, "health": {"status": "HEALTH_OK"}},
        ),
        (ceph, "get_ceph_metadata", {"node": {"pve": {}}}),
        (ceph, "get_ceph_flags", []),
        (ceph, "get_ceph_health_mutes", []),
        (ceph, "get_ceph_monitors", [{"name": "pve", "host": "pve"}]),
        (ceph, "get_ceph_managers", [{"name": "pve", "host": "pve"}]),
        (
            ceph,
            "get_ceph_metadata_servers",
            [{"name": "pve", "host": "pve", "fs_name": "cephfs"}],
        ),
        (
            ceph,
            "get_ceph_osd_tree",
            {
                "root": {
                    "children": [
                        {
                            "type": "host",
                            "name": "pve",
                            "children": [{"id": 0, "type": "osd", "name": "osd.0"}],
                        },
                    ],
                },
            },
        ),
        (ceph, "get_ceph_osd_metadata", {}),
        (ceph, "get_ceph_osd_lv_info", {}),
        (ceph, "get_ceph_rules", [{"name": "replicated_rule"}]),
        (
            ceph,
            "get_ceph_pools",
            [{"pool_name": "rbd", "crush_rule_name": "replicated_rule"}],
        ),
        (ceph, "get_ceph_pool_status", {}),
        (
            ceph,
            "get_ceph_filesystems",
            [{"name": "cephfs", "metadata_pool": "rbd", "data_pool": "rbd"}],
        ),
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
                "hostpci0": "mapping=gpu",
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
        (
            storage,
            "get_storage_status",
            [
                {
                    "storage": "local",
                    "content": "images,backup,iso",
                    "active": 1,
                    "enabled": 1,
                    "shared": 0,
                },
            ],
        ),
        (
            cartography.intel.proxmox.storage_content,
            "get_storage_content",
            [
                {
                    "volid": "local:backup/vzdump-qemu-100-2026_01_01-00_00_00.vma.zst",
                    "content": "backup",
                    "vmid": 100,
                },
                {"volid": "local:iso/debian.iso", "content": "iso"},
            ],
        ),
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
        (
            cartography.intel.proxmox.backup_coverage,
            "get_included_volumes",
            {
                "children": [
                    {
                        "id": 100,
                        "type": "qemu",
                        "children": [{"id": "scsi0", "included": True}],
                    },
                ],
            },
        ),
        (cartography.intel.proxmox.backup_coverage, "get_not_backed_up", []),
        (
            cartography.intel.proxmox.backup_coverage,
            "get_vzdump_defaults",
            {"storage": "local"},
        ),
        (
            cartography.intel.proxmox.replication,
            "get_cluster_replication_jobs",
            [{"id": "100-0", "guest": 100, "target": "pve", "type": "local"}],
        ),
        (
            cartography.intel.proxmox.replication,
            "get_node_replication_status",
            [{"id": "100-0", "fail_count": 0}],
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
        (
            mapping,
            "get_pci_mappings",
            [{"id": "gpu", "map": ["node=pve,path=0000:01:00.0"]}],
        ),
        (mapping, "get_usb_mappings", []),
        (mapping, "get_dir_mappings", []),
        (
            integrations,
            "get_notification_targets",
            [{"name": "mail-to-root", "type": "sendmail"}],
        ),
        (
            integrations,
            "get_notification_endpoints",
            [],
        ),
        (
            integrations,
            "get_notification_matchers",
            [{"name": "default-matcher", "target": ["mail-to-root"]}],
        ),
        (
            integrations,
            "get_metric_servers",
            [{"id": "influx", "type": "influxdb", "server": "influx", "port": 8086}],
        ),
        (integrations, "get_acme_accounts", [{"name": "default"}]),
        (integrations, "get_acme_account", {"directory": "https://acme.example"}),
        *_node_details_api_data(cluster_id),
    ]


def _node_details_api_data(cluster_id: str) -> list[tuple[Any, str, Any]]:
    """Mocked node detail responses; disk, pool and device names match across clusters."""
    details = cartography.intel.proxmox.node_details
    return [
        (details, "get_node_disks", [{"devpath": "/dev/sda", "serial": cluster_id}]),
        (details, "get_disk_smart", {"health": "PASSED"}),
        (details, "get_zfs_pools", [{"name": "rpool"}]),
        (
            details,
            "get_zfs_pool_details",
            {"children": [{"name": "rpool", "children": [{"name": "sda3"}]}]},
        ),
        (
            details,
            "get_lvm_volume_groups",
            {"children": [{"name": "pve", "children": [{"name": "/dev/sda2"}]}]},
        ),
        (details, "get_lvm_thin_pools", [{"lv": "data", "vg": "pve"}]),
        (
            details,
            "get_managed_directories",
            [{"path": "/mnt/pve/backup", "device": "/dev/sda4"}],
        ),
        (
            details,
            "get_package_versions",
            [{"Package": "pve-manager", "Version": "9.0.10"}],
        ),
        (
            details,
            "get_apt_repositories",
            {
                "files": [
                    {
                        "path": "/etc/apt/sources.list",
                        "repositories": [{"Enabled": True}],
                    },
                ],
            },
        ),
        (details, "get_subscription", {"status": "notfound"}),
        (details, "get_node_config", {}),
        (details, "get_node_dns", {}),
        (details, "get_node_time", {"timezone": "UTC"}),
        (details, "get_node_services", [{"service": "pveproxy", "name": "pveproxy"}]),
        (details, "get_pci_devices", [{"id": "0000:01:00.0", "mdev": 1}]),
        (details, "get_pci_mdev_types", [{"type": "nvidia-1", "available": 1}]),
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
        ("ProxmoxBackupJob", "COVERS", "ProxmoxVM"),
        ("ProxmoxBackupJob", "INCLUDES_DISK", "ProxmoxDisk"),
        ("ProxmoxNode", "HAS_BACKUP_DEFAULTS", "ProxmoxBackupDefaults"),
        ("ProxmoxBackupDefaults", "BACKS_UP_TO", "ProxmoxStorage"),
        ("ProxmoxBackupArchive", "STORED_ON", "ProxmoxStorage"),
        ("ProxmoxBackupArchive", "BACKUP_OF", "ProxmoxVM"),
        ("ProxmoxStorageTemplate", "STORED_ON", "ProxmoxStorage"),
        ("ProxmoxReplicationJob", "REPLICATES", "ProxmoxVM"),
        ("ProxmoxReplicationJob", "REPLICATES_TO", "ProxmoxNode"),
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
        ("ProxmoxResourceMapping", "AVAILABLE_ON", "ProxmoxNode"),
        ("ProxmoxVM", "USES_MAPPING", "ProxmoxResourceMapping"),
        ("ProxmoxNotificationMatcher", "ROUTES_TO", "ProxmoxNotificationTarget"),
        ("ProxmoxNode", "HAS_PHYSICAL_DISK", "ProxmoxPhysicalDisk"),
        ("ProxmoxNode", "HAS_ZFS_POOL", "ProxmoxZFSPool"),
        ("ProxmoxZFSPool", "USES_DISK", "ProxmoxPhysicalDisk"),
        ("ProxmoxLVMVolumeGroup", "USES_DISK", "ProxmoxPhysicalDisk"),
        ("ProxmoxLVMVolumeGroup", "CONTAINS_THIN_POOL", "ProxmoxLVMThinPool"),
        ("ProxmoxManagedDirectory", "USES_DISK", "ProxmoxPhysicalDisk"),
        ("ProxmoxNode", "HAS_PACKAGE", "ProxmoxPackage"),
        ("ProxmoxNode", "HAS_APT_REPOSITORY", "ProxmoxAPTRepository"),
        ("ProxmoxNode", "HAS_SUBSCRIPTION", "ProxmoxSubscription"),
        ("ProxmoxNode", "HAS_CONFIG", "ProxmoxNodeConfig"),
        ("ProxmoxNode", "HAS_SERVICE", "ProxmoxService"),
        ("ProxmoxNode", "HAS_PCI_DEVICE", "ProxmoxPCIDevice"),
        ("ProxmoxCephOSD", "RUNS_ON", "ProxmoxNode"),
        ("ProxmoxCephMonitor", "MEMBER_OF_CEPH_CLUSTER", "ProxmoxCephCluster"),
        ("ProxmoxCephPool", "USES_CRUSH_RULE", "ProxmoxCephCrushRule"),
        ("ProxmoxCephFilesystem", "USES_POOL", "ProxmoxCephPool"),
        ("ProxmoxCephMetadataServer", "SERVES", "ProxmoxCephFilesystem"),
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
