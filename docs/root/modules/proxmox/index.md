# Proxmox Virtual Environment

Cartography syncs one Proxmox VE cluster per run. Each cluster is a `ProxmoxCluster` node and owns every other Proxmox node in the graph.

Proxmox names such as node `pve`, storage `local`, or user `root@pam` are only unique inside one cluster, so the `id` of every other Proxmox node starts with the cluster ID, for example `prod/pve` or `prod/root@pam`. The name inside the cluster stays in its own indexed property, such as `name`, `userid`, or `vmid`, next to `cluster_id`.

The module ingests:

- **Cluster topology**: cluster settings, nodes, and node network interfaces.
- **Compute**: QEMU virtual machines and LXC containers, with their disks and network interfaces. Guest agent data (OS, hostname, guest IP addresses) is optional.
- **Storage**: storage backends and the nodes where they are available. On Proxmox VE 9, shared storage also gets its instance identity.
- **Storage content**: backup archives (with size, creation time, notes, protection, encryption, and Proxmox Backup Server verification state), linked to their storage and to the guest with the same VM ID, and ISO images and container templates. Guest disk volumes are not duplicated: they are the `ProxmoxDisk` nodes of the compute sync. Shared storage is listed from one node, storage local to a node from every node where it is active. Storage that only holds guest disks is not listed.
- **Resource pools**: pools and the VMs and storage they contain.
- **Backup jobs**: scheduled vzdump jobs, their target storage, and the guests they back up.
- **Backup coverage**: the guests each backup job selects when it runs, including `all` and pool selections (`COVERS`), and the guest disks it includes (`INCLUDES_DISK`). Every guest gets `backup_covered`, false when Proxmox lists it as not covered by any backup job. The vzdump defaults of each node are `ProxmoxBackupDefaults` nodes.
- **Replication**: storage replication jobs, linked to the replicated guest and the target node, with the last sync time, duration, failure count, and last error.
- **High availability**: HA groups and HA-managed resources.
- **Access control**: users, groups, roles, and ACLs, with the resources each ACL applies to.
- **Firewall**: cluster, node, and guest firewall rules, and cluster IP sets.
- **Certificates**: TLS certificates installed on each node.

```{toctree}
config
schema
```
