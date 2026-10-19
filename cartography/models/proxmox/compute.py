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
class ProxmoxVMNodeProperties(CartographyNodeProperties):
    id: PropertyRef = PropertyRef(
        "id",
        description="Guest ID in the form cluster_id/node/type/vmid.",
    )
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)
    vmid: PropertyRef = PropertyRef(
        "vmid",
        extra_index=True,
        description="Numeric VM ID, unique within the cluster.",
    )
    name: PropertyRef = PropertyRef(
        "name",
        extra_index=True,
        description="Guest name.",
    )
    node: PropertyRef = PropertyRef(
        "node",
        extra_index=True,
        description="Name of the node hosting the guest.",
    )
    cluster_id: PropertyRef = PropertyRef(
        "cluster_id",
        description="ID of the cluster the guest belongs to.",
    )
    type: PropertyRef = PropertyRef(
        "type",
        description="Guest type, qemu for virtual machines or lxc for containers.",
    )
    status: PropertyRef = PropertyRef(
        "status",
        description="Guest status, such as running or stopped.",
    )
    template: PropertyRef = PropertyRef(
        "template",
        description="Whether the guest is a template.",
    )
    cpu_cores: PropertyRef = PropertyRef(
        "cpu_cores",
        description="Number of CPUs reported in the guest list.",
    )
    cpu_sockets: PropertyRef = PropertyRef(
        "cpu_sockets",
        description="Number of CPU sockets reported in the guest list.",
    )
    cores: PropertyRef = PropertyRef(
        "cores",
        description="Number of cores per socket from the guest configuration.",
    )
    sockets: PropertyRef = PropertyRef(
        "sockets",
        description="Number of CPU sockets from the guest configuration.",
    )
    vcpus: PropertyRef = PropertyRef(
        "vcpus",
        description="Total virtual CPUs, computed as cores multiplied by sockets.",
    )
    memory: PropertyRef = PropertyRef(
        "memory",
        description="Maximum memory in bytes.",
    )
    disk_size: PropertyRef = PropertyRef(
        "disk_size",
        description="Maximum root disk size in bytes.",
    )
    uptime: PropertyRef = PropertyRef("uptime", description="Uptime in seconds.")
    tags: PropertyRef = PropertyRef("tags", description="Guest tags.")
    ostype: PropertyRef = PropertyRef(
        "ostype",
        description="Guest operating system type, such as l26 or win10.",
    )
    onboot: PropertyRef = PropertyRef(
        "onboot",
        description="Whether the guest starts when the host boots.",
    )
    protection: PropertyRef = PropertyRef(
        "protection",
        description="Whether removal of the guest and its disks is blocked.",
    )
    description: PropertyRef = PropertyRef(
        "description",
        description="Guest description.",
    )
    vmgenid: PropertyRef = PropertyRef(
        "vmgenid",
        description="VM generation ID exposed to the guest.",
    )
    machine: PropertyRef = PropertyRef(
        "machine",
        description="QEMU machine type.",
    )
    bios: PropertyRef = PropertyRef(
        "bios",
        description="BIOS implementation, seabios or ovmf.",
    )
    boot: PropertyRef = PropertyRef("boot", description="Boot order.")
    scsihw: PropertyRef = PropertyRef(
        "scsihw",
        description="SCSI controller model.",
    )
    cpu: PropertyRef = PropertyRef(
        "cpu",
        description="Emulated CPU type and flags.",
    )
    cpulimit: PropertyRef = PropertyRef(
        "cpulimit",
        description="Limit of CPU usage.",
    )
    cpuunits: PropertyRef = PropertyRef(
        "cpuunits",
        description="CPU weight relative to other guests.",
    )
    hotplug: PropertyRef = PropertyRef(
        "hotplug",
        description="Hotplug features enabled for the guest.",
    )
    lock: PropertyRef = PropertyRef(
        "lock",
        description="Lock held on the guest, such as backup or migrate.",
    )
    balloon: PropertyRef = PropertyRef(
        "balloon",
        description="Target memory for the balloon device in MiB.",
    )
    shares: PropertyRef = PropertyRef(
        "shares",
        description="Memory shares used for auto-ballooning.",
    )
    numa: PropertyRef = PropertyRef(
        "numa",
        description="Whether NUMA is enabled.",
    )
    kvm: PropertyRef = PropertyRef(
        "kvm",
        description="Whether KVM hardware virtualization is enabled.",
    )
    localtime: PropertyRef = PropertyRef(
        "localtime",
        description="Whether the real-time clock uses local time.",
    )
    keyboard: PropertyRef = PropertyRef(
        "keyboard",
        description="Keyboard layout for the VNC server.",
    )
    vga: PropertyRef = PropertyRef("vga", description="VGA hardware configuration.")
    agent_config: PropertyRef = PropertyRef(
        "agent_config",
        description="QEMU guest agent configuration string.",
    )
    args: PropertyRef = PropertyRef(
        "args",
        description="Extra arguments passed to QEMU.",
    )
    hugepages: PropertyRef = PropertyRef(
        "hugepages",
        description="Huge page size used for guest memory.",
    )
    keephugepages: PropertyRef = PropertyRef(
        "keephugepages",
        description="Whether huge pages are kept after the guest shuts down.",
    )
    freeze: PropertyRef = PropertyRef(
        "freeze",
        description="Whether the CPU is frozen at startup.",
    )
    watchdog: PropertyRef = PropertyRef(
        "watchdog",
        description="Virtual watchdog device configuration.",
    )
    rng0: PropertyRef = PropertyRef(
        "rng0",
        description="Virtual random number generator configuration.",
    )
    audio0: PropertyRef = PropertyRef(
        "audio0",
        description="Audio device configuration.",
    )
    efidisk0: PropertyRef = PropertyRef(
        "efidisk0",
        description="EFI variables disk configuration.",
    )
    tpmstate0: PropertyRef = PropertyRef(
        "tpmstate0",
        description="TPM state disk configuration.",
    )
    hostpci_count: PropertyRef = PropertyRef(
        "hostpci_count",
        description="Number of host PCI passthrough devices.",
    )
    usb_count: PropertyRef = PropertyRef(
        "usb_count",
        description="Number of USB devices.",
    )
    serial_count: PropertyRef = PropertyRef(
        "serial_count",
        description="Number of serial ports.",
    )
    parallel_count: PropertyRef = PropertyRef(
        "parallel_count",
        description="Number of parallel ports.",
    )
    guest_hostname: PropertyRef = PropertyRef(
        "guest_hostname",
        description="Hostname reported by the QEMU guest agent.",
    )
    guest_os_name: PropertyRef = PropertyRef(
        "guest_os_name",
        description="Operating system name reported by the QEMU guest agent.",
    )
    guest_os_version: PropertyRef = PropertyRef(
        "guest_os_version",
        description="Operating system version reported by the QEMU guest agent.",
    )
    guest_kernel_release: PropertyRef = PropertyRef(
        "guest_kernel_release",
        description="Kernel release reported by the QEMU guest agent.",
    )
    guest_kernel_version: PropertyRef = PropertyRef(
        "guest_kernel_version",
        description="Kernel version reported by the QEMU guest agent.",
    )
    guest_machine: PropertyRef = PropertyRef(
        "guest_machine",
        description="Hardware architecture reported by the QEMU guest agent.",
    )
    agent_enabled: PropertyRef = PropertyRef(
        "agent_enabled",
        description="Whether the QEMU guest agent returned data.",
    )
    hastate: PropertyRef = PropertyRef(
        "hastate",
        description="HA service status of the guest, such as started or stopped, when the HA manager handles it.",
    )
    pool: PropertyRef = PropertyRef(
        "pool",
        description="Name of the resource pool the guest belongs to.",
    )
    qmpstatus: PropertyRef = PropertyRef(
        "qmpstatus",
        description="VM run state from the QMP query-status command, such as running or paused.",
    )
    running_machine: PropertyRef = PropertyRef(
        "running_machine",
        description="QEMU machine type the running VM uses.",
    )
    running_qemu: PropertyRef = PropertyRef(
        "running_qemu",
        description="QEMU version the running VM uses.",
    )
    custom_cpu_model: PropertyRef = PropertyRef(
        "custom_cpu_model",
        description="Name of the custom CPU model set as the VM CPU type, without the custom- prefix.",
    )
    cloudinit_user: PropertyRef = PropertyRef(
        "cloudinit_user",
        description="User name that cloud-init configures in the current cloud-init image.",
    )
    cloudinit_type: PropertyRef = PropertyRef(
        "cloudinit_type",
        description="Cloud-init configuration format, such as nocloud or configdrive2.",
    )
    cloudinit_custom: PropertyRef = PropertyRef(
        "cloudinit_custom",
        description="Custom cloud-init snippet files that replace the generated configuration.",
    )
    cloudinit_upgrade: PropertyRef = PropertyRef(
        "cloudinit_upgrade",
        description="Whether cloud-init upgrades packages on first boot.",
    )
    cloudinit_nameserver: PropertyRef = PropertyRef(
        "cloudinit_nameserver",
        description="DNS servers that cloud-init configures.",
    )
    cloudinit_searchdomain: PropertyRef = PropertyRef(
        "cloudinit_searchdomain",
        description="DNS search domains that cloud-init configures.",
    )
    cloudinit_ipconfig: PropertyRef = PropertyRef(
        "cloudinit_ipconfig",
        description="Per-interface IP settings that cloud-init configures, as key=value entries such as ipconfig0=ip=dhcp.",
    )
    cloudinit_password_set: PropertyRef = PropertyRef(
        "cloudinit_password_set",
        description="Whether the cloud-init image sets a user password. The password itself is never stored.",
    )
    cloudinit_ssh_key_count: PropertyRef = PropertyRef(
        "cloudinit_ssh_key_count",
        description="Number of public SSH keys that cloud-init installs.",
    )
    cloudinit_ssh_key_fingerprints: PropertyRef = PropertyRef(
        "cloudinit_ssh_key_fingerprints",
        description="SHA256 fingerprints of the public SSH keys that cloud-init installs.",
    )
    guest_timezone: PropertyRef = PropertyRef(
        "guest_timezone",
        description="Time zone name reported by the QEMU guest agent.",
    )
    guest_timezone_offset: PropertyRef = PropertyRef(
        "guest_timezone_offset",
        description="Offset from UTC in seconds reported by the QEMU guest agent.",
    )
    guest_users: PropertyRef = PropertyRef(
        "guest_users",
        description="Users logged in to the VM, as domain\\user or user, reported by the QEMU guest agent.",
    )


@dataclass(frozen=True)
class ProxmoxVMToCustomCPUModelRelProperties(CartographyRelProperties):
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)


@dataclass(frozen=True)
class ProxmoxVMToCustomCPUModelRel(CartographyRelSchema):
    """The VM uses the custom CPU model as its CPU type."""

    target_node_label: str = "ProxmoxCustomCPUModel"
    target_node_matcher: TargetNodeMatcher = make_target_node_matcher(
        {"id": PropertyRef("custom_cpu_model_id")},
    )
    direction: LinkDirection = LinkDirection.OUTWARD
    rel_label: str = "USES_CPU_MODEL"
    properties: ProxmoxVMToCustomCPUModelRelProperties = (
        ProxmoxVMToCustomCPUModelRelProperties()
    )


@dataclass(frozen=True)
class ProxmoxVMToClusterRelProperties(CartographyRelProperties):
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)


@dataclass(frozen=True)
class ProxmoxVMToClusterRel(CartographyRelSchema):
    """The cluster contains the guest."""

    target_node_label: str = "ProxmoxCluster"
    target_node_matcher: TargetNodeMatcher = make_target_node_matcher(
        {"id": PropertyRef("CLUSTER_ID", set_in_kwargs=True)},
    )
    direction: LinkDirection = LinkDirection.INWARD
    rel_label: str = "RESOURCE"
    properties: ProxmoxVMToClusterRelProperties = ProxmoxVMToClusterRelProperties()


@dataclass(frozen=True)
class ProxmoxVMToNodeRelProperties(CartographyRelProperties):
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)


@dataclass(frozen=True)
class ProxmoxVMToNodeRel(CartographyRelSchema):
    """The node hosts the guest."""

    target_node_label: str = "ProxmoxNode"
    target_node_matcher: TargetNodeMatcher = make_target_node_matcher(
        {"id": PropertyRef("node_id")},
    )
    direction: LinkDirection = LinkDirection.INWARD
    rel_label: str = "HOSTS_VM"
    properties: ProxmoxVMToNodeRelProperties = ProxmoxVMToNodeRelProperties()


@dataclass(frozen=True)
class ProxmoxVMSchema(CartographyNodeSchema):
    """A QEMU virtual machine or LXC container in a Proxmox VE cluster."""

    label: str = "ProxmoxVM"
    properties: ProxmoxVMNodeProperties = ProxmoxVMNodeProperties()
    sub_resource_relationship: ProxmoxVMToClusterRel = ProxmoxVMToClusterRel()
    other_relationships: OtherRelationships = OtherRelationships(
        [ProxmoxVMToNodeRel(), ProxmoxVMToCustomCPUModelRel()],
    )


@dataclass(frozen=True)
class ProxmoxDiskNodeProperties(CartographyNodeProperties):
    id: PropertyRef = PropertyRef(
        "id",
        description="Disk ID in the form cluster_id/node/type/vmid:disk_id.",
    )
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)
    cluster_id: PropertyRef = PropertyRef(
        "cluster_id",
        description="ID of the cluster the disk belongs to.",
    )
    disk_id: PropertyRef = PropertyRef(
        "disk_id",
        description="Disk key in the guest configuration, such as scsi0, rootfs or mp0.",
    )
    vmid: PropertyRef = PropertyRef(
        "vmid",
        description="Numeric VM ID of the guest that uses the disk.",
    )
    storage: PropertyRef = PropertyRef(
        "storage",
        description="Name of the storage that holds the disk.",
    )
    size: PropertyRef = PropertyRef("size", description="Disk size in bytes.")
    backup: PropertyRef = PropertyRef(
        "backup",
        description="Whether the disk is included in backups.",
    )
    cache: PropertyRef = PropertyRef(
        "cache",
        description="Disk cache mode.",
    )
    format: PropertyRef = PropertyRef(
        "format",
        description="Disk image format, such as raw or qcow2.",
    )
    iothread: PropertyRef = PropertyRef(
        "iothread",
        description="Whether a dedicated I/O thread is used.",
    )
    discard: PropertyRef = PropertyRef(
        "discard",
        description="Discard (trim) mode.",
    )
    ssd: PropertyRef = PropertyRef(
        "ssd",
        description="Whether the disk is exposed to the guest as an SSD.",
    )
    replicate: PropertyRef = PropertyRef(
        "replicate",
        description="Whether the disk is included in storage replication.",
    )
    serial: PropertyRef = PropertyRef(
        "serial",
        description="Serial number reported to the guest.",
    )
    wwn: PropertyRef = PropertyRef(
        "wwn",
        description="World Wide Name reported to the guest.",
    )
    snapshot: PropertyRef = PropertyRef(
        "snapshot",
        description="Whether snapshot mode is enabled.",
    )
    iops: PropertyRef = PropertyRef(
        "iops",
        description="Maximum I/O operations per second.",
    )
    iops_rd: PropertyRef = PropertyRef(
        "iops_rd",
        description="Maximum read I/O operations per second.",
    )
    iops_wr: PropertyRef = PropertyRef(
        "iops_wr",
        description="Maximum write I/O operations per second.",
    )
    mbps: PropertyRef = PropertyRef(
        "mbps",
        description="Maximum throughput in MB/s.",
    )
    mbps_rd: PropertyRef = PropertyRef(
        "mbps_rd",
        description="Maximum read throughput in MB/s.",
    )
    mbps_wr: PropertyRef = PropertyRef(
        "mbps_wr",
        description="Maximum write throughput in MB/s.",
    )
    mbps_max: PropertyRef = PropertyRef(
        "mbps_max",
        description="Maximum burst throughput in MB/s.",
    )
    mbps_rd_max: PropertyRef = PropertyRef(
        "mbps_rd_max",
        description="Maximum burst read throughput in MB/s.",
    )
    mbps_wr_max: PropertyRef = PropertyRef(
        "mbps_wr_max",
        description="Maximum burst write throughput in MB/s.",
    )
    iops_max: PropertyRef = PropertyRef(
        "iops_max",
        description="Maximum burst I/O operations per second.",
    )
    iops_rd_max: PropertyRef = PropertyRef(
        "iops_rd_max",
        description="Maximum burst read I/O operations per second.",
    )
    iops_wr_max: PropertyRef = PropertyRef(
        "iops_wr_max",
        description="Maximum burst write I/O operations per second.",
    )
    media: PropertyRef = PropertyRef(
        "media",
        description="Drive media type.",
    )
    ro: PropertyRef = PropertyRef(
        "ro",
        description="Whether the disk is read-only.",
    )
    detect_zeroes: PropertyRef = PropertyRef(
        "detect_zeroes",
        description="Whether writes of zeroes are detected and optimized.",
    )


@dataclass(frozen=True)
class ProxmoxDiskToClusterRelProperties(CartographyRelProperties):
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)


@dataclass(frozen=True)
class ProxmoxDiskToClusterRel(CartographyRelSchema):
    """The cluster contains the disk."""

    target_node_label: str = "ProxmoxCluster"
    target_node_matcher: TargetNodeMatcher = make_target_node_matcher(
        {"id": PropertyRef("CLUSTER_ID", set_in_kwargs=True)},
    )
    direction: LinkDirection = LinkDirection.INWARD
    rel_label: str = "RESOURCE"
    properties: ProxmoxDiskToClusterRelProperties = ProxmoxDiskToClusterRelProperties()


@dataclass(frozen=True)
class ProxmoxDiskToVMRelProperties(CartographyRelProperties):
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)


@dataclass(frozen=True)
class ProxmoxDiskToVMRel(CartographyRelSchema):
    """The guest uses the disk."""

    target_node_label: str = "ProxmoxVM"
    target_node_matcher: TargetNodeMatcher = make_target_node_matcher(
        {"id": PropertyRef("vm_id")},
    )
    direction: LinkDirection = LinkDirection.INWARD
    rel_label: str = "HAS_DISK"
    properties: ProxmoxDiskToVMRelProperties = ProxmoxDiskToVMRelProperties()


@dataclass(frozen=True)
class ProxmoxDiskToStorageRelProperties(CartographyRelProperties):
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)


@dataclass(frozen=True)
class ProxmoxDiskToStorageRel(CartographyRelSchema):
    """The disk is stored on the storage."""

    target_node_label: str = "ProxmoxStorage"
    target_node_matcher: TargetNodeMatcher = make_target_node_matcher(
        {"id": PropertyRef("storage_id")},
    )
    direction: LinkDirection = LinkDirection.OUTWARD
    rel_label: str = "STORED_ON"
    properties: ProxmoxDiskToStorageRelProperties = ProxmoxDiskToStorageRelProperties()


@dataclass(frozen=True)
class ProxmoxDiskSchema(CartographyNodeSchema):
    """A virtual disk or container volume attached to a Proxmox guest."""

    label: str = "ProxmoxDisk"
    properties: ProxmoxDiskNodeProperties = ProxmoxDiskNodeProperties()
    sub_resource_relationship: ProxmoxDiskToClusterRel = ProxmoxDiskToClusterRel()
    other_relationships: OtherRelationships = OtherRelationships(
        [
            ProxmoxDiskToVMRel(),
            ProxmoxDiskToStorageRel(),
        ],
    )


@dataclass(frozen=True)
class ProxmoxNetworkInterfaceNodeProperties(CartographyNodeProperties):
    id: PropertyRef = PropertyRef(
        "id",
        description="Interface ID in the form cluster_id/node/type/vmid:net_id.",
    )
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)
    cluster_id: PropertyRef = PropertyRef(
        "cluster_id",
        description="ID of the cluster the interface belongs to.",
    )
    net_id: PropertyRef = PropertyRef(
        "net_id",
        description="Interface key in the guest configuration, such as net0.",
    )
    vmid: PropertyRef = PropertyRef(
        "vmid",
        description="Numeric VM ID of the guest that owns the interface.",
    )
    bridge: PropertyRef = PropertyRef(
        "bridge",
        description="Bridge the interface is attached to.",
    )
    mac_address: PropertyRef = PropertyRef(
        "mac_address",
        extra_index=True,
        description="MAC address.",
    )
    model: PropertyRef = PropertyRef(
        "model",
        description="Network card model, such as virtio, e1000 or veth.",
    )
    firewall: PropertyRef = PropertyRef(
        "firewall",
        description="Whether the Proxmox firewall is enabled on the interface.",
    )
    vlan_tag: PropertyRef = PropertyRef(
        "vlan_tag",
        description="VLAN tag applied to the interface traffic.",
    )
    ip: PropertyRef = PropertyRef(
        "ip",
        description="Configured IPv4 address in CIDR notation, or dhcp.",
    )
    ip6: PropertyRef = PropertyRef(
        "ip6",
        description="Configured IPv6 address in CIDR notation, or auto or dhcp.",
    )
    gw: PropertyRef = PropertyRef("gw", description="Configured IPv4 gateway.")
    gw6: PropertyRef = PropertyRef("gw6", description="Configured IPv6 gateway.")
    mtu: PropertyRef = PropertyRef("mtu", description="Maximum transmission unit.")
    rate: PropertyRef = PropertyRef(
        "rate",
        description="Rate limit in MB/s.",
    )
    link_up: PropertyRef = PropertyRef(
        "link_up",
        description="Whether the link is up, the inverse of the link_down option.",
    )
    queues: PropertyRef = PropertyRef(
        "queues",
        description="Number of packet queues on the guest side.",
    )
    trunks: PropertyRef = PropertyRef(
        "trunks",
        description="VLAN trunks passed through the interface.",
    )
    tag: PropertyRef = PropertyRef(
        "tag",
        description="Native VLAN tag when VLAN trunks are configured.",
    )
    actual_ipv4: PropertyRef = PropertyRef(
        "actual_ipv4",
        description="IPv4 addresses reported by the QEMU guest agent, comma-separated.",
    )
    actual_ipv6: PropertyRef = PropertyRef(
        "actual_ipv6",
        description="IPv6 addresses reported by the QEMU guest agent, comma-separated.",
    )
    guest_interface_name: PropertyRef = PropertyRef(
        "guest_interface_name",
        description="Interface name inside the guest reported by the QEMU guest agent.",
    )


@dataclass(frozen=True)
class ProxmoxNetworkInterfaceToClusterRelProperties(CartographyRelProperties):
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)


@dataclass(frozen=True)
class ProxmoxNetworkInterfaceToClusterRel(CartographyRelSchema):
    """The cluster contains the guest network interface."""

    target_node_label: str = "ProxmoxCluster"
    target_node_matcher: TargetNodeMatcher = make_target_node_matcher(
        {"id": PropertyRef("CLUSTER_ID", set_in_kwargs=True)},
    )
    direction: LinkDirection = LinkDirection.INWARD
    rel_label: str = "RESOURCE"
    properties: ProxmoxNetworkInterfaceToClusterRelProperties = (
        ProxmoxNetworkInterfaceToClusterRelProperties()
    )


@dataclass(frozen=True)
class ProxmoxNetworkInterfaceToVMRelProperties(CartographyRelProperties):
    lastupdated: PropertyRef = PropertyRef("lastupdated", set_in_kwargs=True)


@dataclass(frozen=True)
class ProxmoxNetworkInterfaceToVMRel(CartographyRelSchema):
    """The guest has the network interface."""

    target_node_label: str = "ProxmoxVM"
    target_node_matcher: TargetNodeMatcher = make_target_node_matcher(
        {"id": PropertyRef("vm_id")},
    )
    direction: LinkDirection = LinkDirection.INWARD
    rel_label: str = "HAS_NETWORK_INTERFACE"
    properties: ProxmoxNetworkInterfaceToVMRelProperties = (
        ProxmoxNetworkInterfaceToVMRelProperties()
    )


@dataclass(frozen=True)
class ProxmoxNetworkInterfaceSchema(CartographyNodeSchema):
    """A virtual network interface configured on a Proxmox guest."""

    label: str = "ProxmoxNetworkInterface"
    properties: ProxmoxNetworkInterfaceNodeProperties = (
        ProxmoxNetworkInterfaceNodeProperties()
    )
    sub_resource_relationship: ProxmoxNetworkInterfaceToClusterRel = (
        ProxmoxNetworkInterfaceToClusterRel()
    )
    other_relationships: OtherRelationships = OtherRelationships(
        [ProxmoxNetworkInterfaceToVMRel()],
    )
