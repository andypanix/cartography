# Proxmox Configuration

Cartography reads a Proxmox VE cluster through its REST API. Proxmox VE 7.0 or later is required.

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

Grant the built-in `PVEAuditor` role on path `/` with propagation enabled. It covers every endpoint Cartography reads:

| Privilege | Used for |
| --- | --- |
| `Sys.Audit` | Cluster status and options, nodes, node networks, certificates, users, groups, roles, ACLs, HA, firewall, guests and volumes included in backup jobs, guests not covered by backups, all fields of the node vzdump defaults |
| `VM.Audit` | VM and container configuration, guest firewall rules, backup jobs, replication jobs and their state |
| `Datastore.Audit` | Storage backends, storage content (backup archives, ISO images, container templates), storage identity (Proxmox VE 9), node vzdump defaults (on the default backup storage) |
| `Pool.Audit` | Resource pools |

Cartography does not read `/storage/{storage}`: it requires `Datastore.Allocate`, and `/storage` already returns the storage configuration. The storage identity endpoint exists only on Proxmox VE 9; on Proxmox VE 8.4 Cartography skips it.

The number of API calls grows with the cluster. For N online nodes and J backup jobs:

- Backup coverage makes `J + N + 3` calls.
- Storage content makes one listing per active shared storage, plus one per node for each active local storage that can hold backups, ISO images, or container templates. Storage that only holds guest disks is not listed.
- Storage identity makes one call per active shared storage on Proxmox VE 9, and one call in total on Proxmox VE 8.4.
- Replication makes `N + 2` calls. A per-job status call is only added when a node returns a job without its state.

When a storage content listing fails, Cartography logs a warning with the node and storage and goes on with the rest of the sync. The backup archives, ISO images and container templates of a storage that is not read in a run, because the listing failed or the storage is inactive or disabled, are kept as seen in the last successful listing. An offline Proxmox Backup Server therefore does not make its guests look unbacked. Content of a storage that no node reports any more, for example after it is removed from the configuration, is deleted. A failed storage identity read is skipped in the same way, storage by storage.

## Optional Permissions

`--proxmox-enable-guest-agent` queries the QEMU guest agent of running VMs. This needs `VM.Monitor` on Proxmox VE 8, or `VM.GuestAgent.Audit` on Proxmox VE 9, which `PVEAuditor` does not include. Without it, Cartography logs the failure and syncs the VMs without guest agent data.

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
| `--proxmox-enable-guest-agent` | Collect OS and network details from the QEMU guest agent. Increases sync time. Default: disabled. |
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

Cartography tries an API request up to three times, with exponential backoff, when it times out, cannot connect, or gets a 429, 502, 503 or 504 response. Other errors stop the Proxmox sync.

To sync several clusters, run Cartography once per cluster with a different `--proxmox-host`. Each run only cleans up data of the cluster it synced. Resources with the same name in different clusters, such as node `pve` or storage `local`, stay separate nodes because their IDs start with the cluster ID.

Use `--no-proxmox-verify-ssl` only for clusters that still use the self-signed certificate created at installation.
