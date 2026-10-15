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
class ProxmoxBackupJobNodeProperties(CartographyNodeProperties):
    id: PropertyRef = PropertyRef(
        "id",
        description="Backup job ID in the form cluster_id/job_id.",
    )
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)
    job_id: PropertyRef = PropertyRef(
        "job_id",
        extra_index=True,
        description="Backup job ID as returned by the Proxmox VE API.",
    )
    cluster_id: PropertyRef = PropertyRef(
        "cluster_id",
        description="ID of the Proxmox cluster the backup job belongs to.",
    )
    schedule: PropertyRef = PropertyRef(
        "schedule",
        description="Calendar event schedule of the backup job.",
    )
    storage: PropertyRef = PropertyRef(
        "storage",
        description="Name of the storage the backups are written to.",
    )
    enabled: PropertyRef = PropertyRef(
        "enabled",
        description="Whether the backup job is enabled.",
    )
    mode: PropertyRef = PropertyRef(
        "mode",
        description="Backup mode: snapshot, suspend, or stop.",
    )
    compression: PropertyRef = PropertyRef(
        "compression",
        description="Compression setting of the backup files.",
    )
    mailnotification: PropertyRef = PropertyRef(
        "mailnotification",
        description="When to send email notifications: always or failure.",
    )
    mailto: PropertyRef = PropertyRef(
        "mailto",
        description="Email addresses that receive notifications.",
    )
    notes: PropertyRef = PropertyRef(
        "notes",
        description="Notes template applied to the created backups.",
    )
    prune_keep_last: PropertyRef = PropertyRef(
        "prune_keep_last",
        description="Number of most recent backups to keep.",
    )
    prune_keep_hourly: PropertyRef = PropertyRef(
        "prune_keep_hourly",
        description="Number of hourly backups to keep.",
    )
    prune_keep_daily: PropertyRef = PropertyRef(
        "prune_keep_daily",
        description="Number of daily backups to keep.",
    )
    prune_keep_weekly: PropertyRef = PropertyRef(
        "prune_keep_weekly",
        description="Number of weekly backups to keep.",
    )
    prune_keep_monthly: PropertyRef = PropertyRef(
        "prune_keep_monthly",
        description="Number of monthly backups to keep.",
    )
    prune_keep_yearly: PropertyRef = PropertyRef(
        "prune_keep_yearly",
        description="Number of yearly backups to keep.",
    )
    repeat_missed: PropertyRef = PropertyRef(
        "repeat_missed",
        description="Whether runs missed while the node was offline are executed as soon as possible.",
    )


@dataclass(frozen=True)
class ProxmoxBackupJobToClusterRelProperties(CartographyRelProperties):
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)


@dataclass(frozen=True)
class ProxmoxBackupJobToClusterRel(CartographyRelSchema):
    """The cluster contains the backup job."""

    target_node_label: str = "ProxmoxCluster"
    target_node_matcher: TargetNodeMatcher = make_target_node_matcher(
        {"id": PropertyRef("CLUSTER_ID", set_in_kwargs=True)},
    )
    direction: LinkDirection = LinkDirection.INWARD
    rel_label: str = "RESOURCE"
    properties: ProxmoxBackupJobToClusterRelProperties = (
        ProxmoxBackupJobToClusterRelProperties()
    )


@dataclass(frozen=True)
class ProxmoxBackupJobToStorageRelProperties(CartographyRelProperties):
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)


@dataclass(frozen=True)
class ProxmoxBackupJobToStorageRel(CartographyRelSchema):
    """The backup job writes its backups to the storage."""

    target_node_label: str = "ProxmoxStorage"
    target_node_matcher: TargetNodeMatcher = make_target_node_matcher(
        {"id": PropertyRef("storage_id")},
    )
    direction: LinkDirection = LinkDirection.OUTWARD
    rel_label: str = "BACKS_UP_TO"
    properties: ProxmoxBackupJobToStorageRelProperties = (
        ProxmoxBackupJobToStorageRelProperties()
    )


@dataclass(frozen=True)
class ProxmoxBackupJobToVMRelProperties(CartographyRelProperties):
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)


@dataclass(frozen=True)
class ProxmoxBackupJobToVMRel(CartographyRelSchema):
    """The backup job backs up the VM or container of the same cluster."""

    target_node_label: str = "ProxmoxVM"
    target_node_matcher: TargetNodeMatcher = make_target_node_matcher(
        {
            "vmid": PropertyRef("vmids", one_to_many=True),
            "cluster_id": PropertyRef("CLUSTER_ID", set_in_kwargs=True),
        },
    )
    direction: LinkDirection = LinkDirection.OUTWARD
    rel_label: str = "BACKS_UP"
    properties: ProxmoxBackupJobToVMRelProperties = ProxmoxBackupJobToVMRelProperties()


@dataclass(frozen=True)
class ProxmoxBackupJobSchema(CartographyNodeSchema):
    """A scheduled vzdump backup job in a Proxmox VE cluster."""

    label: str = "ProxmoxBackupJob"
    properties: ProxmoxBackupJobNodeProperties = ProxmoxBackupJobNodeProperties()
    sub_resource_relationship: ProxmoxBackupJobToClusterRel = (
        ProxmoxBackupJobToClusterRel()
    )
    other_relationships: OtherRelationships = OtherRelationships(
        [ProxmoxBackupJobToStorageRel(), ProxmoxBackupJobToVMRel()],
    )
