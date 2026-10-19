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
class ProxmoxReplicationJobNodeProperties(CartographyNodeProperties):
    id: PropertyRef = PropertyRef(
        "id",
        description="Replication job ID in the form cluster_id/guest-jobnum.",
    )
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)
    job_id: PropertyRef = PropertyRef(
        "job_id",
        extra_index=True,
        description="Replication job ID as returned by the Proxmox VE API, in the form guest-jobnum.",
    )
    cluster_id: PropertyRef = PropertyRef(
        "cluster_id",
        description="ID of the cluster the replication job belongs to.",
    )
    guest: PropertyRef = PropertyRef(
        "guest",
        description="VM ID of the replicated guest.",
    )
    jobnum: PropertyRef = PropertyRef(
        "jobnum",
        description="Sequential job number of the replication job for its guest.",
    )
    target: PropertyRef = PropertyRef(
        "target",
        description="Name of the node the guest volumes are replicated to.",
    )
    type: PropertyRef = PropertyRef(
        "type",
        description="Replication job type. Proxmox VE only supports local.",
    )
    schedule: PropertyRef = PropertyRef(
        "schedule",
        description="Calendar event schedule of the replication. Proxmox VE defaults to */15.",
    )
    rate: PropertyRef = PropertyRef(
        "rate",
        description="Rate limit in megabytes per second.",
    )
    enabled: PropertyRef = PropertyRef(
        "enabled",
        description="Whether the replication job is enabled.",
    )
    comment: PropertyRef = PropertyRef(
        "comment",
        description="Description of the replication job.",
    )
    remove_job: PropertyRef = PropertyRef(
        "remove_job",
        description="Removal mark of the job: local or full when the job is being removed.",
    )
    source: PropertyRef = PropertyRef(
        "source",
        description="Node the guest was on when the job last ran, as reported by the job configuration.",
    )
    last_sync: PropertyRef = PropertyRef(
        "last_sync",
        description="Time of the last successful replication, in seconds since the UNIX epoch.",
    )
    last_try: PropertyRef = PropertyRef(
        "last_try",
        description="Time of the last replication attempt, in seconds since the UNIX epoch.",
    )
    next_sync: PropertyRef = PropertyRef(
        "next_sync",
        description="Time of the next scheduled replication, in seconds since the UNIX epoch.",
    )
    duration: PropertyRef = PropertyRef(
        "duration",
        description="Duration of the last replication run, in seconds.",
    )
    fail_count: PropertyRef = PropertyRef(
        "fail_count",
        description="Number of consecutive failed replication runs.",
    )
    error: PropertyRef = PropertyRef(
        "error",
        description="Error message of the last failed replication run.",
    )


@dataclass(frozen=True)
class ProxmoxReplicationJobToClusterRelProperties(CartographyRelProperties):
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)


@dataclass(frozen=True)
class ProxmoxReplicationJobToClusterRel(CartographyRelSchema):
    """The cluster contains the replication job."""

    target_node_label: str = "ProxmoxCluster"
    target_node_matcher: TargetNodeMatcher = make_target_node_matcher(
        {"id": PropertyRef("CLUSTER_ID", set_in_kwargs=True)},
    )
    direction: LinkDirection = LinkDirection.INWARD
    rel_label: str = "RESOURCE"
    properties: ProxmoxReplicationJobToClusterRelProperties = (
        ProxmoxReplicationJobToClusterRelProperties()
    )


@dataclass(frozen=True)
class ProxmoxReplicationJobToVMRelProperties(CartographyRelProperties):
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)


@dataclass(frozen=True)
class ProxmoxReplicationJobToVMRel(CartographyRelSchema):
    """The replication job replicates the volumes of the guest of the same cluster."""

    target_node_label: str = "ProxmoxVM"
    target_node_matcher: TargetNodeMatcher = make_target_node_matcher(
        {
            "vmid": PropertyRef("guest"),
            "cluster_id": PropertyRef("CLUSTER_ID", set_in_kwargs=True),
        },
    )
    direction: LinkDirection = LinkDirection.OUTWARD
    rel_label: str = "REPLICATES"
    properties: ProxmoxReplicationJobToVMRelProperties = (
        ProxmoxReplicationJobToVMRelProperties()
    )


@dataclass(frozen=True)
class ProxmoxReplicationJobToNodeRelProperties(CartographyRelProperties):
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)


@dataclass(frozen=True)
class ProxmoxReplicationJobToNodeRel(CartographyRelSchema):
    """The replication job copies the guest volumes to the target node."""

    target_node_label: str = "ProxmoxNode"
    target_node_matcher: TargetNodeMatcher = make_target_node_matcher(
        {"id": PropertyRef("target_node_id")},
    )
    direction: LinkDirection = LinkDirection.OUTWARD
    rel_label: str = "REPLICATES_TO"
    properties: ProxmoxReplicationJobToNodeRelProperties = (
        ProxmoxReplicationJobToNodeRelProperties()
    )


@dataclass(frozen=True)
class ProxmoxReplicationJobSchema(CartographyNodeSchema):
    """A storage replication job that copies a guest's volumes to another node."""

    label: str = "ProxmoxReplicationJob"
    properties: ProxmoxReplicationJobNodeProperties = (
        ProxmoxReplicationJobNodeProperties()
    )
    sub_resource_relationship: ProxmoxReplicationJobToClusterRel = (
        ProxmoxReplicationJobToClusterRel()
    )
    other_relationships: OtherRelationships = OtherRelationships(
        [
            ProxmoxReplicationJobToVMRel(),
            ProxmoxReplicationJobToNodeRel(),
        ],
    )
