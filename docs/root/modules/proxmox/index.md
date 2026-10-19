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
- **Software-Defined Networking (SDN)**: the running SDN configuration (zones, VNets, subnets, VNet firewall options and rules, controllers, IPAM plugins with the addresses of the built-in IPAM, and DNS plugins) and, per node, the zone and VNet status. On Proxmox VE 9 also fabrics, prefix lists, route maps, the VNet bridges and their ports on each node, and fabric neighbors, interfaces and routes. Guest network interfaces link to the VNet they are attached to.

```{toctree}
config
schema
```
