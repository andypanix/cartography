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
- **Access control**: users, API tokens, second factors, authentication realms, realm sync jobs, groups, roles, and ACLs, with the resources each ACL applies to. ACL entries for an API token link to the token, not to its user; each token stores `privsep`, which tells whether it is limited to its own ACLs or has all permissions of its user. The derived `HAS_PERMISSION` edges cover users and groups only, not API tokens. Users carry a TFA summary (`tfa_enabled`, `tfa_types`, `totp_locked`, `tfa_locked_until`).
- **Firewall**: cluster, node, and guest firewall rules, and cluster IP sets.
- **Certificates**: TLS certificates installed on each node.

```{toctree}
config
schema
```
