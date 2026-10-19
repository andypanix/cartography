from dataclasses import dataclass

from cartography.models.core.common import PropertyRef
from cartography.models.core.nodes import CartographyNodeProperties
from cartography.models.core.nodes import CartographyNodeSchema
from cartography.models.core.relationships import CartographyRelProperties
from cartography.models.core.relationships import CartographyRelSchema
from cartography.models.core.relationships import LinkDirection
from cartography.models.core.relationships import make_target_node_matcher
from cartography.models.core.relationships import OtherRelationships
from cartography.models.core.relationships import TargetNodeMatcher

# ============================================================================
# Shared relationships
# ============================================================================


@dataclass(frozen=True)
class ProxmoxCephRelProperties(CartographyRelProperties):
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)


@dataclass(frozen=True)
class ProxmoxCephToClusterRel(CartographyRelSchema):
    """The Proxmox VE cluster contains the Ceph resource."""

    target_node_label: str = "ProxmoxCluster"
    target_node_matcher: TargetNodeMatcher = make_target_node_matcher(
        {"id": PropertyRef("CLUSTER_ID", set_in_kwargs=True)},
    )
    direction: LinkDirection = LinkDirection.INWARD
    rel_label: str = "RESOURCE"
    properties: ProxmoxCephRelProperties = ProxmoxCephRelProperties()


@dataclass(frozen=True)
class ProxmoxCephToCephClusterRel(CartographyRelSchema):
    """The Ceph resource belongs to the Ceph cluster of the Proxmox VE cluster."""

    target_node_label: str = "ProxmoxCephCluster"
    target_node_matcher: TargetNodeMatcher = make_target_node_matcher(
        {"id": PropertyRef("ceph_cluster_id")},
    )
    direction: LinkDirection = LinkDirection.OUTWARD
    rel_label: str = "MEMBER_OF_CEPH_CLUSTER"
    properties: ProxmoxCephRelProperties = ProxmoxCephRelProperties()


@dataclass(frozen=True)
class ProxmoxCephDaemonToNodeRel(CartographyRelSchema):
    """The Ceph daemon runs on the Proxmox VE node."""

    target_node_label: str = "ProxmoxNode"
    target_node_matcher: TargetNodeMatcher = make_target_node_matcher(
        {"id": PropertyRef("node_id")},
    )
    direction: LinkDirection = LinkDirection.OUTWARD
    rel_label: str = "RUNS_ON"
    properties: ProxmoxCephRelProperties = ProxmoxCephRelProperties()


# ============================================================================
# ProxmoxCephCluster
# ============================================================================


@dataclass(frozen=True)
class ProxmoxCephClusterNodeProperties(CartographyNodeProperties):
    id: PropertyRef = PropertyRef(
        "id",
        description="Ceph cluster ID in the form cluster_id/fsid.",
    )
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)
    fsid: PropertyRef = PropertyRef(
        "fsid",
        extra_index=True,
        description="Ceph cluster file system ID (fsid), a UUID unique to the Ceph cluster.",
    )
    cluster_id: PropertyRef = PropertyRef(
        "cluster_id",
        description="ID of the Proxmox VE cluster that runs the Ceph cluster.",
    )
    health_status: PropertyRef = PropertyRef(
        "health_status",
        description="Overall Ceph health, such as HEALTH_OK, HEALTH_WARN, or HEALTH_ERR.",
    )
    health_checks: PropertyRef = PropertyRef(
        "health_checks",
        description="Codes of the health checks Ceph currently reports, such as OSD_DOWN.",
    )
    muted_health_checks: PropertyRef = PropertyRef(
        "muted_health_checks",
        description="Codes of the health checks an operator muted. Proxmox VE 9 only.",
    )
    flags: PropertyRef = PropertyRef(
        "flags",
        description="Cluster-wide OSD flags that are set, such as noout or noscrub.",
    )
    ceph_versions: PropertyRef = PropertyRef(
        "ceph_versions",
        description="Distinct short Ceph versions reported by the daemons and nodes of the cluster.",
    )


@dataclass(frozen=True)
class ProxmoxCephClusterSchema(CartographyNodeSchema):
    """A hyper-converged Ceph cluster deployed and managed by a Proxmox VE cluster."""

    label: str = "ProxmoxCephCluster"
    properties: ProxmoxCephClusterNodeProperties = ProxmoxCephClusterNodeProperties()
    sub_resource_relationship: ProxmoxCephToClusterRel = ProxmoxCephToClusterRel()


# ============================================================================
# Daemons: monitors, managers, metadata servers
# ============================================================================


@dataclass(frozen=True)
class ProxmoxCephMonitorNodeProperties(CartographyNodeProperties):
    id: PropertyRef = PropertyRef(
        "id",
        description="Monitor ID in the form cluster_id/mon.name.",
    )
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)
    name: PropertyRef = PropertyRef(
        "name",
        extra_index=True,
        description="Monitor ID inside Ceph, usually the node hostname.",
    )
    cluster_id: PropertyRef = PropertyRef(
        "cluster_id",
        description="ID of the Proxmox VE cluster that runs the monitor.",
    )
    host: PropertyRef = PropertyRef(
        "host", description="Proxmox VE node the monitor runs on."
    )
    addr: PropertyRef = PropertyRef(
        "addr",
        description="Address the monitor advertises, in Ceph format such as IP:PORT/NONCE.",
    )
    rank: PropertyRef = PropertyRef(
        "rank", description="Rank of the monitor in the monitor map."
    )
    quorum: PropertyRef = PropertyRef(
        "quorum",
        description="Whether the monitor is part of the current quorum.",
    )
    state: PropertyRef = PropertyRef(
        "state",
        description="Run state of the monitor, such as running, stopped, or unknown.",
    )
    ceph_version: PropertyRef = PropertyRef(
        "ceph_version",
        description="Short Ceph version of the monitor daemon, such as 19.2.0.",
    )


@dataclass(frozen=True)
class ProxmoxCephMonitorSchema(CartographyNodeSchema):
    """A Ceph monitor daemon, which keeps the cluster maps of a Proxmox VE Ceph cluster."""

    label: str = "ProxmoxCephMonitor"
    properties: ProxmoxCephMonitorNodeProperties = ProxmoxCephMonitorNodeProperties()
    sub_resource_relationship: ProxmoxCephToClusterRel = ProxmoxCephToClusterRel()
    other_relationships: OtherRelationships = OtherRelationships(
        [ProxmoxCephToCephClusterRel(), ProxmoxCephDaemonToNodeRel()],
    )


@dataclass(frozen=True)
class ProxmoxCephManagerNodeProperties(CartographyNodeProperties):
    id: PropertyRef = PropertyRef(
        "id",
        description="Manager ID in the form cluster_id/mgr.name.",
    )
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)
    name: PropertyRef = PropertyRef(
        "name",
        extra_index=True,
        description="Manager ID inside Ceph, usually the node hostname.",
    )
    cluster_id: PropertyRef = PropertyRef(
        "cluster_id",
        description="ID of the Proxmox VE cluster that runs the manager.",
    )
    host: PropertyRef = PropertyRef(
        "host", description="Proxmox VE node the manager runs on."
    )
    addr: PropertyRef = PropertyRef(
        "addr",
        description="Address the manager advertises, in Ceph format such as IP:PORT/NONCE.",
    )
    state: PropertyRef = PropertyRef(
        "state",
        description="Manager state, such as active, standby, stopped, or unknown.",
    )
    ceph_version: PropertyRef = PropertyRef(
        "ceph_version",
        description="Short Ceph version of the manager daemon. Proxmox VE 9 only.",
    )


@dataclass(frozen=True)
class ProxmoxCephManagerSchema(CartographyNodeSchema):
    """A Ceph manager daemon, which runs monitoring and management modules of a Proxmox VE Ceph cluster."""

    label: str = "ProxmoxCephManager"
    properties: ProxmoxCephManagerNodeProperties = ProxmoxCephManagerNodeProperties()
    sub_resource_relationship: ProxmoxCephToClusterRel = ProxmoxCephToClusterRel()
    other_relationships: OtherRelationships = OtherRelationships(
        [ProxmoxCephToCephClusterRel(), ProxmoxCephDaemonToNodeRel()],
    )


@dataclass(frozen=True)
class ProxmoxCephMDSToFilesystemRel(CartographyRelSchema):
    """The metadata server serves the CephFS file system."""

    target_node_label: str = "ProxmoxCephFilesystem"
    target_node_matcher: TargetNodeMatcher = make_target_node_matcher(
        {"id": PropertyRef("filesystem_id")},
    )
    direction: LinkDirection = LinkDirection.OUTWARD
    rel_label: str = "SERVES"
    properties: ProxmoxCephRelProperties = ProxmoxCephRelProperties()


@dataclass(frozen=True)
class ProxmoxCephMetadataServerNodeProperties(CartographyNodeProperties):
    id: PropertyRef = PropertyRef(
        "id",
        description="Metadata server ID in the form cluster_id/mds.name.",
    )
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)
    name: PropertyRef = PropertyRef(
        "name",
        extra_index=True,
        description="Metadata server ID inside Ceph.",
    )
    cluster_id: PropertyRef = PropertyRef(
        "cluster_id",
        description="ID of the Proxmox VE cluster that runs the metadata server.",
    )
    host: PropertyRef = PropertyRef(
        "host", description="Proxmox VE node the metadata server runs on."
    )
    addr: PropertyRef = PropertyRef(
        "addr",
        description="Address the metadata server advertises, in Ceph format such as IP:PORT/NONCE.",
    )
    state: PropertyRef = PropertyRef(
        "state",
        description="Metadata server state, such as up:active, up:standby, stopped, or unknown.",
    )
    rank: PropertyRef = PropertyRef(
        "rank",
        description="Rank of the metadata server in its file system, -1 for a standby.",
    )
    standby_replay: PropertyRef = PropertyRef(
        "standby_replay",
        description="Whether the standby metadata server follows the active one as a hot standby.",
    )
    fs_name: PropertyRef = PropertyRef(
        "fs_name",
        description="Name of the CephFS file system the metadata server serves. Proxmox VE 9 only.",
    )
    ceph_version: PropertyRef = PropertyRef(
        "ceph_version",
        description="Short Ceph version of the metadata server daemon. Proxmox VE 9 only.",
    )


@dataclass(frozen=True)
class ProxmoxCephMetadataServerSchema(CartographyNodeSchema):
    """A Ceph metadata server (MDS) daemon, which serves CephFS metadata in a Proxmox VE Ceph cluster."""

    label: str = "ProxmoxCephMetadataServer"
    properties: ProxmoxCephMetadataServerNodeProperties = (
        ProxmoxCephMetadataServerNodeProperties()
    )
    sub_resource_relationship: ProxmoxCephToClusterRel = ProxmoxCephToClusterRel()
    other_relationships: OtherRelationships = OtherRelationships(
        [
            ProxmoxCephToCephClusterRel(),
            ProxmoxCephDaemonToNodeRel(),
            ProxmoxCephMDSToFilesystemRel(),
        ],
    )


# ============================================================================
# OSDs
# ============================================================================


@dataclass(frozen=True)
class ProxmoxCephOSDNodeProperties(CartographyNodeProperties):
    id: PropertyRef = PropertyRef(
        "id",
        description="OSD ID in the form cluster_id/osd.N.",
    )
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)
    osd_id: PropertyRef = PropertyRef(
        "osd_id",
        extra_index=True,
        description="Numeric OSD ID inside Ceph.",
    )
    name: PropertyRef = PropertyRef("name", description="OSD name, such as osd.0.")
    cluster_id: PropertyRef = PropertyRef(
        "cluster_id",
        description="ID of the Proxmox VE cluster that runs the OSD.",
    )
    host: PropertyRef = PropertyRef(
        "host", description="Proxmox VE node that holds the OSD."
    )
    status: PropertyRef = PropertyRef(
        "status", description="Whether the OSD is up or down."
    )
    is_in: PropertyRef = PropertyRef(
        "is_in",
        description="Whether the OSD is in the cluster and receives data.",
    )
    device_class: PropertyRef = PropertyRef(
        "device_class",
        description="CRUSH device class of the OSD, such as hdd, ssd, or nvme.",
    )
    crush_weight: PropertyRef = PropertyRef(
        "crush_weight",
        description="CRUSH weight of the OSD, which sets its share of the data.",
    )
    objectstore: PropertyRef = PropertyRef(
        "objectstore",
        description="Object store type of the OSD, such as bluestore.",
    )
    encrypted: PropertyRef = PropertyRef(
        "encrypted",
        description="Whether the OSD is encrypted with LUKS through dm-crypt.",
    )
    ceph_version: PropertyRef = PropertyRef(
        "ceph_version",
        description="Ceph version of the OSD service.",
    )
    front_addr: PropertyRef = PropertyRef(
        "front_addr",
        description="Address and port the OSD uses for clients and monitors.",
    )
    back_addr: PropertyRef = PropertyRef(
        "back_addr",
        description="Address and port the OSD uses to talk to other OSDs.",
    )
    physical_devices: PropertyRef = PropertyRef(
        "physical_devices",
        description="Physical devices under the OSD block, DB, and WAL devices, such as sdb.",
    )
    device_types: PropertyRef = PropertyRef(
        "device_types",
        description="Types of the OSD devices, such as hdd or ssd.",
    )
    lv_path: PropertyRef = PropertyRef(
        "lv_path",
        description="Path of the LVM logical volume that holds the OSD block device.",
    )
    vg_name: PropertyRef = PropertyRef(
        "vg_name",
        description="LVM volume group of the OSD block device.",
    )
    lv_uuid: PropertyRef = PropertyRef(
        "lv_uuid",
        description="UUID of the LVM logical volume of the OSD block device.",
    )
    lv_size: PropertyRef = PropertyRef(
        "lv_size",
        description="Size in bytes of the LVM logical volume of the OSD block device.",
    )


@dataclass(frozen=True)
class ProxmoxCephOSDSchema(CartographyNodeSchema):
    """A Ceph object storage daemon (OSD), which stores data on one disk of a Proxmox VE node."""

    label: str = "ProxmoxCephOSD"
    properties: ProxmoxCephOSDNodeProperties = ProxmoxCephOSDNodeProperties()
    sub_resource_relationship: ProxmoxCephToClusterRel = ProxmoxCephToClusterRel()
    other_relationships: OtherRelationships = OtherRelationships(
        [ProxmoxCephToCephClusterRel(), ProxmoxCephDaemonToNodeRel()],
    )


# ============================================================================
# CRUSH rules
# ============================================================================


@dataclass(frozen=True)
class ProxmoxCephCrushRuleNodeProperties(CartographyNodeProperties):
    id: PropertyRef = PropertyRef(
        "id",
        description="CRUSH rule ID in the form cluster_id/crush_rule:name.",
    )
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)
    name: PropertyRef = PropertyRef(
        "name",
        extra_index=True,
        description="Name of the CRUSH rule.",
    )
    cluster_id: PropertyRef = PropertyRef(
        "cluster_id",
        description="ID of the Proxmox VE cluster that runs the Ceph cluster.",
    )


@dataclass(frozen=True)
class ProxmoxCephCrushRuleSchema(CartographyNodeSchema):
    """A CRUSH rule that decides where a Ceph pool places its data in a Proxmox VE Ceph cluster."""

    label: str = "ProxmoxCephCrushRule"
    properties: ProxmoxCephCrushRuleNodeProperties = (
        ProxmoxCephCrushRuleNodeProperties()
    )
    sub_resource_relationship: ProxmoxCephToClusterRel = ProxmoxCephToClusterRel()
    other_relationships: OtherRelationships = OtherRelationships(
        [ProxmoxCephToCephClusterRel()],
    )


# ============================================================================
# Pools
# ============================================================================


@dataclass(frozen=True)
class ProxmoxCephPoolToCrushRuleRel(CartographyRelSchema):
    """The Ceph pool places its data with the CRUSH rule."""

    target_node_label: str = "ProxmoxCephCrushRule"
    target_node_matcher: TargetNodeMatcher = make_target_node_matcher(
        {"id": PropertyRef("crush_rule_id")},
    )
    direction: LinkDirection = LinkDirection.OUTWARD
    rel_label: str = "USES_CRUSH_RULE"
    properties: ProxmoxCephRelProperties = ProxmoxCephRelProperties()


@dataclass(frozen=True)
class ProxmoxStorageToCephPoolRel(CartographyRelSchema):
    """The Proxmox VE RBD or CephFS storage keeps its data in the Ceph pool."""

    target_node_label: str = "ProxmoxStorage"
    target_node_matcher: TargetNodeMatcher = make_target_node_matcher(
        {"id": PropertyRef("storage_ids", one_to_many=True)},
    )
    direction: LinkDirection = LinkDirection.INWARD
    rel_label: str = "USES_CEPH_POOL"
    properties: ProxmoxCephRelProperties = ProxmoxCephRelProperties()


@dataclass(frozen=True)
class ProxmoxCephPoolNodeProperties(CartographyNodeProperties):
    id: PropertyRef = PropertyRef(
        "id",
        description="Pool ID in the form cluster_id/pool:name.",
    )
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)
    name: PropertyRef = PropertyRef(
        "name",
        extra_index=True,
        description="Pool name.",
    )
    cluster_id: PropertyRef = PropertyRef(
        "cluster_id",
        description="ID of the Proxmox VE cluster that runs the Ceph cluster.",
    )
    pool_id: PropertyRef = PropertyRef(
        "pool_id", description="Numeric pool ID assigned by Ceph."
    )
    type: PropertyRef = PropertyRef(
        "type",
        description="Pool type: replicated, erasure, or unknown.",
    )
    size: PropertyRef = PropertyRef(
        "size", description="Number of replicas Ceph keeps of each object."
    )
    min_size: PropertyRef = PropertyRef(
        "min_size",
        description="Minimum number of replicas needed to accept writes.",
    )
    pg_num: PropertyRef = PropertyRef(
        "pg_num", description="Current number of placement groups."
    )
    pg_autoscale_mode: PropertyRef = PropertyRef(
        "pg_autoscale_mode",
        description="Placement group autoscaler mode: on, warn, or off.",
    )
    crush_rule: PropertyRef = PropertyRef(
        "crush_rule", description="Numeric ID of the CRUSH rule the pool uses."
    )
    crush_rule_name: PropertyRef = PropertyRef(
        "crush_rule_name", description="Name of the CRUSH rule the pool uses."
    )
    applications: PropertyRef = PropertyRef(
        "applications",
        description="Applications enabled on the pool, such as rbd, cephfs, or rgw.",
    )
    bytes_used: PropertyRef = PropertyRef(
        "bytes_used", description="Bytes currently stored in the pool."
    )
    percent_used: PropertyRef = PropertyRef(
        "percent_used", description="Share of the pool capacity in use."
    )
    nodelete: PropertyRef = PropertyRef(
        "nodelete",
        description="Whether the pool is protected against deletion.",
    )
    nosizechange: PropertyRef = PropertyRef(
        "nosizechange",
        description="Whether changes to the pool size are blocked.",
    )
    nopgchange: PropertyRef = PropertyRef(
        "nopgchange",
        description="Whether changes to the placement group count are blocked.",
    )
    noscrub: PropertyRef = PropertyRef(
        "noscrub", description="Whether scrubbing is disabled for the pool."
    )
    nodeep_scrub: PropertyRef = PropertyRef(
        "nodeep_scrub",
        description="Whether deep scrubbing is disabled for the pool.",
    )


@dataclass(frozen=True)
class ProxmoxCephPoolSchema(CartographyNodeSchema):
    """A Ceph pool, a logical partition that stores objects in a Proxmox VE Ceph cluster."""

    label: str = "ProxmoxCephPool"
    properties: ProxmoxCephPoolNodeProperties = ProxmoxCephPoolNodeProperties()
    sub_resource_relationship: ProxmoxCephToClusterRel = ProxmoxCephToClusterRel()
    other_relationships: OtherRelationships = OtherRelationships(
        [
            ProxmoxCephToCephClusterRel(),
            ProxmoxCephPoolToCrushRuleRel(),
            ProxmoxStorageToCephPoolRel(),
        ],
    )


# ============================================================================
# CephFS file systems
# ============================================================================


@dataclass(frozen=True)
class ProxmoxCephFilesystemToPoolRel(CartographyRelSchema):
    """The CephFS file system stores its metadata or data in the Ceph pool."""

    target_node_label: str = "ProxmoxCephPool"
    target_node_matcher: TargetNodeMatcher = make_target_node_matcher(
        {"id": PropertyRef("pool_ids", one_to_many=True)},
    )
    direction: LinkDirection = LinkDirection.OUTWARD
    rel_label: str = "USES_POOL"
    properties: ProxmoxCephRelProperties = ProxmoxCephRelProperties()


@dataclass(frozen=True)
class ProxmoxStorageToCephFilesystemRel(CartographyRelSchema):
    """The Proxmox VE CephFS storage mounts the CephFS file system."""

    target_node_label: str = "ProxmoxStorage"
    target_node_matcher: TargetNodeMatcher = make_target_node_matcher(
        {"id": PropertyRef("storage_ids", one_to_many=True)},
    )
    direction: LinkDirection = LinkDirection.INWARD
    rel_label: str = "USES_CEPH_FILESYSTEM"
    properties: ProxmoxCephRelProperties = ProxmoxCephRelProperties()


@dataclass(frozen=True)
class ProxmoxCephFilesystemNodeProperties(CartographyNodeProperties):
    id: PropertyRef = PropertyRef(
        "id",
        description="File system ID in the form cluster_id/fs:name.",
    )
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)
    name: PropertyRef = PropertyRef(
        "name",
        extra_index=True,
        description="CephFS file system name.",
    )
    cluster_id: PropertyRef = PropertyRef(
        "cluster_id",
        description="ID of the Proxmox VE cluster that runs the Ceph cluster.",
    )
    metadata_pool: PropertyRef = PropertyRef(
        "metadata_pool", description="Name of the pool that holds the metadata."
    )
    data_pools: PropertyRef = PropertyRef(
        "data_pools",
        description="Names of the pools that hold the file data.",
    )


@dataclass(frozen=True)
class ProxmoxCephFilesystemSchema(CartographyNodeSchema):
    """A CephFS file system in a Proxmox VE Ceph cluster."""

    label: str = "ProxmoxCephFilesystem"
    properties: ProxmoxCephFilesystemNodeProperties = (
        ProxmoxCephFilesystemNodeProperties()
    )
    sub_resource_relationship: ProxmoxCephToClusterRel = ProxmoxCephToClusterRel()
    other_relationships: OtherRelationships = OtherRelationships(
        [
            ProxmoxCephToCephClusterRel(),
            ProxmoxCephFilesystemToPoolRel(),
            ProxmoxStorageToCephFilesystemRel(),
        ],
    )
