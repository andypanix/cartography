# Proxmox Virtual Environment

Cartography syncs one Proxmox VE cluster per run. The module supports Proxmox VE 9, and Proxmox VE 8.4 or later. Each cluster is a `ProxmoxCluster` node and owns every other Proxmox node in the graph.

Proxmox names such as node `pve`, storage `local`, or user `root@pam` are only unique inside one cluster, so the `id` of every other Proxmox node starts with the cluster ID, for example `prod/pve` or `prod/root@pam`. The name inside the cluster stays in its own indexed property, such as `name`, `userid`, or `vmid`, next to `cluster_id`.

The module ingests:

- **Cluster topology**: cluster settings, nodes, and node network interfaces. On a cluster, also the Corosync totem settings, the QDevice status, and each node's Corosync ID, votes, and link addresses. A standalone host has no Corosync configuration, so these properties stay empty. When the QDevice status cannot be read, Cartography logs a warning and syncs the cluster without it.
- **Compute**: QEMU virtual machines and LXC containers, with their disks and network interfaces. Guest agent data (OS, hostname, guest IP addresses) is optional.
- **Guest details**: snapshots and their parent chain, HA state and pool, the running QEMU machine and version, cloud-init values, IP addresses of running containers, and custom CPU models (Proxmox VE 9). Cloud-init passwords are never stored: Cartography records only whether one is set, and stores public SSH keys as a count and SHA256 fingerprints. With the guest agent enabled, it also reads the mounted filesystems, logged-in users and time zone of running VMs.
- **Storage**: storage backends and the nodes where they are available. On Proxmox VE 9, shared storage also gets its instance identity.
- **Storage content**: backup archives (with size, creation time, notes, protection, encryption, and Proxmox Backup Server verification state), linked to their storage and to the guest with the same VM ID, and ISO images and container templates. Guest disk volumes are not duplicated: they are the `ProxmoxDisk` nodes of the compute sync. Shared storage is listed from one node, storage local to a node from every node where it is active. Storage that only holds guest disks is not listed.
- **Resource pools**: pools, nested pools, and the VMs and storage they contain.
- **Backup jobs**: scheduled vzdump jobs, their target storage, and the guests they back up.
- **Backup coverage**: the guests each backup job selects when it runs, including `all` and pool selections (`COVERS`), and the guest disks it includes (`INCLUDES_DISK`). Every guest gets `backup_covered`, false when Proxmox lists it as not covered by any backup job. The vzdump defaults of each node are `ProxmoxBackupDefaults` nodes.
- **Replication**: storage replication jobs, linked to the replicated guest and the target node, with the last sync time, duration, failure count, and last error.
- **High availability**: HA-managed resources, HA rules (Proxmox VE 9) and HA groups (Proxmox VE 8.4, or 9 before the groups are migrated to rules), the HA manager with its CRM master node, quorum and fencing state, and the local resource manager (LRM) of each node.
- **Access control**: users, API tokens, second factors, authentication realms, realm sync jobs, groups, roles, and ACLs, with the resources each ACL applies to. ACL entries for an API token link to the token, not to its user; each token stores `privsep`, which tells whether it is limited to its own ACLs or has all permissions of its user. The derived `HAS_PERMISSION` edges cover users and groups only, not API tokens. Users carry a TFA summary (`tfa_enabled`, `tfa_types`, `totp_locked`, `tfa_locked_until`).
- **Firewall**: firewall rules of the cluster, nodes, QEMU VMs, LXC containers, and security groups; cluster and guest IP sets and aliases; and the firewall options of the cluster, each node, and each guest. Rules link to the security group they include and to the IP sets and aliases their source and destination name, when the name resolves to a synced IP set or alias.
- **Certificates**: TLS certificates installed on each node.
- **Ceph**: the hyper-converged Ceph cluster, when Ceph is installed: monitors, managers, metadata servers, and OSDs with the nodes they run on, pools with their CRUSH rules, CephFS file systems, and the RBD and CephFS storage that use them. Cartography reads Ceph through another node when the configured host does not run Ceph. Clusters without Ceph on any online node skip this step, and Cartography keeps the existing Ceph data when Ceph cannot be read.
- **Software-Defined Networking (SDN)**: the running SDN configuration (zones, VNets, subnets, VNet firewall options and rules, controllers, IPAM plugins with the addresses of the built-in IPAM, and DNS plugins) and, per node, the zone and VNet status. On Proxmox VE 9 also fabrics, prefix lists, route maps, the VNet bridges and their ports on each node, and fabric neighbors, interfaces and routes. Guest network interfaces link to the VNet they are attached to. VNet firewall rules link to the cluster IP sets, aliases, and security groups they name, like the other firewall rules.
- **Resource mappings**: cluster-wide PCI, USB, and directory mappings, the nodes in their map, and the VMs whose configuration uses them (`hostpciN` or `usbN` with `mapping=`, `virtiofsN`).
- **Notifications**: notification targets (sendmail, SMTP, gotify, webhook endpoints), the Proxmox users that mail targets notify, and the matchers that route notifications to targets. Passwords, tokens, webhook header and secret values, webhook bodies, and URL paths are never stored: only header and secret names, and the scheme, host, and port of gotify and webhook URLs.
- **Metric servers**: external InfluxDB and Graphite servers the cluster sends metrics to, without tokens.
- **ACME accounts**: ACME accounts used to order certificates, with their CA directory, contacts, and status, without the account key.
- **Node hardware**: local disks with their SMART health (power-on hours, wear, reallocated sectors, temperature), ZFS pools with their state and member disks, LVM volume groups and thin pools, directory storages managed by Proxmox, and PCI devices with their IOMMU group and mediated device types.
- **Node software**: versions of the key Proxmox packages (such as `proxmox-ve` with the running kernel, `pve-manager`, `qemu-server`, `lxc-pve` and Ceph when installed), the APT repositories and which Proxmox standard repositories are enabled, and the support subscription. Cartography keeps only the last four characters of the subscription key and never stores the key in full or the offline signature.
- **Node system settings**: node notes, wake on LAN, ballooning target, ACME domains, DNS servers and search domain, time zone, and the state of the Proxmox system services.

Node hardware, software and system settings are read only from nodes that are online. The details of a node that is offline during a sync are removed until it is online again.

When the details of one online node cannot be read, for example because the node is unreachable or the API user lacks a privilege on it, Cartography logs a warning, syncs the other nodes, and skips the cleanup of node details for that sync, so the failed node keeps the details of its last successful sync. A disk whose SMART data cannot be read, such as a RAID virtual disk, is synced without SMART values, and a PCI device whose mediated device types cannot be read is synced without them.

User names, passwords and credential query parameters (such as `token` or `key`) are removed from APT repository URIs and from the datacenter HTTP proxy URL before they are stored.

A `ProxmoxPhysicalDisk` keeps the kernel device name in `name`, such as `sdb` or `nvme0n1`, next to `devpath`, so it can be matched to the devices Ceph reports for an OSD. ZFS pools, LVM volume groups and managed directories link to a disk with `USES_DISK` when their device is named by kernel name, partition, or a `/dev/disk/by-id` name built from the disk WWN or serial. A device named by UUID is not linked.

```{toctree}
config
schema
```

## Firewall enforcement

Proxmox only applies the rules of a guest when the firewall is enabled for the whole cluster, for the guest, and on the network interface (the `firewall=1` flag). The firewall options are stored as `firewall_*` properties on `ProxmoxCluster`, `ProxmoxNode`, and `ProxmoxVM`. Options that are not set take the default documented by Proxmox. This query lists the guest interfaces whose rules are enforced:

```cypher
MATCH (c:ProxmoxCluster)-[:RESOURCE]->(vm:ProxmoxVM)
      -[:HAS_NETWORK_INTERFACE]->(nic:ProxmoxNetworkInterface)
WHERE c.firewall_enabled AND vm.firewall_enabled AND nic.firewall
RETURN vm.name, vm.vmid, nic.net_id
```

A rule source or destination such as `+name`, `+dc/name`, `+guest/name`, `name`, `dc/name`, or `guest/name` links the rule to that IP set or alias. A guest rule without a prefix uses the guest definition first, then the cluster one, as Proxmox does. Cluster, node, and security group rules only use cluster definitions. Names that match no synced object, such as SDN IP sets (`+sdn/...`) or the built-in `local_network` alias, are kept on the rule without a link.
