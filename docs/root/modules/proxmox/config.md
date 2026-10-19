# Proxmox Configuration

Cartography reads a Proxmox VE cluster through its REST API. The module supports Proxmox VE 9 and is compatible with Proxmox VE 8.4. Data that only Proxmox VE 9 provides, such as HA rules, is skipped on 8.4.

## Authentication

Cartography supports API tokens (recommended) and user passwords. Store the secret in an environment variable and pass the variable name to Cartography.

### API token

1. In the Proxmox web interface, open **Datacenter** > **Permissions** > **API Tokens** and click **Add**.
1. Select the user, for example `cartography@pve`, and set a token ID, for example `cartography`.
1. Keep **Privilege Separation** enabled and grant the token the permissions listed below, or disable it so the token inherits the user's permissions.
1. Copy the token secret. Proxmox shows it only once.

### Password

Use the password of a Proxmox user. Prefer an API token: a password grants the full rights of the user and cannot be scoped.

## Required Permissions

Grant the built-in `PVEAuditor` role on path `/` with propagation enabled. It covers every endpoint Cartography reads except the ACME account details described below:

| Privilege | Used for |
| --- | --- |
| `Sys.Audit` | Cluster status and options, Corosync configuration and QDevice status, nodes, node networks, certificates, users, API tokens, second factors, realms, realm sync jobs, groups, roles, ACLs, HA groups, resources, rules and status, cluster and node firewall (rules, options, security groups, aliases, IP sets), Ceph (OSD flags, OSD details, and OSD volumes need `Sys.Audit`; the other Ceph endpoints accept `Sys.Audit` or `Datastore.Audit`), guests and volumes included in backup jobs, guests not covered by backups, all fields of the node vzdump defaults, metric servers, node disks, SMART data, ZFS, LVM, managed directories, package versions, APT repositories, node options, DNS, time, services, PCI devices and mediated device types |
| `VM.Audit` | VM and container configuration, snapshots, cloud-init values, container IP addresses, VM and container firewall (rules, options, aliases, IP sets), backup jobs, replication jobs and their state |
| `Datastore.Audit` | Storage backends, storage content (backup archives, ISO images, container templates), storage identity (Proxmox VE 9), node vzdump defaults (on the default backup storage) |
| `Pool.Audit` | Resource pools, including nested pools. Cartography lists only the pools where the user has `Pool.Audit`. |
| `Mapping.Audit` | PCI, USB, and directory resource mappings; notification targets, endpoints, and matchers on `/mapping/notifications`; custom CPU models (Proxmox VE 9 only; skipped on Proxmox VE 8.4) |

Ceph muted health checks (`/cluster/ceph/health-mute`) exist only on Proxmox VE 9. On Proxmox VE 8.4 Cartography syncs Ceph without them.

Cartography does not read `/storage/{storage}`: it requires `Datastore.Allocate`, and `/storage` already returns the storage configuration. The storage identity endpoint exists only on Proxmox VE 9; on Proxmox VE 8.4 Cartography skips it.

The number of API calls grows with the cluster. For N online nodes and J backup jobs:

- Backup coverage makes `J + N + 3` calls.
- Storage content makes one listing per active shared storage, plus one per node for each active local storage that can hold backups, ISO images, or container templates. Storage that only holds guest disks is not listed.
- Storage identity makes one call per active shared storage on Proxmox VE 9, and one call in total on Proxmox VE 8.4.
- Replication makes `N + 2` calls. A per-job status call is only added when a node returns a job without its state.

When a storage content listing fails, Cartography logs a warning with the node and storage and goes on with the rest of the sync. The backup archives, ISO images and container templates of a storage that is not read in a run, because the listing failed or the storage is inactive or disabled, are kept as seen in the last successful listing. An offline Proxmox Backup Server therefore does not make its guests look unbacked. Content of a storage that no node reports any more, for example after it is removed from the configuration, is deleted. A failed storage identity read is skipped in the same way, storage by storage.

The resource mapping lists (`/cluster/mapping/pci`, `/cluster/mapping/usb`, `/cluster/mapping/dir`) return only the mappings the token has `Mapping.Audit`, `Mapping.Use`, or `Mapping.Modify` on, under `/mapping/<type>/<id>`. Without it, Cartography syncs no mappings and logs no error.

Notification targets and matchers accept `Mapping.Audit`, `Mapping.Modify`, or `Mapping.Use` on `/mapping/notifications`. The endpoint details need `Mapping.Audit` or `Mapping.Modify` there (gotify and webhook lists accept only `Mapping.Audit`). When a token gets 403 on one of them, Cartography logs it and skips that part: without endpoint details, targets keep only their name, type, and status.

The ACME account list is open to every user, but the account details (`/cluster/acme/account/{name}`) are readable only by `root@pam`, on both Proxmox VE 8.4 and 9. With `PVEAuditor`, Cartography syncs the account names only and logs it. Cartography does not read `/cluster/acme/plugins`, which needs `Sys.Modify` and holds DNS API credentials.

The node details need `Sys.Audit` on `/`, or on `/nodes/{node}` for the disk list, package versions, APT repositories, DNS, time and services. The PCI device and mediated device type endpoints accept either `Sys.Audit` or `Sys.Modify`, so `Sys.Audit` is enough. The subscription endpoint is readable by any user, but Proxmox returns the subscription key only with `Sys.Audit`. The privileges are the same on Proxmox VE 8.4 and 9. Cartography never calls `/nodes/{node}/apt/update`, which needs `Sys.Modify`.

For each online node, the node details sync makes 14 API calls, plus one per local disk (SMART data), one per ZFS pool (pool details) and one per PCI device that supports mediated devices.

### Access control endpoints

`PVEAuditor` on `/` reads all access control data Cartography collects. The table lists the endpoints and the privilege each one checks:

| Endpoint | Privilege | Notes |
| --- | --- | --- |
| `/access/users?full=1` | `Sys.Audit` or `User.Modify` on `/access/groups`, or on a group of the user | Users with their groups, API tokens and TFA lock state. Users outside the caller's reach are left out silently. |
| `/access/tfa` | `Sys.Audit` or `User.Modify` on `/access/groups` | Second factors of every user. Without the privilege the API returns only the caller's own factors. |
| `/access/domains` | None | Realm list, public for the login screen. |
| `/access/domains/{realm}` | `Sys.Audit` or `Realm.Allocate` on `/access/realm` | Server and client settings of LDAP, AD and OpenID realms. On a 403, Cartography logs it at info level and loads the realms without these settings. |
| `/cluster/jobs/realm-sync` | `Sys.Audit` on `/` | Scheduled realm sync jobs. |
| `/access/groups`, `/access/groups/{groupid}`, `/access/roles` | `Sys.Audit` on `/access` | Groups, group members, roles. |
| `/access/acl` | `Sys.Audit` on `/access` | All ACL entries, including entries for API tokens. |

`PVEAuditor` cannot call `/access/users/{userid}/token` for other users: that endpoint requires `User.Modify`. Cartography does not call it and reads the same token fields (`tokenid`, `comment`, `expire`, `privsep`) from `/access/users?full=1`, which `Sys.Audit` covers.

Cartography never reads secrets: the API returns no token secrets, TOTP secrets or recovery codes, and Cartography keeps only an allowlist of realm settings, so the LDAP bind password and the OpenID client key are never stored.

## Optional Permissions

`--proxmox-enable-guest-agent` queries the QEMU guest agent of running VMs. The privilege it needs depends on the Proxmox VE version:

- Proxmox VE 9: `VM.GuestAgent.Audit`, which `PVEAuditor` includes.
- Proxmox VE 8.4: `VM.Monitor`, which `PVEAuditor` does not include. Grant it through a custom role that contains `VM.Monitor`.

Without it, Cartography logs the failure and syncs the VMs without guest agent data. The same privilege covers the filesystem, logged-in user and time zone commands; a command that the agent does not support or blocks is skipped for that VM.

## Configure Cartography

| Option | Description |
| --- | --- |
| `--proxmox-host` | Proxmox VE host to sync, for example `proxmox.example.com`. Enables the module. |
| `--proxmox-port` | API port. Default: `8006`. |
| `--proxmox-user` | User including the realm, for example `cartography@pve`. Default: `root@pam`. |
| `--proxmox-token-name` | API token ID, the part after `!`. Use with `--proxmox-token-value-env-var`. |
| `--proxmox-token-value-env-var` | Name of the environment variable that holds the API token secret. |
| `--proxmox-password-env-var` | Name of the environment variable that holds the user password. Used only when no API token is configured. |
| `--proxmox-verify-ssl` / `--no-proxmox-verify-ssl` | Verify the TLS certificate of the API. Default: enabled. |
| `--proxmox-enable-guest-agent` | Collect OS, network, filesystem, logged-in user and time zone details from the QEMU guest agent. Increases sync time. Default: disabled. |
| `--proxmox-request-timeout` | Timeout in seconds for each API request. Default: `60`. |

## Run Cartography

```bash
export PROXMOX_TOKEN_VALUE='<token-secret>'
cartography \
  --selected-modules proxmox \
  --proxmox-host proxmox.example.com \
  --proxmox-user cartography@pve \
  --proxmox-token-name cartography \
  --proxmox-token-value-env-var PROXMOX_TOKEN_VALUE
```

## Advanced Configuration

Each guest costs one configuration and one snapshot request, plus one cloud-init request for a VM with a cloud-init drive and one interface request for a running container. With `--proxmox-enable-guest-agent`, a running VM costs six more guest agent requests, three of them only when the agent answers the first three.

Cartography tries an API request up to three times, with exponential backoff, when it times out, cannot connect, or gets a 429, 502, 503 or 504 response. Other errors stop the Proxmox sync.

On Proxmox VE 9, once every node is upgraded, HA groups are migrated to HA rules and the HA groups endpoint returns an error. Cartography then reads HA rules only and skips HA groups.

To sync several clusters, run Cartography once per cluster with a different `--proxmox-host`. Each run only cleans up data of the cluster it synced. Resources with the same name in different clusters, such as node `pve` or storage `local`, stay separate nodes because their IDs start with the cluster ID.

Use `--no-proxmox-verify-ssl` only for clusters that still use the self-signed certificate created at installation.
