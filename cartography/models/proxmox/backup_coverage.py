from dataclasses import dataclass

from cartography.models.core.common import PropertyRef
from cartography.models.core.nodes import CartographyNodeProperties
from cartography.models.core.nodes import CartographyNodeSchema
from cartography.models.core.relationships import CartographyRelProperties
from cartography.models.core.relationships import CartographyRelSchema
from cartography.models.core.relationships import LinkDirection
from cartography.models.core.relationships import make_source_node_matcher
from cartography.models.core.relationships import make_target_node_matcher
from cartography.models.core.relationships import OtherRelationships
from cartography.models.core.relationships import SourceNodeMatcher
from cartography.models.core.relationships import TargetNodeMatcher

# ============================================================================
# Backup defaults of a node (/nodes/{node}/vzdump/defaults)
# ============================================================================


@dataclass(frozen=True)
class ProxmoxBackupDefaultsNodeProperties(CartographyNodeProperties):
    id: PropertyRef = PropertyRef(
        "id",
        description="Backup defaults ID in the form cluster_id/node.",
    )
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)
    cluster_id: PropertyRef = PropertyRef(
        "cluster_id",
        description="ID of the cluster the node belongs to.",
    )
    node: PropertyRef = PropertyRef(
        "node",
        extra_index=True,
        description="Name of the node the vzdump defaults apply to.",
    )
    storage: PropertyRef = PropertyRef(
        "storage",
        description="Default storage that backups are written to.",
    )
    mode: PropertyRef = PropertyRef(
        "mode",
        description="Default backup mode: snapshot, suspend, or stop.",
    )
    compress: PropertyRef = PropertyRef(
        "compress",
        description="Default compression of the backup files.",
    )
    bwlimit: PropertyRef = PropertyRef(
        "bwlimit",
        description="Default I/O bandwidth limit in KiB/s.",
    )
    ionice: PropertyRef = PropertyRef(
        "ionice",
        description="Default I/O priority when the BFQ scheduler is used.",
    )
    protected: PropertyRef = PropertyRef(
        "protected",
        description="Whether new backups are marked as protected by default.",
    )
    remove: PropertyRef = PropertyRef(
        "remove",
        description="Whether older backups are pruned according to the retention settings.",
    )
    mailto: PropertyRef = PropertyRef(
        "mailto",
        description="Email addresses or users that receive notifications (deprecated).",
    )
    mailnotification: PropertyRef = PropertyRef(
        "mailnotification",
        description="When to send notification mails (deprecated).",
    )
    notification_mode: PropertyRef = PropertyRef(
        "notification_mode",
        description="Notification system used by vzdump.",
    )
    notes_template: PropertyRef = PropertyRef(
        "notes_template",
        description="Template for the notes of new backups.",
    )
    script: PropertyRef = PropertyRef(
        "script",
        description="Path of the hook script run during backups.",
    )
    tmpdir: PropertyRef = PropertyRef(
        "tmpdir",
        description="Directory for temporary files.",
    )
    dumpdir: PropertyRef = PropertyRef(
        "dumpdir",
        description="Directory backups are written to instead of a storage.",
    )
    exclude_path: PropertyRef = PropertyRef(
        "exclude_path",
        description="Container paths excluded from backups (shell globs).",
    )
    stdexcludes: PropertyRef = PropertyRef(
        "stdexcludes",
        description="Whether temporary files and logs are excluded.",
    )
    fleecing_enabled: PropertyRef = PropertyRef(
        "fleecing_enabled",
        description="Whether backup fleecing is enabled for VMs (enabled key of the fleecing option).",
    )
    fleecing_storage: PropertyRef = PropertyRef(
        "fleecing_storage",
        description="Storage that holds the fleecing images (storage key of the fleecing option).",
    )
    performance_max_workers: PropertyRef = PropertyRef(
        "performance_max_workers",
        description="Maximum number of parallel IO workers for VM backups (max-workers key of the performance option).",
    )
    performance_pbs_entries_max: PropertyRef = PropertyRef(
        "performance_pbs_entries_max",
        description="Maximum number of entries a container backup to Proxmox Backup Server keeps in memory (pbs-entries-max key of the performance option).",
    )
    pbs_change_detection_mode: PropertyRef = PropertyRef(
        "pbs_change_detection_mode",
        description="Proxmox Backup Server change detection mode for container backups.",
    )
    zstd: PropertyRef = PropertyRef(
        "zstd",
        description="Number of zstd threads.",
    )
    pigz: PropertyRef = PropertyRef(
        "pigz",
        description="Number of pigz threads used instead of gzip.",
    )
    lockwait: PropertyRef = PropertyRef(
        "lockwait",
        description="Maximum time in minutes to wait for the global lock.",
    )
    stopwait: PropertyRef = PropertyRef(
        "stopwait",
        description="Maximum time in minutes to wait until a guest is stopped.",
    )
    prune_keep_all: PropertyRef = PropertyRef(
        "prune_keep_all",
        description="Whether all backups are kept, overriding the other retention settings.",
    )
    prune_keep_last: PropertyRef = PropertyRef(
        "prune_keep_last",
        description="Default number of most recent backups to keep.",
    )
    prune_keep_hourly: PropertyRef = PropertyRef(
        "prune_keep_hourly",
        description="Default number of hourly backups to keep.",
    )
    prune_keep_daily: PropertyRef = PropertyRef(
        "prune_keep_daily",
        description="Default number of daily backups to keep.",
    )
    prune_keep_weekly: PropertyRef = PropertyRef(
        "prune_keep_weekly",
        description="Default number of weekly backups to keep.",
    )
    prune_keep_monthly: PropertyRef = PropertyRef(
        "prune_keep_monthly",
        description="Default number of monthly backups to keep.",
    )
    prune_keep_yearly: PropertyRef = PropertyRef(
        "prune_keep_yearly",
        description="Default number of yearly backups to keep.",
    )


@dataclass(frozen=True)
class ProxmoxBackupDefaultsToClusterRelProperties(CartographyRelProperties):
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)


@dataclass(frozen=True)
class ProxmoxBackupDefaultsToClusterRel(CartographyRelSchema):
    """The cluster contains the backup defaults of one of its nodes."""

    target_node_label: str = "ProxmoxCluster"
    target_node_matcher: TargetNodeMatcher = make_target_node_matcher(
        {"id": PropertyRef("CLUSTER_ID", set_in_kwargs=True)},
    )
    direction: LinkDirection = LinkDirection.INWARD
    rel_label: str = "RESOURCE"
    properties: ProxmoxBackupDefaultsToClusterRelProperties = (
        ProxmoxBackupDefaultsToClusterRelProperties()
    )


@dataclass(frozen=True)
class ProxmoxBackupDefaultsToNodeRelProperties(CartographyRelProperties):
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)


@dataclass(frozen=True)
class ProxmoxBackupDefaultsToNodeRel(CartographyRelSchema):
    """The node uses these vzdump defaults for backups that do not override them."""

    target_node_label: str = "ProxmoxNode"
    target_node_matcher: TargetNodeMatcher = make_target_node_matcher(
        {"id": PropertyRef("node_id")},
    )
    direction: LinkDirection = LinkDirection.INWARD
    rel_label: str = "HAS_BACKUP_DEFAULTS"
    properties: ProxmoxBackupDefaultsToNodeRelProperties = (
        ProxmoxBackupDefaultsToNodeRelProperties()
    )


@dataclass(frozen=True)
class ProxmoxBackupDefaultsToStorageRelProperties(CartographyRelProperties):
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)


@dataclass(frozen=True)
class ProxmoxBackupDefaultsToStorageRel(CartographyRelSchema):
    """Backups that use the node defaults are written to the storage."""

    target_node_label: str = "ProxmoxStorage"
    target_node_matcher: TargetNodeMatcher = make_target_node_matcher(
        {"id": PropertyRef("storage_id")},
    )
    direction: LinkDirection = LinkDirection.OUTWARD
    rel_label: str = "BACKS_UP_TO"
    properties: ProxmoxBackupDefaultsToStorageRelProperties = (
        ProxmoxBackupDefaultsToStorageRelProperties()
    )


@dataclass(frozen=True)
class ProxmoxBackupDefaultsSchema(CartographyNodeSchema):
    """The vzdump backup defaults of a Proxmox VE node, from /etc/vzdump.conf."""

    label: str = "ProxmoxBackupDefaults"
    properties: ProxmoxBackupDefaultsNodeProperties = (
        ProxmoxBackupDefaultsNodeProperties()
    )
    sub_resource_relationship: ProxmoxBackupDefaultsToClusterRel = (
        ProxmoxBackupDefaultsToClusterRel()
    )
    other_relationships: OtherRelationships = OtherRelationships(
        [
            ProxmoxBackupDefaultsToNodeRel(),
            ProxmoxBackupDefaultsToStorageRel(),
        ],
    )


# ============================================================================
# Backup coverage flag on guests (/cluster/backup-info/not-backed-up)
# ============================================================================


@dataclass(frozen=True)
class ProxmoxVMBackupCoverageNodeProperties(CartographyNodeProperties):
    id: PropertyRef = PropertyRef(
        "id",
        description="Guest ID in the form cluster_id/node/type/vmid.",
    )
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)
    backup_covered: PropertyRef = PropertyRef(
        "backup_covered",
        description=(
            "Whether at least one backup job covers the guest. False when Proxmox "
            "lists the guest as not backed up."
        ),
    )


@dataclass(frozen=True)
class ProxmoxVMBackupCoverageToClusterRelProperties(CartographyRelProperties):
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)


@dataclass(frozen=True)
class ProxmoxVMBackupCoverageToClusterRel(CartographyRelSchema):
    """The cluster contains the guest."""

    target_node_label: str = "ProxmoxCluster"
    target_node_matcher: TargetNodeMatcher = make_target_node_matcher(
        {"id": PropertyRef("CLUSTER_ID", set_in_kwargs=True)},
    )
    direction: LinkDirection = LinkDirection.INWARD
    rel_label: str = "RESOURCE"
    properties: ProxmoxVMBackupCoverageToClusterRelProperties = (
        ProxmoxVMBackupCoverageToClusterRelProperties()
    )


@dataclass(frozen=True)
class ProxmoxVMBackupCoverageSchema(CartographyNodeSchema):
    """The backup coverage of a Proxmox guest, written onto the existing ProxmoxVM node."""

    label: str = "ProxmoxVM"
    properties: ProxmoxVMBackupCoverageNodeProperties = (
        ProxmoxVMBackupCoverageNodeProperties()
    )
    sub_resource_relationship: ProxmoxVMBackupCoverageToClusterRel = (
        ProxmoxVMBackupCoverageToClusterRel()
    )


# ============================================================================
# Guests and volumes a backup job includes (/cluster/backup/{id}/included_volumes)
# ============================================================================


@dataclass(frozen=True)
class ProxmoxBackupJobCoverageRelProperties(CartographyRelProperties):
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)
    _sub_resource_label: PropertyRef = PropertyRef(
        "_sub_resource_label",
        set_in_kwargs=True,
    )
    _sub_resource_id: PropertyRef = PropertyRef("_sub_resource_id", set_in_kwargs=True)


@dataclass(frozen=True)
class ProxmoxBackupJobCoversVMMatchLink(CartographyRelSchema):
    """
    The backup job selects the guest when it runs, whether the job lists the
    guest explicitly, selects all guests, or selects a pool.
    """

    source_node_label: str = "ProxmoxBackupJob"
    source_node_matcher: SourceNodeMatcher = make_source_node_matcher(
        {"id": PropertyRef("job_id")},
    )
    target_node_label: str = "ProxmoxVM"
    target_node_matcher: TargetNodeMatcher = make_target_node_matcher(
        {
            "vmid": PropertyRef("vmid"),
            "cluster_id": PropertyRef("cluster_id"),
        },
    )
    direction: LinkDirection = LinkDirection.OUTWARD
    rel_label: str = "COVERS"
    properties: ProxmoxBackupJobCoverageRelProperties = (
        ProxmoxBackupJobCoverageRelProperties()
    )


@dataclass(frozen=True)
class ProxmoxBackupJobIncludesDiskMatchLink(CartographyRelSchema):
    """The backup job includes the guest disk in its backups."""

    source_node_label: str = "ProxmoxBackupJob"
    source_node_matcher: SourceNodeMatcher = make_source_node_matcher(
        {"id": PropertyRef("job_id")},
    )
    target_node_label: str = "ProxmoxDisk"
    target_node_matcher: TargetNodeMatcher = make_target_node_matcher(
        {
            "vmid": PropertyRef("vmid"),
            "disk_id": PropertyRef("disk_id"),
            "cluster_id": PropertyRef("cluster_id"),
        },
    )
    direction: LinkDirection = LinkDirection.OUTWARD
    rel_label: str = "INCLUDES_DISK"
    properties: ProxmoxBackupJobCoverageRelProperties = (
        ProxmoxBackupJobCoverageRelProperties()
    )
