# Proxmox Virtual Environment

Cartography syncs one Proxmox VE cluster per run. Each cluster is a `ProxmoxCluster` node and owns every other Proxmox node in the graph.

Proxmox names such as node `pve`, storage `local`, or user `root@pam` are only unique inside one cluster, so the `id` of every other Proxmox node starts with the cluster ID, for example `prod/pve` or `prod/root@pam`. The name inside the cluster stays in its own indexed property, such as `name`, `userid`, or `vmid`, next to `cluster_id`.

The module ingests:

- **Cluster topology**: cluster settings, nodes, and node network interfaces.
- **Compute**: QEMU virtual machines and LXC containers, with their disks and network interfaces. Guest agent data (OS, hostname, guest IP addresses) is optional.
- **Storage**: storage backends and the nodes where they are available.
- **Resource pools**: pools and the VMs and storage they contain.
- **Backup jobs**: scheduled vzdump jobs, their target storage, and the guests they back up.
- **High availability**: HA groups and HA-managed resources.
- **Access control**: users, groups, roles, and ACLs, with the resources each ACL applies to.
- **Firewall**: cluster, node, and guest firewall rules, and cluster IP sets.
- **Certificates**: TLS certificates installed on each node.
- **Node hardware**: local disks with their SMART health (power-on hours, wear, reallocated sectors, temperature), ZFS pools with their state and member disks, LVM volume groups and thin pools, directory storages managed by Proxmox, and PCI devices with their IOMMU group and mediated device types.
- **Node software**: versions of the key Proxmox packages (such as `proxmox-ve` with the running kernel, `pve-manager`, `qemu-server`, `lxc-pve` and Ceph when installed), the APT repositories and which Proxmox standard repositories are enabled, and the support subscription. Cartography keeps only the last four characters of the subscription key and never stores the key in full or the offline signature.
- **Node system settings**: node notes, wake on LAN, ballooning target, ACME domains, DNS servers and search domain, time zone, and the state of the Proxmox system services.

Node hardware, software and system settings are read only from nodes that are online. The details of a node that is offline during a sync are removed until it is online again.

When the details of one online node cannot be read, for example because the node is unreachable or the API user lacks a privilege on it, Cartography logs a warning, syncs the other nodes, and skips the cleanup of node details for that sync, so the failed node keeps the details of its last successful sync. A disk whose SMART data cannot be read, such as a RAID virtual disk, is synced without SMART values, and a PCI device whose mediated device types cannot be read is synced without them.

User names, passwords and credential query parameters (such as `token` or `key`) are removed from APT repository URIs before they are stored.

A `ProxmoxPhysicalDisk` keeps the kernel device name in `name`, such as `sdb` or `nvme0n1`, next to `devpath`, so it can be matched to the devices Ceph reports for an OSD. ZFS pools, LVM volume groups and managed directories link to a disk with `USES_DISK` when their device is named by kernel name, partition, or a `/dev/disk/by-id` name built from the disk WWN or serial. A device named by UUID is not linked.

```{toctree}
config
schema
```
