# Proxmox Virtual Environment

Cartography syncs one Proxmox VE cluster per run. The module supports Proxmox VE 9 and is compatible with Proxmox VE 8.4. Each cluster is a `ProxmoxCluster` node and owns every other Proxmox node in the graph.

Proxmox names such as node `pve`, storage `local`, or user `root@pam` are only unique inside one cluster, so the `id` of every other Proxmox node starts with the cluster ID, for example `prod/pve` or `prod/root@pam`. The name inside the cluster stays in its own indexed property, such as `name`, `userid`, or `vmid`, next to `cluster_id`.

The module ingests:

- **Cluster topology**: cluster settings, nodes, and node network interfaces. On a cluster, also the Corosync totem settings, the QDevice status, and each node's Corosync ID, votes, and link addresses. A standalone host has no Corosync configuration, so these properties stay empty.
- **Compute**: QEMU virtual machines and LXC containers, with their disks and network interfaces. Guest agent data (OS, hostname, guest IP addresses) is optional.
- **Guest details**: snapshots and their parent chain, HA state and pool, the running QEMU machine and version, cloud-init values, IP addresses of running containers, and custom CPU models (Proxmox VE 9). Cloud-init passwords are never stored: Cartography records only whether one is set, and stores public SSH keys as a count and SHA256 fingerprints. With the guest agent enabled, it also reads the mounted filesystems, logged-in users and time zone of running VMs.
- **Storage**: storage backends and the nodes where they are available.
- **Resource pools**: pools, nested pools, and the VMs and storage they contain.
- **Backup jobs**: scheduled vzdump jobs, their target storage, and the guests they back up.
- **High availability**: HA-managed resources, HA rules (Proxmox VE 9) and HA groups (Proxmox VE 8.4, or 9 before the groups are migrated to rules), the HA manager with its CRM master node, quorum and fencing state, and the local resource manager (LRM) of each node.
- **Access control**: users, API tokens, second factors, authentication realms, realm sync jobs, groups, roles, and ACLs, with the resources each ACL applies to. ACL entries for an API token link to the token, not to its user; each token stores `privsep`, which tells whether it is limited to its own ACLs or has all permissions of its user. The derived `HAS_PERMISSION` edges cover users and groups only, not API tokens. Users carry a TFA summary (`tfa_enabled`, `tfa_types`, `totp_locked`, `tfa_locked_until`).
- **Firewall**: firewall rules of the cluster, nodes, QEMU VMs, LXC containers, and security groups; cluster and guest IP sets and aliases; and the firewall options of the cluster, each node, and each guest. Rules link to the security group they include and to the IP sets and aliases their source and destination name, when the name resolves to a synced IP set or alias.
- **Certificates**: TLS certificates installed on each node.
- **Resource mappings**: cluster-wide PCI, USB, and directory mappings, the nodes in their map, and the VMs whose configuration uses them (`hostpciN` or `usbN` with `mapping=`, `virtiofsN`).
- **Notifications**: notification targets (sendmail, SMTP, gotify, webhook endpoints), the Proxmox users that mail targets notify, and the matchers that route notifications to targets. Passwords, tokens, webhook header and secret values, webhook bodies, and URL paths are never stored: only header and secret names, and the scheme, host, and port of gotify and webhook URLs.
- **Metric servers**: external InfluxDB and Graphite servers the cluster sends metrics to, without tokens.
- **ACME accounts**: ACME accounts used to order certificates, with their CA directory, contacts, and status, without the account key.

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
