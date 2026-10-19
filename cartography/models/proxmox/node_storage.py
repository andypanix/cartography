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


@dataclass(frozen=True)
class ProxmoxNodeStorageRelProperties(CartographyRelProperties):
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)


# ============================================================================
# ProxmoxPhysicalDisk
# ============================================================================


@dataclass(frozen=True)
class ProxmoxPhysicalDiskNodeProperties(CartographyNodeProperties):
    id: PropertyRef = PropertyRef(
        "id",
        description="Disk ID in the form cluster_id/node_name:devpath.",
    )
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)
    cluster_id: PropertyRef = PropertyRef(
        "cluster_id",
        description="ID of the Proxmox cluster the disk belongs to.",
    )
    node_name: PropertyRef = PropertyRef(
        "node_name",
        description="Name of the Proxmox node the disk is attached to.",
    )
    devpath: PropertyRef = PropertyRef(
        "devpath",
        extra_index=True,
        description="Device path of the disk, such as /dev/sda.",
    )
    name: PropertyRef = PropertyRef(
        "name",
        extra_index=True,
        description=(
            "Kernel device name of the disk, the device path without /dev/, "
            "such as sda or nvme0n1."
        ),
    )
    model: PropertyRef = PropertyRef("model", description="Disk model.")
    vendor: PropertyRef = PropertyRef("vendor", description="Disk vendor.")
    serial: PropertyRef = PropertyRef(
        "serial",
        extra_index=True,
        description="Disk serial number.",
    )
    wwn: PropertyRef = PropertyRef(
        "wwn",
        extra_index=True,
        description="World Wide Name of the disk.",
    )
    size: PropertyRef = PropertyRef("size", description="Disk size in bytes.")
    type: PropertyRef = PropertyRef(
        "type",
        description="Disk type reported by Proxmox, such as hdd, ssd, nvme or usb.",
    )
    health: PropertyRef = PropertyRef(
        "health",
        description="SMART health status reported by the disk list, such as PASSED or OK.",
    )
    used: PropertyRef = PropertyRef(
        "used",
        description="What uses the disk, such as LVM, ZFS, mounted or partitions.",
    )
    gpt: PropertyRef = PropertyRef(
        "gpt",
        description="Whether the disk has a GPT partition table.",
    )
    mounted: PropertyRef = PropertyRef(
        "mounted",
        description="Whether the disk is mounted.",
    )
    osdid: PropertyRef = PropertyRef(
        "osdid",
        description="ID of the Ceph OSD on the disk, or -1 when there is none.",
    )
    osdid_list: PropertyRef = PropertyRef(
        "osdid_list",
        description="IDs of the Ceph OSDs on the disk.",
    )
    smart_type: PropertyRef = PropertyRef(
        "smart_type",
        description="Format of the SMART data: ata for an attribute table, text for NVMe and SAS disks.",
    )
    smart_health: PropertyRef = PropertyRef(
        "smart_health",
        description="SMART overall health self-assessment, such as PASSED.",
    )
    power_on_hours: PropertyRef = PropertyRef(
        "power_on_hours",
        description="Power-on hours reported by SMART.",
    )
    percentage_used: PropertyRef = PropertyRef(
        "percentage_used",
        description=(
            "Estimated share of the SSD endurance used, in percent: the NVMe "
            "Percentage Used value, or 100 minus the normalized value of the "
            "ATA wear attribute."
        ),
    )
    reallocated_sectors: PropertyRef = PropertyRef(
        "reallocated_sectors",
        description="Raw value of the SMART reallocated sector count.",
    )
    temperature: PropertyRef = PropertyRef(
        "temperature",
        description="Disk temperature in degrees Celsius reported by SMART.",
    )


@dataclass(frozen=True)
class ProxmoxPhysicalDiskToClusterRel(CartographyRelSchema):
    """The cluster contains the physical disk."""

    target_node_label: str = "ProxmoxCluster"
    target_node_matcher: TargetNodeMatcher = make_target_node_matcher(
        {"id": PropertyRef("CLUSTER_ID", set_in_kwargs=True)},
    )
    direction: LinkDirection = LinkDirection.INWARD
    rel_label: str = "RESOURCE"
    properties: ProxmoxNodeStorageRelProperties = ProxmoxNodeStorageRelProperties()


@dataclass(frozen=True)
class ProxmoxPhysicalDiskToNodeRel(CartographyRelSchema):
    """The Proxmox node has the physical disk attached."""

    target_node_label: str = "ProxmoxNode"
    target_node_matcher: TargetNodeMatcher = make_target_node_matcher(
        {"id": PropertyRef("node_id")},
    )
    direction: LinkDirection = LinkDirection.INWARD
    rel_label: str = "HAS_PHYSICAL_DISK"
    properties: ProxmoxNodeStorageRelProperties = ProxmoxNodeStorageRelProperties()


@dataclass(frozen=True)
class ProxmoxPhysicalDiskSchema(CartographyNodeSchema):
    """A local block device of a Proxmox VE node, with its SMART health."""

    label: str = "ProxmoxPhysicalDisk"
    properties: ProxmoxPhysicalDiskNodeProperties = ProxmoxPhysicalDiskNodeProperties()
    sub_resource_relationship: ProxmoxPhysicalDiskToClusterRel = (
        ProxmoxPhysicalDiskToClusterRel()
    )
    other_relationships: OtherRelationships = OtherRelationships(
        [ProxmoxPhysicalDiskToNodeRel()],
    )


# ============================================================================
# ProxmoxZFSPool
# ============================================================================


@dataclass(frozen=True)
class ProxmoxZFSPoolNodeProperties(CartographyNodeProperties):
    id: PropertyRef = PropertyRef(
        "id",
        description="Pool ID in the form cluster_id/node_name:zfs:pool_name.",
    )
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)
    cluster_id: PropertyRef = PropertyRef(
        "cluster_id",
        description="ID of the Proxmox cluster the pool belongs to.",
    )
    node_name: PropertyRef = PropertyRef(
        "node_name",
        description="Name of the Proxmox node that imports the pool.",
    )
    name: PropertyRef = PropertyRef(
        "name",
        extra_index=True,
        description="ZFS pool name.",
    )
    size: PropertyRef = PropertyRef("size", description="Pool size in bytes.")
    alloc: PropertyRef = PropertyRef(
        "alloc",
        description="Allocated space in bytes.",
    )
    free: PropertyRef = PropertyRef("free", description="Free space in bytes.")
    frag: PropertyRef = PropertyRef(
        "frag",
        description="Fragmentation of the free space in percent.",
    )
    dedup: PropertyRef = PropertyRef(
        "dedup",
        description="Deduplication ratio.",
    )
    health: PropertyRef = PropertyRef(
        "health",
        description="Pool health from the pool list, such as ONLINE or DEGRADED.",
    )
    state: PropertyRef = PropertyRef(
        "state",
        description="Pool state from the pool details, such as ONLINE or DEGRADED.",
    )
    status: PropertyRef = PropertyRef(
        "status",
        description="Explanation of the pool state, when ZFS reports one.",
    )
    action: PropertyRef = PropertyRef(
        "action",
        description="Recommended action to fix the pool state, when ZFS reports one.",
    )
    scan: PropertyRef = PropertyRef(
        "scan",
        description="Result of the last or current scrub or resilver.",
    )
    errors: PropertyRef = PropertyRef(
        "errors",
        description="Data error summary of the pool, such as No known data errors.",
    )
    member_devices: PropertyRef = PropertyRef(
        "member_devices",
        description="Names of the leaf devices of the pool, as ZFS reports them.",
    )
    degraded_devices: PropertyRef = PropertyRef(
        "degraded_devices",
        description="Names of the leaf devices whose state is not ONLINE.",
    )


@dataclass(frozen=True)
class ProxmoxZFSPoolToClusterRel(CartographyRelSchema):
    """The cluster contains the ZFS pool."""

    target_node_label: str = "ProxmoxCluster"
    target_node_matcher: TargetNodeMatcher = make_target_node_matcher(
        {"id": PropertyRef("CLUSTER_ID", set_in_kwargs=True)},
    )
    direction: LinkDirection = LinkDirection.INWARD
    rel_label: str = "RESOURCE"
    properties: ProxmoxNodeStorageRelProperties = ProxmoxNodeStorageRelProperties()


@dataclass(frozen=True)
class ProxmoxZFSPoolToNodeRel(CartographyRelSchema):
    """The Proxmox node imports the ZFS pool."""

    target_node_label: str = "ProxmoxNode"
    target_node_matcher: TargetNodeMatcher = make_target_node_matcher(
        {"id": PropertyRef("node_id")},
    )
    direction: LinkDirection = LinkDirection.INWARD
    rel_label: str = "HAS_ZFS_POOL"
    properties: ProxmoxNodeStorageRelProperties = ProxmoxNodeStorageRelProperties()


@dataclass(frozen=True)
class ProxmoxZFSPoolToDiskRel(CartographyRelSchema):
    """The ZFS pool stores data on the physical disk, or on one of its partitions."""

    target_node_label: str = "ProxmoxPhysicalDisk"
    target_node_matcher: TargetNodeMatcher = make_target_node_matcher(
        {"id": PropertyRef("disk_ids", one_to_many=True)},
    )
    direction: LinkDirection = LinkDirection.OUTWARD
    rel_label: str = "USES_DISK"
    properties: ProxmoxNodeStorageRelProperties = ProxmoxNodeStorageRelProperties()


@dataclass(frozen=True)
class ProxmoxZFSPoolSchema(CartographyNodeSchema):
    """A ZFS pool imported on a Proxmox VE node."""

    label: str = "ProxmoxZFSPool"
    properties: ProxmoxZFSPoolNodeProperties = ProxmoxZFSPoolNodeProperties()
    sub_resource_relationship: ProxmoxZFSPoolToClusterRel = ProxmoxZFSPoolToClusterRel()
    other_relationships: OtherRelationships = OtherRelationships(
        [ProxmoxZFSPoolToNodeRel(), ProxmoxZFSPoolToDiskRel()],
    )


# ============================================================================
# ProxmoxLVMVolumeGroup
# ============================================================================


@dataclass(frozen=True)
class ProxmoxLVMVolumeGroupNodeProperties(CartographyNodeProperties):
    id: PropertyRef = PropertyRef(
        "id",
        description="Volume group ID in the form cluster_id/node_name:lvm:vg_name.",
    )
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)
    cluster_id: PropertyRef = PropertyRef(
        "cluster_id",
        description="ID of the Proxmox cluster the volume group belongs to.",
    )
    node_name: PropertyRef = PropertyRef(
        "node_name",
        description="Name of the Proxmox node the volume group is on.",
    )
    name: PropertyRef = PropertyRef(
        "name",
        extra_index=True,
        description="Volume group name.",
    )
    size: PropertyRef = PropertyRef(
        "size",
        description="Volume group size in bytes.",
    )
    free: PropertyRef = PropertyRef(
        "free",
        description="Free bytes in the volume group.",
    )
    physical_volumes: PropertyRef = PropertyRef(
        "physical_volumes",
        description="Device paths of the physical volumes of the volume group.",
    )


@dataclass(frozen=True)
class ProxmoxLVMVolumeGroupToClusterRel(CartographyRelSchema):
    """The cluster contains the LVM volume group."""

    target_node_label: str = "ProxmoxCluster"
    target_node_matcher: TargetNodeMatcher = make_target_node_matcher(
        {"id": PropertyRef("CLUSTER_ID", set_in_kwargs=True)},
    )
    direction: LinkDirection = LinkDirection.INWARD
    rel_label: str = "RESOURCE"
    properties: ProxmoxNodeStorageRelProperties = ProxmoxNodeStorageRelProperties()


@dataclass(frozen=True)
class ProxmoxLVMVolumeGroupToNodeRel(CartographyRelSchema):
    """The Proxmox node has the LVM volume group."""

    target_node_label: str = "ProxmoxNode"
    target_node_matcher: TargetNodeMatcher = make_target_node_matcher(
        {"id": PropertyRef("node_id")},
    )
    direction: LinkDirection = LinkDirection.INWARD
    rel_label: str = "HAS_LVM_VOLUME_GROUP"
    properties: ProxmoxNodeStorageRelProperties = ProxmoxNodeStorageRelProperties()


@dataclass(frozen=True)
class ProxmoxLVMVolumeGroupToDiskRel(CartographyRelSchema):
    """A physical volume of the volume group is the disk, or one of its partitions."""

    target_node_label: str = "ProxmoxPhysicalDisk"
    target_node_matcher: TargetNodeMatcher = make_target_node_matcher(
        {"id": PropertyRef("disk_ids", one_to_many=True)},
    )
    direction: LinkDirection = LinkDirection.OUTWARD
    rel_label: str = "USES_DISK"
    properties: ProxmoxNodeStorageRelProperties = ProxmoxNodeStorageRelProperties()


@dataclass(frozen=True)
class ProxmoxLVMVolumeGroupSchema(CartographyNodeSchema):
    """An LVM volume group on a Proxmox VE node."""

    label: str = "ProxmoxLVMVolumeGroup"
    properties: ProxmoxLVMVolumeGroupNodeProperties = (
        ProxmoxLVMVolumeGroupNodeProperties()
    )
    sub_resource_relationship: ProxmoxLVMVolumeGroupToClusterRel = (
        ProxmoxLVMVolumeGroupToClusterRel()
    )
    other_relationships: OtherRelationships = OtherRelationships(
        [ProxmoxLVMVolumeGroupToNodeRel(), ProxmoxLVMVolumeGroupToDiskRel()],
    )


# ============================================================================
# ProxmoxLVMThinPool
# ============================================================================


@dataclass(frozen=True)
class ProxmoxLVMThinPoolNodeProperties(CartographyNodeProperties):
    id: PropertyRef = PropertyRef(
        "id",
        description="Thin pool ID in the form cluster_id/node_name:lvmthin:vg_name/lv_name.",
    )
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)
    cluster_id: PropertyRef = PropertyRef(
        "cluster_id",
        description="ID of the Proxmox cluster the thin pool belongs to.",
    )
    node_name: PropertyRef = PropertyRef(
        "node_name",
        description="Name of the Proxmox node the thin pool is on.",
    )
    name: PropertyRef = PropertyRef(
        "name",
        extra_index=True,
        description="Logical volume name of the thin pool.",
    )
    volume_group: PropertyRef = PropertyRef(
        "volume_group",
        description="Name of the volume group that contains the thin pool.",
    )
    lv_size: PropertyRef = PropertyRef(
        "lv_size",
        description="Thin pool size in bytes.",
    )
    used: PropertyRef = PropertyRef(
        "used",
        description="Used bytes of the thin pool.",
    )
    metadata_size: PropertyRef = PropertyRef(
        "metadata_size",
        description="Size of the metadata volume in bytes.",
    )
    metadata_used: PropertyRef = PropertyRef(
        "metadata_used",
        description="Used bytes of the metadata volume.",
    )


@dataclass(frozen=True)
class ProxmoxLVMThinPoolToClusterRel(CartographyRelSchema):
    """The cluster contains the LVM thin pool."""

    target_node_label: str = "ProxmoxCluster"
    target_node_matcher: TargetNodeMatcher = make_target_node_matcher(
        {"id": PropertyRef("CLUSTER_ID", set_in_kwargs=True)},
    )
    direction: LinkDirection = LinkDirection.INWARD
    rel_label: str = "RESOURCE"
    properties: ProxmoxNodeStorageRelProperties = ProxmoxNodeStorageRelProperties()


@dataclass(frozen=True)
class ProxmoxLVMThinPoolToNodeRel(CartographyRelSchema):
    """The Proxmox node has the LVM thin pool."""

    target_node_label: str = "ProxmoxNode"
    target_node_matcher: TargetNodeMatcher = make_target_node_matcher(
        {"id": PropertyRef("node_id")},
    )
    direction: LinkDirection = LinkDirection.INWARD
    rel_label: str = "HAS_LVM_THIN_POOL"
    properties: ProxmoxNodeStorageRelProperties = ProxmoxNodeStorageRelProperties()


@dataclass(frozen=True)
class ProxmoxLVMThinPoolToVolumeGroupRel(CartographyRelSchema):
    """The LVM volume group contains the thin pool."""

    target_node_label: str = "ProxmoxLVMVolumeGroup"
    target_node_matcher: TargetNodeMatcher = make_target_node_matcher(
        {"id": PropertyRef("volume_group_id")},
    )
    direction: LinkDirection = LinkDirection.INWARD
    rel_label: str = "CONTAINS_THIN_POOL"
    properties: ProxmoxNodeStorageRelProperties = ProxmoxNodeStorageRelProperties()


@dataclass(frozen=True)
class ProxmoxLVMThinPoolSchema(CartographyNodeSchema):
    """An LVM thin pool on a Proxmox VE node."""

    label: str = "ProxmoxLVMThinPool"
    properties: ProxmoxLVMThinPoolNodeProperties = ProxmoxLVMThinPoolNodeProperties()
    sub_resource_relationship: ProxmoxLVMThinPoolToClusterRel = (
        ProxmoxLVMThinPoolToClusterRel()
    )
    other_relationships: OtherRelationships = OtherRelationships(
        [ProxmoxLVMThinPoolToNodeRel(), ProxmoxLVMThinPoolToVolumeGroupRel()],
    )


# ============================================================================
# ProxmoxManagedDirectory
# ============================================================================


@dataclass(frozen=True)
class ProxmoxManagedDirectoryNodeProperties(CartographyNodeProperties):
    id: PropertyRef = PropertyRef(
        "id",
        description="Directory ID in the form cluster_id/node_name:directory:path.",
    )
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)
    cluster_id: PropertyRef = PropertyRef(
        "cluster_id",
        description="ID of the Proxmox cluster the directory belongs to.",
    )
    node_name: PropertyRef = PropertyRef(
        "node_name",
        description="Name of the Proxmox node that mounts the directory.",
    )
    path: PropertyRef = PropertyRef(
        "path",
        extra_index=True,
        description="Mount path of the directory.",
    )
    device: PropertyRef = PropertyRef(
        "device",
        description="Mounted device.",
    )
    type: PropertyRef = PropertyRef(
        "type",
        description="File system type, such as ext4 or xfs.",
    )
    options: PropertyRef = PropertyRef(
        "options",
        description="Mount options.",
    )
    unitfile: PropertyRef = PropertyRef(
        "unitfile",
        description="Path of the systemd mount unit.",
    )


@dataclass(frozen=True)
class ProxmoxManagedDirectoryToClusterRel(CartographyRelSchema):
    """The cluster contains the managed directory."""

    target_node_label: str = "ProxmoxCluster"
    target_node_matcher: TargetNodeMatcher = make_target_node_matcher(
        {"id": PropertyRef("CLUSTER_ID", set_in_kwargs=True)},
    )
    direction: LinkDirection = LinkDirection.INWARD
    rel_label: str = "RESOURCE"
    properties: ProxmoxNodeStorageRelProperties = ProxmoxNodeStorageRelProperties()


@dataclass(frozen=True)
class ProxmoxManagedDirectoryToNodeRel(CartographyRelSchema):
    """The Proxmox node mounts the managed directory."""

    target_node_label: str = "ProxmoxNode"
    target_node_matcher: TargetNodeMatcher = make_target_node_matcher(
        {"id": PropertyRef("node_id")},
    )
    direction: LinkDirection = LinkDirection.INWARD
    rel_label: str = "HAS_MANAGED_DIRECTORY"
    properties: ProxmoxNodeStorageRelProperties = ProxmoxNodeStorageRelProperties()


@dataclass(frozen=True)
class ProxmoxManagedDirectoryToDiskRel(CartographyRelSchema):
    """The managed directory is on the disk, or on one of its partitions."""

    target_node_label: str = "ProxmoxPhysicalDisk"
    target_node_matcher: TargetNodeMatcher = make_target_node_matcher(
        {"id": PropertyRef("disk_ids", one_to_many=True)},
    )
    direction: LinkDirection = LinkDirection.OUTWARD
    rel_label: str = "USES_DISK"
    properties: ProxmoxNodeStorageRelProperties = ProxmoxNodeStorageRelProperties()


@dataclass(frozen=True)
class ProxmoxManagedDirectorySchema(CartographyNodeSchema):
    """A directory storage mount created and managed by Proxmox VE on a node."""

    label: str = "ProxmoxManagedDirectory"
    properties: ProxmoxManagedDirectoryNodeProperties = (
        ProxmoxManagedDirectoryNodeProperties()
    )
    sub_resource_relationship: ProxmoxManagedDirectoryToClusterRel = (
        ProxmoxManagedDirectoryToClusterRel()
    )
    other_relationships: OtherRelationships = OtherRelationships(
        [ProxmoxManagedDirectoryToNodeRel(), ProxmoxManagedDirectoryToDiskRel()],
    )
