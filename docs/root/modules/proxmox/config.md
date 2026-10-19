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

Grant the built-in `PVEAuditor` role on path `/` with propagation enabled. It covers every endpoint Cartography reads except the ACME account details described below:

| Privilege | Used for |
| --- | --- |
| `Sys.Audit` | Cluster status and options, nodes, node networks, certificates, users, groups, roles, ACLs, HA, firewall, metric servers |
| `VM.Audit` | VM and container configuration, guest firewall rules, backup jobs |
| `Datastore.Audit` | Storage backends |
| `Pool.Audit` | Resource pools |
| `Mapping.Audit` | PCI, USB, and directory resource mappings; notification targets, endpoints, and matchers on `/mapping/notifications` |

The resource mapping lists (`/cluster/mapping/pci`, `/cluster/mapping/usb`, `/cluster/mapping/dir`) return only the mappings the token has `Mapping.Audit`, `Mapping.Use`, or `Mapping.Modify` on, under `/mapping/<type>/<id>`. Without it, Cartography syncs no mappings and logs no error.

Notification targets and matchers accept `Mapping.Audit`, `Mapping.Modify`, or `Mapping.Use` on `/mapping/notifications`. The endpoint details need `Mapping.Audit` or `Mapping.Modify` there (gotify and webhook lists accept only `Mapping.Audit`). When a token gets 403 on one of them, Cartography logs it and skips that part: without endpoint details, targets keep only their name, type, and status.

The ACME account list is open to every user, but the account details (`/cluster/acme/account/{name}`) are readable only by `root@pam`, on both Proxmox VE 8.4 and 9. With `PVEAuditor`, Cartography syncs the account names only and logs it. Cartography does not read `/cluster/acme/plugins`, which needs `Sys.Modify` and holds DNS API credentials.

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
