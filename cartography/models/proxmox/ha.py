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
class ProxmoxHAGroupNodeProperties(CartographyNodeProperties):
    id: PropertyRef = PropertyRef(
        "id",
        description="HA group ID in the form cluster_id/group.",
    )
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)
    group: PropertyRef = PropertyRef(
        "group",
        extra_index=True,
        description="HA group name.",
    )
    cluster_id: PropertyRef = PropertyRef(
        "cluster_id",
        description="ID of the cluster that defines the HA group.",
    )
    nodes: PropertyRef = PropertyRef(
        "nodes",
        description="Cluster nodes in the group, with optional priorities, as returned by the API.",
    )
    restricted: PropertyRef = PropertyRef(
        "restricted",
        description="Whether resources in the group can run only on the group's nodes.",
    )
    nofailback: PropertyRef = PropertyRef(
        "nofailback",
        description="Whether resources stay put instead of migrating back to a higher-priority node.",
    )
    comment: PropertyRef = PropertyRef("comment", description="HA group comment.")


@dataclass(frozen=True)
class ProxmoxHAGroupToClusterRelProperties(CartographyRelProperties):
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)


@dataclass(frozen=True)
class ProxmoxHAGroupToClusterRel(CartographyRelSchema):
    """The cluster contains the HA group."""

    target_node_label: str = "ProxmoxCluster"
    target_node_matcher: TargetNodeMatcher = make_target_node_matcher(
        {"id": PropertyRef("CLUSTER_ID", set_in_kwargs=True)},
    )
    direction: LinkDirection = LinkDirection.INWARD
    rel_label: str = "RESOURCE"
    properties: ProxmoxHAGroupToClusterRelProperties = (
        ProxmoxHAGroupToClusterRelProperties()
    )


@dataclass(frozen=True)
class ProxmoxHAGroupSchema(CartographyNodeSchema):
    """A high availability group that sets node preferences for HA resources in a Proxmox VE cluster."""

    label: str = "ProxmoxHAGroup"
    properties: ProxmoxHAGroupNodeProperties = ProxmoxHAGroupNodeProperties()
    sub_resource_relationship: ProxmoxHAGroupToClusterRel = ProxmoxHAGroupToClusterRel()


@dataclass(frozen=True)
class ProxmoxHAResourceNodeProperties(CartographyNodeProperties):
    id: PropertyRef = PropertyRef(
        "id",
        description="HA resource ID in the form cluster_id/sid, such as prod/vm:100.",
    )
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)
    sid: PropertyRef = PropertyRef(
        "sid",
        extra_index=True,
        description="HA resource service ID, such as vm:100 or ct:200.",
    )
    cluster_id: PropertyRef = PropertyRef(
        "cluster_id",
        description="ID of the cluster that manages the HA resource.",
    )
    state: PropertyRef = PropertyRef(
        "state",
        description="Requested HA state, such as started, stopped, disabled, or ignored.",
    )
    group: PropertyRef = PropertyRef(
        "group",
        description="Name of the HA group the resource belongs to.",
    )
    max_restart: PropertyRef = PropertyRef(
        "max_restart",
        description="Maximum number of restart attempts on a node after a start failure.",
    )
    max_relocate: PropertyRef = PropertyRef(
        "max_relocate",
        description="Maximum number of relocation attempts to another node after a start failure.",
    )
    comment: PropertyRef = PropertyRef("comment", description="HA resource comment.")
    type: PropertyRef = PropertyRef(
        "type",
        description="HA resource type, such as vm or ct.",
    )
    failback: PropertyRef = PropertyRef(
        "failback",
        description=(
            "Whether the resource migrates back to the highest-priority node of its "
            "node affinity rule when that node comes online. Proxmox VE 9 only; "
            "unset means the default, enabled."
        ),
    )
    auto_rebalance: PropertyRef = PropertyRef(
        "auto_rebalance",
        description=(
            "Whether the resource may be migrated during automatic rebalancing. "
            "Proxmox VE 9.2 or later; unset means the default, enabled."
        ),
    )
    vmid: PropertyRef = PropertyRef(
        "vmid",
        description="Numeric VM ID parsed from the service ID, when the resource is a VM or container.",
    )


@dataclass(frozen=True)
class ProxmoxHAResourceToClusterRelProperties(CartographyRelProperties):
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)


@dataclass(frozen=True)
class ProxmoxHAResourceToClusterRel(CartographyRelSchema):
    """The cluster contains the HA resource."""

    target_node_label: str = "ProxmoxCluster"
    target_node_matcher: TargetNodeMatcher = make_target_node_matcher(
        {"id": PropertyRef("CLUSTER_ID", set_in_kwargs=True)},
    )
    direction: LinkDirection = LinkDirection.INWARD
    rel_label: str = "RESOURCE"
    properties: ProxmoxHAResourceToClusterRelProperties = (
        ProxmoxHAResourceToClusterRelProperties()
    )


@dataclass(frozen=True)
class ProxmoxHAResourceToHAGroupRelProperties(CartographyRelProperties):
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)


@dataclass(frozen=True)
class ProxmoxHAResourceToHAGroupRel(CartographyRelSchema):
    """The HA resource is assigned to the HA group."""

    target_node_label: str = "ProxmoxHAGroup"
    target_node_matcher: TargetNodeMatcher = make_target_node_matcher(
        {"id": PropertyRef("group_id")},
    )
    direction: LinkDirection = LinkDirection.OUTWARD
    rel_label: str = "MEMBER_OF_HA_GROUP"
    properties: ProxmoxHAResourceToHAGroupRelProperties = (
        ProxmoxHAResourceToHAGroupRelProperties()
    )


@dataclass(frozen=True)
class ProxmoxHAResourceToVMRelProperties(CartographyRelProperties):
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)


@dataclass(frozen=True)
class ProxmoxHAResourceToVMRel(CartographyRelSchema):
    """The HA resource keeps the VM or container of the same cluster highly available."""

    target_node_label: str = "ProxmoxVM"
    target_node_matcher: TargetNodeMatcher = make_target_node_matcher(
        {
            "vmid": PropertyRef("vmid"),
            "cluster_id": PropertyRef("CLUSTER_ID", set_in_kwargs=True),
        },
    )
    direction: LinkDirection = LinkDirection.OUTWARD
    rel_label: str = "PROTECTS"
    properties: ProxmoxHAResourceToVMRelProperties = (
        ProxmoxHAResourceToVMRelProperties()
    )


@dataclass(frozen=True)
class ProxmoxHAResourceSchema(CartographyNodeSchema):
    """A VM or container managed by the high availability stack of a Proxmox VE cluster."""

    label: str = "ProxmoxHAResource"
    properties: ProxmoxHAResourceNodeProperties = ProxmoxHAResourceNodeProperties()
    sub_resource_relationship: ProxmoxHAResourceToClusterRel = (
        ProxmoxHAResourceToClusterRel()
    )
    other_relationships: OtherRelationships = OtherRelationships(
        [ProxmoxHAResourceToHAGroupRel(), ProxmoxHAResourceToVMRel()],
    )


@dataclass(frozen=True)
class ProxmoxHARuleNodeProperties(CartographyNodeProperties):
    id: PropertyRef = PropertyRef(
        "id",
        description="HA rule ID in the form cluster_id/rule.",
    )
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)
    rule: PropertyRef = PropertyRef(
        "rule",
        extra_index=True,
        description="HA rule identifier.",
    )
    cluster_id: PropertyRef = PropertyRef(
        "cluster_id",
        description="ID of the cluster that defines the HA rule.",
    )
    type: PropertyRef = PropertyRef(
        "type",
        description="HA rule type: node-affinity or resource-affinity.",
    )
    resources: PropertyRef = PropertyRef(
        "resources",
        description="Service IDs of the HA resources the rule applies to, such as vm:100.",
    )
    nodes: PropertyRef = PropertyRef(
        "nodes",
        description=(
            "For node affinity rules, the cluster nodes with optional priorities, "
            "in the form node[:priority],..."
        ),
    )
    affinity: PropertyRef = PropertyRef(
        "affinity",
        description=(
            "positive or negative. Node affinity: run the resources on the listed "
            "nodes, or on any other node. Resource affinity: keep the resources "
            "on the same node, or on separate nodes."
        ),
    )
    strict: PropertyRef = PropertyRef(
        "strict",
        description=(
            "For node affinity rules, whether the resources are restricted to the "
            "listed nodes and stopped when none is available."
        ),
    )
    disable: PropertyRef = PropertyRef(
        "disable",
        description="Whether the HA rule is disabled.",
    )
    comment: PropertyRef = PropertyRef("comment", description="HA rule comment.")


@dataclass(frozen=True)
class ProxmoxHARuleToClusterRelProperties(CartographyRelProperties):
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)


@dataclass(frozen=True)
class ProxmoxHARuleToClusterRel(CartographyRelSchema):
    """The cluster contains the HA rule."""

    target_node_label: str = "ProxmoxCluster"
    target_node_matcher: TargetNodeMatcher = make_target_node_matcher(
        {"id": PropertyRef("CLUSTER_ID", set_in_kwargs=True)},
    )
    direction: LinkDirection = LinkDirection.INWARD
    rel_label: str = "RESOURCE"
    properties: ProxmoxHARuleToClusterRelProperties = (
        ProxmoxHARuleToClusterRelProperties()
    )


@dataclass(frozen=True)
class ProxmoxHARuleToHAResourceRelProperties(CartographyRelProperties):
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)


@dataclass(frozen=True)
class ProxmoxHARuleToHAResourceRel(CartographyRelSchema):
    """The HA rule constrains the placement of the HA resource."""

    target_node_label: str = "ProxmoxHAResource"
    target_node_matcher: TargetNodeMatcher = make_target_node_matcher(
        {"id": PropertyRef("resource_ids", one_to_many=True)},
    )
    direction: LinkDirection = LinkDirection.OUTWARD
    rel_label: str = "APPLIES_TO_HA_RESOURCE"
    properties: ProxmoxHARuleToHAResourceRelProperties = (
        ProxmoxHARuleToHAResourceRelProperties()
    )


@dataclass(frozen=True)
class ProxmoxHARuleToNodeRelProperties(CartographyRelProperties):
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)


@dataclass(frozen=True)
class ProxmoxHARuleToNodeRel(CartographyRelSchema):
    """The node affinity rule lists the cluster node, as a placement target or, when its affinity is negative, as a node to avoid."""

    target_node_label: str = "ProxmoxNode"
    target_node_matcher: TargetNodeMatcher = make_target_node_matcher(
        {"id": PropertyRef("node_ids", one_to_many=True)},
    )
    direction: LinkDirection = LinkDirection.OUTWARD
    rel_label: str = "APPLIES_TO_NODE"
    properties: ProxmoxHARuleToNodeRelProperties = ProxmoxHARuleToNodeRelProperties()


@dataclass(frozen=True)
class ProxmoxHARuleSchema(CartographyNodeSchema):
    """A high availability rule that sets node affinity or resource affinity for HA resources in a Proxmox VE 9 cluster. HA rules replace HA groups."""

    label: str = "ProxmoxHARule"
    properties: ProxmoxHARuleNodeProperties = ProxmoxHARuleNodeProperties()
    sub_resource_relationship: ProxmoxHARuleToClusterRel = ProxmoxHARuleToClusterRel()
    other_relationships: OtherRelationships = OtherRelationships(
        [ProxmoxHARuleToHAResourceRel(), ProxmoxHARuleToNodeRel()],
    )


@dataclass(frozen=True)
class ProxmoxHAManagerNodeProperties(CartographyNodeProperties):
    id: PropertyRef = PropertyRef(
        "id",
        description="HA manager ID in the form cluster_id/ha-manager.",
    )
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)
    cluster_id: PropertyRef = PropertyRef(
        "cluster_id",
        description="ID of the cluster the HA manager runs in.",
    )
    quorate: PropertyRef = PropertyRef(
        "quorate",
        description="Whether the cluster was quorate when the HA status was read.",
    )
    master_node: PropertyRef = PropertyRef(
        "master_node",
        description="Name of the node that holds the cluster resource manager (CRM) master role.",
    )
    master_status: PropertyRef = PropertyRef(
        "master_status",
        description="Status text of the CRM master, as shown by ha-manager status.",
    )
    armed_state: PropertyRef = PropertyRef(
        "armed_state",
        description=(
            "Fencing state of the HA stack: armed, standby, disarming, or disarmed. "
            "Proxmox VE 9.2 or later."
        ),
    )
    resource_mode: PropertyRef = PropertyRef(
        "resource_mode",
        description=(
            "How HA resources are handled while HA is disarmed: freeze or ignore. "
            "Proxmox VE 9.2 or later."
        ),
    )


@dataclass(frozen=True)
class ProxmoxHAManagerToClusterRelProperties(CartographyRelProperties):
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)


@dataclass(frozen=True)
class ProxmoxHAManagerToClusterRel(CartographyRelSchema):
    """The cluster runs the HA manager."""

    target_node_label: str = "ProxmoxCluster"
    target_node_matcher: TargetNodeMatcher = make_target_node_matcher(
        {"id": PropertyRef("CLUSTER_ID", set_in_kwargs=True)},
    )
    direction: LinkDirection = LinkDirection.INWARD
    rel_label: str = "RESOURCE"
    properties: ProxmoxHAManagerToClusterRelProperties = (
        ProxmoxHAManagerToClusterRelProperties()
    )


@dataclass(frozen=True)
class ProxmoxHAManagerToMasterNodeRelProperties(CartographyRelProperties):
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)


@dataclass(frozen=True)
class ProxmoxHAManagerToMasterNodeRel(CartographyRelSchema):
    """The cluster node holds the CRM master role of the HA manager."""

    target_node_label: str = "ProxmoxNode"
    target_node_matcher: TargetNodeMatcher = make_target_node_matcher(
        {"id": PropertyRef("master_node_id")},
    )
    direction: LinkDirection = LinkDirection.OUTWARD
    rel_label: str = "CRM_MASTER"
    properties: ProxmoxHAManagerToMasterNodeRelProperties = (
        ProxmoxHAManagerToMasterNodeRelProperties()
    )


@dataclass(frozen=True)
class ProxmoxHAManagerSchema(CartographyNodeSchema):
    """The high availability manager of a Proxmox VE cluster, with its quorum, CRM master, and fencing state."""

    label: str = "ProxmoxHAManager"
    properties: ProxmoxHAManagerNodeProperties = ProxmoxHAManagerNodeProperties()
    sub_resource_relationship: ProxmoxHAManagerToClusterRel = (
        ProxmoxHAManagerToClusterRel()
    )
    other_relationships: OtherRelationships = OtherRelationships(
        [ProxmoxHAManagerToMasterNodeRel()],
    )


@dataclass(frozen=True)
class ProxmoxHALRMNodeProperties(CartographyNodeProperties):
    id: PropertyRef = PropertyRef(
        "id",
        description="LRM ID in the form cluster_id/lrm:node.",
    )
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)
    cluster_id: PropertyRef = PropertyRef(
        "cluster_id",
        description="ID of the cluster the LRM belongs to.",
    )
    node: PropertyRef = PropertyRef(
        "node",
        extra_index=True,
        description="Name of the node the LRM runs on.",
    )
    status: PropertyRef = PropertyRef(
        "status",
        description="LRM status text, as shown by ha-manager status, such as active, idle, or maintenance mode.",
    )
    state: PropertyRef = PropertyRef(
        "state",
        description="LRM state: wait_for_agent_lock, active, or lost_agent_lock.",
    )
    mode: PropertyRef = PropertyRef(
        "mode",
        description="LRM mode, such as active or maintenance.",
    )
    crm_node_state: PropertyRef = PropertyRef(
        "crm_node_state",
        description="State of the node as seen by the CRM master, such as online, maintenance, or unknown.",
    )


@dataclass(frozen=True)
class ProxmoxHALRMToClusterRelProperties(CartographyRelProperties):
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)


@dataclass(frozen=True)
class ProxmoxHALRMToClusterRel(CartographyRelSchema):
    """The cluster contains the HA local resource manager."""

    target_node_label: str = "ProxmoxCluster"
    target_node_matcher: TargetNodeMatcher = make_target_node_matcher(
        {"id": PropertyRef("CLUSTER_ID", set_in_kwargs=True)},
    )
    direction: LinkDirection = LinkDirection.INWARD
    rel_label: str = "RESOURCE"
    properties: ProxmoxHALRMToClusterRelProperties = (
        ProxmoxHALRMToClusterRelProperties()
    )


@dataclass(frozen=True)
class ProxmoxHALRMToNodeRelProperties(CartographyRelProperties):
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)


@dataclass(frozen=True)
class ProxmoxHALRMToNodeRel(CartographyRelSchema):
    """The HA local resource manager runs on the cluster node."""

    target_node_label: str = "ProxmoxNode"
    target_node_matcher: TargetNodeMatcher = make_target_node_matcher(
        {"id": PropertyRef("node_id")},
    )
    direction: LinkDirection = LinkDirection.OUTWARD
    rel_label: str = "RUNS_ON"
    properties: ProxmoxHALRMToNodeRelProperties = ProxmoxHALRMToNodeRelProperties()


@dataclass(frozen=True)
class ProxmoxHALRMSchema(CartographyNodeSchema):
    """The high availability local resource manager (LRM) of one node in a Proxmox VE cluster."""

    label: str = "ProxmoxHALRM"
    properties: ProxmoxHALRMNodeProperties = ProxmoxHALRMNodeProperties()
    sub_resource_relationship: ProxmoxHALRMToClusterRel = ProxmoxHALRMToClusterRel()
    other_relationships: OtherRelationships = OtherRelationships(
        [ProxmoxHALRMToNodeRel()],
    )
