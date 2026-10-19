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
# ProxmoxSnapshot
# ============================================================================


@dataclass(frozen=True)
class ProxmoxSnapshotNodeProperties(CartographyNodeProperties):
    id: PropertyRef = PropertyRef(
        "id",
        description="Snapshot ID in the form cluster_id/node/type/vmid/snapshot/name.",
    )
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)
    name: PropertyRef = PropertyRef(
        "name",
        extra_index=True,
        description="Snapshot name, unique per guest.",
    )
    cluster_id: PropertyRef = PropertyRef(
        "cluster_id",
        description="ID of the cluster the guest belongs to.",
    )
    vmid: PropertyRef = PropertyRef(
        "vmid",
        description="Numeric ID of the guest the snapshot belongs to.",
    )
    description: PropertyRef = PropertyRef(
        "description",
        description="Snapshot description.",
    )
    snaptime: PropertyRef = PropertyRef(
        "snaptime",
        description="Snapshot creation time as a Unix timestamp.",
    )
    vmstate: PropertyRef = PropertyRef(
        "vmstate",
        description="Whether the snapshot includes the VM memory. Always empty for containers.",
    )
    parent: PropertyRef = PropertyRef(
        "parent",
        description="Name of the parent snapshot, if any.",
    )


@dataclass(frozen=True)
class ProxmoxSnapshotToClusterRelProperties(CartographyRelProperties):
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)


@dataclass(frozen=True)
class ProxmoxSnapshotToClusterRel(CartographyRelSchema):
    """The cluster contains the guest snapshot."""

    target_node_label: str = "ProxmoxCluster"
    target_node_matcher: TargetNodeMatcher = make_target_node_matcher(
        {"id": PropertyRef("CLUSTER_ID", set_in_kwargs=True)},
    )
    direction: LinkDirection = LinkDirection.INWARD
    rel_label: str = "RESOURCE"
    properties: ProxmoxSnapshotToClusterRelProperties = (
        ProxmoxSnapshotToClusterRelProperties()
    )


@dataclass(frozen=True)
class ProxmoxSnapshotToVMRelProperties(CartographyRelProperties):
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)


@dataclass(frozen=True)
class ProxmoxSnapshotToVMRel(CartographyRelSchema):
    """The guest has the snapshot."""

    target_node_label: str = "ProxmoxVM"
    target_node_matcher: TargetNodeMatcher = make_target_node_matcher(
        {"id": PropertyRef("vm_id")},
    )
    direction: LinkDirection = LinkDirection.INWARD
    rel_label: str = "HAS_SNAPSHOT"
    properties: ProxmoxSnapshotToVMRelProperties = ProxmoxSnapshotToVMRelProperties()


@dataclass(frozen=True)
class ProxmoxSnapshotToParentRelProperties(CartographyRelProperties):
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)


@dataclass(frozen=True)
class ProxmoxSnapshotToParentRel(CartographyRelSchema):
    """The snapshot was taken after its parent snapshot of the same guest."""

    target_node_label: str = "ProxmoxSnapshot"
    target_node_matcher: TargetNodeMatcher = make_target_node_matcher(
        {"id": PropertyRef("parent_id")},
    )
    direction: LinkDirection = LinkDirection.OUTWARD
    rel_label: str = "HAS_PARENT"
    properties: ProxmoxSnapshotToParentRelProperties = (
        ProxmoxSnapshotToParentRelProperties()
    )


@dataclass(frozen=True)
class ProxmoxSnapshotSchema(CartographyNodeSchema):
    """A snapshot of a QEMU virtual machine or LXC container in a Proxmox VE cluster."""

    label: str = "ProxmoxSnapshot"
    properties: ProxmoxSnapshotNodeProperties = ProxmoxSnapshotNodeProperties()
    sub_resource_relationship: ProxmoxSnapshotToClusterRel = (
        ProxmoxSnapshotToClusterRel()
    )
    other_relationships: OtherRelationships = OtherRelationships(
        [ProxmoxSnapshotToVMRel(), ProxmoxSnapshotToParentRel()],
    )


# ============================================================================
# ProxmoxGuestFilesystem
# ============================================================================


@dataclass(frozen=True)
class ProxmoxGuestFilesystemNodeProperties(CartographyNodeProperties):
    id: PropertyRef = PropertyRef(
        "id",
        description="Filesystem ID in the form cluster_id/node/qemu/vmid:fs:mountpoint.",
    )
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)
    mountpoint: PropertyRef = PropertyRef(
        "mountpoint",
        extra_index=True,
        description="Path where the filesystem is mounted inside the guest.",
    )
    cluster_id: PropertyRef = PropertyRef(
        "cluster_id",
        description="ID of the cluster the VM belongs to.",
    )
    vmid: PropertyRef = PropertyRef(
        "vmid",
        description="Numeric ID of the VM that mounts the filesystem.",
    )
    name: PropertyRef = PropertyRef(
        "name",
        description="Guest device name of the filesystem, such as sda1.",
    )
    type: PropertyRef = PropertyRef(
        "type",
        description="Filesystem type, such as ext4, xfs or NTFS.",
    )
    total_bytes: PropertyRef = PropertyRef(
        "total_bytes",
        description="Filesystem size in bytes, when the guest agent reports it.",
    )
    used_bytes: PropertyRef = PropertyRef(
        "used_bytes",
        description="Used space in bytes, when the guest agent reports it.",
    )
    disk_serials: PropertyRef = PropertyRef(
        "disk_serials",
        description="Serial numbers of the virtual disks backing the filesystem, when the guest agent reports them.",
    )


@dataclass(frozen=True)
class ProxmoxGuestFilesystemToClusterRelProperties(CartographyRelProperties):
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)


@dataclass(frozen=True)
class ProxmoxGuestFilesystemToClusterRel(CartographyRelSchema):
    """The cluster contains the guest filesystem."""

    target_node_label: str = "ProxmoxCluster"
    target_node_matcher: TargetNodeMatcher = make_target_node_matcher(
        {"id": PropertyRef("CLUSTER_ID", set_in_kwargs=True)},
    )
    direction: LinkDirection = LinkDirection.INWARD
    rel_label: str = "RESOURCE"
    properties: ProxmoxGuestFilesystemToClusterRelProperties = (
        ProxmoxGuestFilesystemToClusterRelProperties()
    )


@dataclass(frozen=True)
class ProxmoxGuestFilesystemToVMRelProperties(CartographyRelProperties):
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)


@dataclass(frozen=True)
class ProxmoxGuestFilesystemToVMRel(CartographyRelSchema):
    """The VM has the filesystem mounted, as reported by the QEMU guest agent."""

    target_node_label: str = "ProxmoxVM"
    target_node_matcher: TargetNodeMatcher = make_target_node_matcher(
        {"id": PropertyRef("vm_id")},
    )
    direction: LinkDirection = LinkDirection.INWARD
    rel_label: str = "HAS_FILESYSTEM"
    properties: ProxmoxGuestFilesystemToVMRelProperties = (
        ProxmoxGuestFilesystemToVMRelProperties()
    )


@dataclass(frozen=True)
class ProxmoxGuestFilesystemSchema(CartographyNodeSchema):
    """A filesystem mounted inside a running QEMU virtual machine, reported by its guest agent."""

    label: str = "ProxmoxGuestFilesystem"
    properties: ProxmoxGuestFilesystemNodeProperties = (
        ProxmoxGuestFilesystemNodeProperties()
    )
    sub_resource_relationship: ProxmoxGuestFilesystemToClusterRel = (
        ProxmoxGuestFilesystemToClusterRel()
    )
    other_relationships: OtherRelationships = OtherRelationships(
        [ProxmoxGuestFilesystemToVMRel()],
    )


# ============================================================================
# ProxmoxCustomCPUModel
# ============================================================================


@dataclass(frozen=True)
class ProxmoxCustomCPUModelNodeProperties(CartographyNodeProperties):
    id: PropertyRef = PropertyRef(
        "id",
        description="Custom CPU model ID in the form cluster_id/name.",
    )
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)
    name: PropertyRef = PropertyRef(
        "name",
        extra_index=True,
        description="Model name without the custom- prefix that VM configurations use.",
    )
    cluster_id: PropertyRef = PropertyRef(
        "cluster_id",
        description="ID of the cluster that defines the model.",
    )
    reported_model: PropertyRef = PropertyRef(
        "reported_model",
        description="CPU model and vendor reported to the guest.",
    )
    flags: PropertyRef = PropertyRef(
        "flags",
        description="CPU flags the model enables (+FLAG) or disables (-FLAG), separated by semicolons.",
    )
    hidden: PropertyRef = PropertyRef(
        "hidden",
        description="Whether the vCPU hides that it runs in a KVM virtual machine.",
    )
    phys_bits: PropertyRef = PropertyRef(
        "phys_bits",
        description="Physical address bits reported to the guest, or host to use the host value.",
    )
    guest_phys_bits: PropertyRef = PropertyRef(
        "guest_phys_bits",
        description="Physical address bits available to the guest.",
    )
    hv_vendor_id: PropertyRef = PropertyRef(
        "hv_vendor_id",
        description="Hyper-V vendor ID reported to the guest.",
    )
    level: PropertyRef = PropertyRef(
        "level",
        description="Maximum basic CPUID leaf the guest can query.",
    )


@dataclass(frozen=True)
class ProxmoxCustomCPUModelToClusterRelProperties(CartographyRelProperties):
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)


@dataclass(frozen=True)
class ProxmoxCustomCPUModelToClusterRel(CartographyRelSchema):
    """The cluster defines the custom CPU model."""

    target_node_label: str = "ProxmoxCluster"
    target_node_matcher: TargetNodeMatcher = make_target_node_matcher(
        {"id": PropertyRef("CLUSTER_ID", set_in_kwargs=True)},
    )
    direction: LinkDirection = LinkDirection.INWARD
    rel_label: str = "RESOURCE"
    properties: ProxmoxCustomCPUModelToClusterRelProperties = (
        ProxmoxCustomCPUModelToClusterRelProperties()
    )


@dataclass(frozen=True)
class ProxmoxCustomCPUModelSchema(CartographyNodeSchema):
    """A custom CPU model defined cluster-wide in Proxmox VE 9 that VMs can use as their CPU type."""

    label: str = "ProxmoxCustomCPUModel"
    properties: ProxmoxCustomCPUModelNodeProperties = (
        ProxmoxCustomCPUModelNodeProperties()
    )
    sub_resource_relationship: ProxmoxCustomCPUModelToClusterRel = (
        ProxmoxCustomCPUModelToClusterRel()
    )
