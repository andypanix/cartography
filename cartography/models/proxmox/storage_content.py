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
# Backup archives (storage content type "backup")
# ============================================================================


@dataclass(frozen=True)
class ProxmoxBackupArchiveNodeProperties(CartographyNodeProperties):
    id: PropertyRef = PropertyRef(
        "id",
        description=(
            "Backup archive ID in the form cluster_id/volid on shared storage, or "
            "cluster_id/node/volid on storage local to one node."
        ),
    )
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)
    cluster_id: PropertyRef = PropertyRef(
        "cluster_id",
        description="ID of the cluster the storage belongs to.",
    )
    volid: PropertyRef = PropertyRef(
        "volid",
        extra_index=True,
        description="Proxmox volume identifier of the archive, such as local:backup/vzdump-qemu-100-....vma.zst.",
    )
    storage: PropertyRef = PropertyRef(
        "storage",
        description="Name of the storage that holds the archive.",
    )
    node: PropertyRef = PropertyRef(
        "node",
        description="Node whose local storage holds the archive. Empty for shared storage.",
    )
    vmid: PropertyRef = PropertyRef(
        "vmid",
        extra_index=True,
        description="VM ID of the guest the archive backs up.",
    )
    format: PropertyRef = PropertyRef(
        "format",
        description="Archive format identifier, such as vma.zst, tar.zst, or pbs-vm.",
    )
    size: PropertyRef = PropertyRef(
        "size",
        description="Archive size in bytes, or the approximate size when the storage cannot report the exact one.",
    )
    ctime: PropertyRef = PropertyRef(
        "ctime",
        description="Creation time of the archive, in seconds since the UNIX epoch.",
    )
    last_listed: PropertyRef = PropertyRef(
        "last_listed",
        description="When the archive was last seen in a storage content listing, in seconds since the UNIX epoch. Content of a storage that was not read in a sync is kept with this value unchanged.",
    )
    notes: PropertyRef = PropertyRef(
        "notes",
        description="First line of the archive notes.",
    )
    protected: PropertyRef = PropertyRef(
        "protected",
        description="Whether the archive is protected from pruning and removal.",
    )
    encrypted: PropertyRef = PropertyRef(
        "encrypted",
        description="Whether the whole archive is encrypted. Only reported by Proxmox Backup Server storage.",
    )
    encryption_key_fingerprint: PropertyRef = PropertyRef(
        "encryption_key_fingerprint",
        description="Fingerprint of the encryption key, when the storage reports it.",
    )
    verification_state: PropertyRef = PropertyRef(
        "verification_state",
        description="State of the last verification, such as ok or failed. Only reported by Proxmox Backup Server storage.",
    )


@dataclass(frozen=True)
class ProxmoxBackupArchiveToClusterRelProperties(CartographyRelProperties):
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)


@dataclass(frozen=True)
class ProxmoxBackupArchiveToClusterRel(CartographyRelSchema):
    """The cluster contains the backup archive."""

    target_node_label: str = "ProxmoxCluster"
    target_node_matcher: TargetNodeMatcher = make_target_node_matcher(
        {"id": PropertyRef("CLUSTER_ID", set_in_kwargs=True)},
    )
    direction: LinkDirection = LinkDirection.INWARD
    rel_label: str = "RESOURCE"
    properties: ProxmoxBackupArchiveToClusterRelProperties = (
        ProxmoxBackupArchiveToClusterRelProperties()
    )


@dataclass(frozen=True)
class ProxmoxBackupArchiveToStorageRelProperties(CartographyRelProperties):
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)


@dataclass(frozen=True)
class ProxmoxBackupArchiveToStorageRel(CartographyRelSchema):
    """The backup archive is stored on the storage."""

    target_node_label: str = "ProxmoxStorage"
    target_node_matcher: TargetNodeMatcher = make_target_node_matcher(
        {"id": PropertyRef("storage_id")},
    )
    direction: LinkDirection = LinkDirection.OUTWARD
    rel_label: str = "STORED_ON"
    properties: ProxmoxBackupArchiveToStorageRelProperties = (
        ProxmoxBackupArchiveToStorageRelProperties()
    )


@dataclass(frozen=True)
class ProxmoxBackupArchiveToVMRelProperties(CartographyRelProperties):
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)


@dataclass(frozen=True)
class ProxmoxBackupArchiveToVMRel(CartographyRelSchema):
    """
    The backup archive holds a backup of the guest with the same VM ID in the
    same cluster.
    """

    target_node_label: str = "ProxmoxVM"
    target_node_matcher: TargetNodeMatcher = make_target_node_matcher(
        {
            "vmid": PropertyRef("vmid"),
            "cluster_id": PropertyRef("CLUSTER_ID", set_in_kwargs=True),
        },
    )
    direction: LinkDirection = LinkDirection.OUTWARD
    rel_label: str = "BACKUP_OF"
    properties: ProxmoxBackupArchiveToVMRelProperties = (
        ProxmoxBackupArchiveToVMRelProperties()
    )


@dataclass(frozen=True)
class ProxmoxBackupArchiveSchema(CartographyNodeSchema):
    """A guest backup archive stored on a Proxmox VE storage."""

    label: str = "ProxmoxBackupArchive"
    properties: ProxmoxBackupArchiveNodeProperties = (
        ProxmoxBackupArchiveNodeProperties()
    )
    sub_resource_relationship: ProxmoxBackupArchiveToClusterRel = (
        ProxmoxBackupArchiveToClusterRel()
    )
    other_relationships: OtherRelationships = OtherRelationships(
        [
            ProxmoxBackupArchiveToStorageRel(),
            ProxmoxBackupArchiveToVMRel(),
        ],
    )


# ============================================================================
# ISO images and container templates (storage content types "iso" and "vztmpl")
# ============================================================================


@dataclass(frozen=True)
class ProxmoxStorageTemplateNodeProperties(CartographyNodeProperties):
    id: PropertyRef = PropertyRef(
        "id",
        description=(
            "Template ID in the form cluster_id/volid on shared storage, or "
            "cluster_id/node/volid on storage local to one node."
        ),
    )
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)
    cluster_id: PropertyRef = PropertyRef(
        "cluster_id",
        description="ID of the cluster the storage belongs to.",
    )
    volid: PropertyRef = PropertyRef(
        "volid",
        extra_index=True,
        description="Proxmox volume identifier, such as local:iso/debian-12.iso.",
    )
    content: PropertyRef = PropertyRef(
        "content",
        description="Content type: iso for ISO images or vztmpl for container templates.",
    )
    storage: PropertyRef = PropertyRef(
        "storage",
        description="Name of the storage that holds the file.",
    )
    node: PropertyRef = PropertyRef(
        "node",
        description="Node whose local storage holds the file. Empty for shared storage.",
    )
    format: PropertyRef = PropertyRef(
        "format",
        description="File format identifier, such as iso or tzst.",
    )
    size: PropertyRef = PropertyRef(
        "size",
        description="File size in bytes.",
    )
    ctime: PropertyRef = PropertyRef(
        "ctime",
        description="Creation time of the file, in seconds since the UNIX epoch.",
    )
    last_listed: PropertyRef = PropertyRef(
        "last_listed",
        description="When the file was last seen in a storage content listing, in seconds since the UNIX epoch. Content of a storage that was not read in a sync is kept with this value unchanged.",
    )


@dataclass(frozen=True)
class ProxmoxStorageTemplateToClusterRelProperties(CartographyRelProperties):
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)


@dataclass(frozen=True)
class ProxmoxStorageTemplateToClusterRel(CartographyRelSchema):
    """The cluster contains the ISO image or container template."""

    target_node_label: str = "ProxmoxCluster"
    target_node_matcher: TargetNodeMatcher = make_target_node_matcher(
        {"id": PropertyRef("CLUSTER_ID", set_in_kwargs=True)},
    )
    direction: LinkDirection = LinkDirection.INWARD
    rel_label: str = "RESOURCE"
    properties: ProxmoxStorageTemplateToClusterRelProperties = (
        ProxmoxStorageTemplateToClusterRelProperties()
    )


@dataclass(frozen=True)
class ProxmoxStorageTemplateToStorageRelProperties(CartographyRelProperties):
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)


@dataclass(frozen=True)
class ProxmoxStorageTemplateToStorageRel(CartographyRelSchema):
    """The ISO image or container template is stored on the storage."""

    target_node_label: str = "ProxmoxStorage"
    target_node_matcher: TargetNodeMatcher = make_target_node_matcher(
        {"id": PropertyRef("storage_id")},
    )
    direction: LinkDirection = LinkDirection.OUTWARD
    rel_label: str = "STORED_ON"
    properties: ProxmoxStorageTemplateToStorageRelProperties = (
        ProxmoxStorageTemplateToStorageRelProperties()
    )


@dataclass(frozen=True)
class ProxmoxStorageTemplateSchema(CartographyNodeSchema):
    """An ISO image or LXC container template stored on a Proxmox VE storage."""

    label: str = "ProxmoxStorageTemplate"
    properties: ProxmoxStorageTemplateNodeProperties = (
        ProxmoxStorageTemplateNodeProperties()
    )
    sub_resource_relationship: ProxmoxStorageTemplateToClusterRel = (
        ProxmoxStorageTemplateToClusterRel()
    )
    other_relationships: OtherRelationships = OtherRelationships(
        [ProxmoxStorageTemplateToStorageRel()],
    )
