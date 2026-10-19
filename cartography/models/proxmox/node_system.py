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
class ProxmoxNodeSystemRelProperties(CartographyRelProperties):
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)


# ============================================================================
# ProxmoxNodeConfig
# ============================================================================


@dataclass(frozen=True)
class ProxmoxNodeConfigNodeProperties(CartographyNodeProperties):
    id: PropertyRef = PropertyRef(
        "id",
        description="Configuration ID in the form cluster_id/node_name:config.",
    )
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)
    cluster_id: PropertyRef = PropertyRef(
        "cluster_id",
        description="ID of the Proxmox cluster the node belongs to.",
    )
    node_name: PropertyRef = PropertyRef(
        "node_name",
        description="Name of the Proxmox node the configuration describes.",
    )
    description: PropertyRef = PropertyRef(
        "description",
        description="Node notes shown in the web interface.",
    )
    location: PropertyRef = PropertyRef(
        "location",
        description="Node location, overriding the datacenter default. Proxmox VE 9 only.",
    )
    wakeonlan_mac: PropertyRef = PropertyRef(
        "wakeonlan_mac",
        description="MAC address used to wake the node over LAN.",
    )
    wakeonlan_bind_interface: PropertyRef = PropertyRef(
        "wakeonlan_bind_interface",
        description="Interface that sends the wake on LAN packet.",
    )
    wakeonlan_broadcast_address: PropertyRef = PropertyRef(
        "wakeonlan_broadcast_address",
        description="IPv4 broadcast address of the wake on LAN packet.",
    )
    ballooning_target: PropertyRef = PropertyRef(
        "ballooning_target",
        description="RAM usage target for ballooning, in percent of total memory.",
    )
    startall_onboot_delay: PropertyRef = PropertyRef(
        "startall_onboot_delay",
        description="Delay in seconds before starting the guests with on-boot enabled.",
    )
    acme_account: PropertyRef = PropertyRef(
        "acme_account",
        description="ACME account used for the node certificate.",
    )
    acme_domains: PropertyRef = PropertyRef(
        "acme_domains",
        description="Domains of the node ACME certificate.",
    )
    dns_servers: PropertyRef = PropertyRef(
        "dns_servers",
        description="Name server IP addresses of the node, in order.",
    )
    dns_search: PropertyRef = PropertyRef(
        "dns_search",
        description="Search domain for host name lookup.",
    )
    timezone: PropertyRef = PropertyRef(
        "timezone",
        description="Time zone of the node.",
    )
    enterprise_repo_enabled: PropertyRef = PropertyRef(
        "enterprise_repo_enabled",
        description=(
            "Whether the Proxmox VE enterprise repository is enabled. Empty when "
            "it is not configured."
        ),
    )
    no_subscription_repo_enabled: PropertyRef = PropertyRef(
        "no_subscription_repo_enabled",
        description=(
            "Whether the Proxmox VE no-subscription repository is enabled. Empty "
            "when it is not configured."
        ),
    )
    test_repo_enabled: PropertyRef = PropertyRef(
        "test_repo_enabled",
        description=(
            "Whether the Proxmox VE test repository is enabled. Empty when it is "
            "not configured."
        ),
    )
    enabled_standard_repos: PropertyRef = PropertyRef(
        "enabled_standard_repos",
        description=(
            "Handles of the enabled Proxmox standard repositories, such as "
            "enterprise or ceph-squid-no-subscription."
        ),
    )
    apt_repository_errors: PropertyRef = PropertyRef(
        "apt_repository_errors",
        description="Problems found while parsing the APT source files, as path: error.",
    )


@dataclass(frozen=True)
class ProxmoxNodeConfigToClusterRel(CartographyRelSchema):
    """The cluster contains the node configuration."""

    target_node_label: str = "ProxmoxCluster"
    target_node_matcher: TargetNodeMatcher = make_target_node_matcher(
        {"id": PropertyRef("CLUSTER_ID", set_in_kwargs=True)},
    )
    direction: LinkDirection = LinkDirection.INWARD
    rel_label: str = "RESOURCE"
    properties: ProxmoxNodeSystemRelProperties = ProxmoxNodeSystemRelProperties()


@dataclass(frozen=True)
class ProxmoxNodeConfigToNodeRel(CartographyRelSchema):
    """The configuration applies to the Proxmox node."""

    target_node_label: str = "ProxmoxNode"
    target_node_matcher: TargetNodeMatcher = make_target_node_matcher(
        {"id": PropertyRef("node_id")},
    )
    direction: LinkDirection = LinkDirection.INWARD
    rel_label: str = "HAS_CONFIG"
    properties: ProxmoxNodeSystemRelProperties = ProxmoxNodeSystemRelProperties()


@dataclass(frozen=True)
class ProxmoxNodeConfigSchema(CartographyNodeSchema):
    """System settings of a Proxmox VE node: node options, DNS, time zone and APT repository usage."""

    label: str = "ProxmoxNodeConfig"
    properties: ProxmoxNodeConfigNodeProperties = ProxmoxNodeConfigNodeProperties()
    sub_resource_relationship: ProxmoxNodeConfigToClusterRel = (
        ProxmoxNodeConfigToClusterRel()
    )
    other_relationships: OtherRelationships = OtherRelationships(
        [ProxmoxNodeConfigToNodeRel()],
    )


# ============================================================================
# ProxmoxService
# ============================================================================


@dataclass(frozen=True)
class ProxmoxServiceNodeProperties(CartographyNodeProperties):
    id: PropertyRef = PropertyRef(
        "id",
        description="Service ID in the form cluster_id/node_name:service:name.",
    )
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)
    cluster_id: PropertyRef = PropertyRef(
        "cluster_id",
        description="ID of the Proxmox cluster the service belongs to.",
    )
    node_name: PropertyRef = PropertyRef(
        "node_name",
        description="Name of the Proxmox node that runs the service.",
    )
    name: PropertyRef = PropertyRef(
        "name",
        extra_index=True,
        description="Short identifier of the service, such as pveproxy.",
    )
    service: PropertyRef = PropertyRef(
        "service",
        description="Systemd unit name of the service.",
    )
    description: PropertyRef = PropertyRef(
        "description",
        description="Description of the service.",
    )
    state: PropertyRef = PropertyRef(
        "state",
        description="Execution status of the service (systemd SubState), such as running or dead.",
    )
    active_state: PropertyRef = PropertyRef(
        "active_state",
        description="State of the service process (systemd ActiveState), such as active or failed.",
    )
    unit_state: PropertyRef = PropertyRef(
        "unit_state",
        description="Whether the unit is enabled (systemd UnitFileState), such as enabled or masked.",
    )


@dataclass(frozen=True)
class ProxmoxServiceToClusterRel(CartographyRelSchema):
    """The cluster contains the service."""

    target_node_label: str = "ProxmoxCluster"
    target_node_matcher: TargetNodeMatcher = make_target_node_matcher(
        {"id": PropertyRef("CLUSTER_ID", set_in_kwargs=True)},
    )
    direction: LinkDirection = LinkDirection.INWARD
    rel_label: str = "RESOURCE"
    properties: ProxmoxNodeSystemRelProperties = ProxmoxNodeSystemRelProperties()


@dataclass(frozen=True)
class ProxmoxServiceToNodeRel(CartographyRelSchema):
    """The Proxmox node runs the service."""

    target_node_label: str = "ProxmoxNode"
    target_node_matcher: TargetNodeMatcher = make_target_node_matcher(
        {"id": PropertyRef("node_id")},
    )
    direction: LinkDirection = LinkDirection.INWARD
    rel_label: str = "HAS_SERVICE"
    properties: ProxmoxNodeSystemRelProperties = ProxmoxNodeSystemRelProperties()


@dataclass(frozen=True)
class ProxmoxServiceSchema(CartographyNodeSchema):
    """A Proxmox VE system service on a node, such as pveproxy or corosync."""

    label: str = "ProxmoxService"
    properties: ProxmoxServiceNodeProperties = ProxmoxServiceNodeProperties()
    sub_resource_relationship: ProxmoxServiceToClusterRel = ProxmoxServiceToClusterRel()
    other_relationships: OtherRelationships = OtherRelationships(
        [ProxmoxServiceToNodeRel()],
    )


# ============================================================================
# ProxmoxPCIDevice
# ============================================================================


@dataclass(frozen=True)
class ProxmoxPCIDeviceNodeProperties(CartographyNodeProperties):
    id: PropertyRef = PropertyRef(
        "id",
        description="PCI device ID in the form cluster_id/node_name:pci:pci_id.",
    )
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)
    cluster_id: PropertyRef = PropertyRef(
        "cluster_id",
        description="ID of the Proxmox cluster the device belongs to.",
    )
    node_name: PropertyRef = PropertyRef(
        "node_name",
        description="Name of the Proxmox node the device is in.",
    )
    pci_id: PropertyRef = PropertyRef(
        "pci_id",
        extra_index=True,
        description="PCI address of the device, such as 0000:01:00.0.",
    )
    pci_class: PropertyRef = PropertyRef(
        "pci_class",
        description="PCI class code of the device.",
    )
    vendor: PropertyRef = PropertyRef(
        "vendor",
        description="PCI vendor ID.",
    )
    vendor_name: PropertyRef = PropertyRef(
        "vendor_name",
        description="PCI vendor name.",
    )
    device: PropertyRef = PropertyRef(
        "device",
        description="PCI device ID.",
    )
    device_name: PropertyRef = PropertyRef(
        "device_name",
        description="PCI device name.",
    )
    subsystem_vendor: PropertyRef = PropertyRef(
        "subsystem_vendor",
        description="PCI subsystem vendor ID.",
    )
    subsystem_vendor_name: PropertyRef = PropertyRef(
        "subsystem_vendor_name",
        description="PCI subsystem vendor name.",
    )
    subsystem_device: PropertyRef = PropertyRef(
        "subsystem_device",
        description="PCI subsystem device ID.",
    )
    subsystem_device_name: PropertyRef = PropertyRef(
        "subsystem_device_name",
        description="PCI subsystem device name.",
    )
    iommu_group: PropertyRef = PropertyRef(
        "iommu_group",
        description="IOMMU group of the device, or -1 when no IOMMU group is detected.",
    )
    mdev: PropertyRef = PropertyRef(
        "mdev",
        description="Whether the device can create mediated devices.",
    )
    mdev_types: PropertyRef = PropertyRef(
        "mdev_types",
        description="Mediated device types the device offers.",
    )
    mdev_available: PropertyRef = PropertyRef(
        "mdev_available",
        description="Number of mediated device instances still available, summed over all types.",
    )


@dataclass(frozen=True)
class ProxmoxPCIDeviceToClusterRel(CartographyRelSchema):
    """The cluster contains the PCI device."""

    target_node_label: str = "ProxmoxCluster"
    target_node_matcher: TargetNodeMatcher = make_target_node_matcher(
        {"id": PropertyRef("CLUSTER_ID", set_in_kwargs=True)},
    )
    direction: LinkDirection = LinkDirection.INWARD
    rel_label: str = "RESOURCE"
    properties: ProxmoxNodeSystemRelProperties = ProxmoxNodeSystemRelProperties()


@dataclass(frozen=True)
class ProxmoxPCIDeviceToNodeRel(CartographyRelSchema):
    """The Proxmox node has the PCI device."""

    target_node_label: str = "ProxmoxNode"
    target_node_matcher: TargetNodeMatcher = make_target_node_matcher(
        {"id": PropertyRef("node_id")},
    )
    direction: LinkDirection = LinkDirection.INWARD
    rel_label: str = "HAS_PCI_DEVICE"
    properties: ProxmoxNodeSystemRelProperties = ProxmoxNodeSystemRelProperties()


@dataclass(frozen=True)
class ProxmoxPCIDeviceSchema(CartographyNodeSchema):
    """A PCI device of a Proxmox VE node that can be passed through to guests."""

    label: str = "ProxmoxPCIDevice"
    properties: ProxmoxPCIDeviceNodeProperties = ProxmoxPCIDeviceNodeProperties()
    sub_resource_relationship: ProxmoxPCIDeviceToClusterRel = (
        ProxmoxPCIDeviceToClusterRel()
    )
    other_relationships: OtherRelationships = OtherRelationships(
        [ProxmoxPCIDeviceToNodeRel()],
    )
