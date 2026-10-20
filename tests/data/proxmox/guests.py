"""
Mock data for the Proxmox guest details (snapshots, cloud-init, guest agent, ...).
"""

MOCK_SSH_PUBLIC_KEY = (
    "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIGCAYx0dg8vX9lsFLAXM4KpKrxWbY7mJKM6cKwWZW3ck"
    " test@example"
)
# Output of ssh-keygen -lf for MOCK_SSH_PUBLIC_KEY.
MOCK_SSH_FINGERPRINT = "SHA256:UJE91ik98ftZC2CHqE8Davky4xY/KOZ6JUNFMizPJJs"

# /nodes/{node}/qemu?full=1 and /nodes/{node}/lxc
MOCK_GUEST_LIST = {
    "node1": [
        {
            "vmid": 100,
            "name": "web",
            "status": "running",
            "type": "qemu",
            "node": "node1",
            "qmpstatus": "running",
            "running-machine": "pc-q35-9.2+pve1",
            "running-qemu": "9.2.0",
        },
    ],
    "node2": [
        {
            "vmid": 200,
            "name": "ct",
            "status": "running",
            "type": "lxc",
            "node": "node2",
        },
    ],
}

# /nodes/{node}/{type}/{vmid}/config
MOCK_GUEST_CONFIG = {
    100: {
        "cpu": "custom-avx,flags=+aes",
        "scsi0": "local-lvm:vm-100-disk-0,size=10G",
        "ide2": "local-lvm:vm-100-cloudinit,media=cdrom",
        "net0": "virtio=BC:24:11:00:01:00,bridge=vmbr0",
    },
    200: {
        "rootfs": "local-lvm:vm-200-disk-0,size=8G",
        "net0": "name=eth0,bridge=vmbr0,hwaddr=BC:24:11:00:02:00,ip=dhcp",
    },
}

# /cluster/resources?type=vm
MOCK_GUEST_RESOURCES = [
    {
        "id": "qemu/100",
        "type": "qemu",
        "vmid": 100,
        "node": "node1",
        "hastate": "started",
        "pool": "prod",
    },
    {"id": "lxc/200", "type": "lxc", "vmid": 200, "node": "node2"},
]

# /cluster/qemu/custom-cpu-models
MOCK_CUSTOM_CPU_MODELS = [
    {
        "cputype": "custom-avx",
        "flags": "+avx;+avx2",
        "phys-bits": "host",
        "hidden": 0,
        "hv-vendor-id": "proxmox",
        "reported-model": "kvm64",
        "digest": "abc",
    },
]

# /nodes/{node}/{type}/{vmid}/snapshot, children listed before parents on
# purpose: the transform must load parents first.
MOCK_SNAPSHOTS = {
    100: [
        {
            "name": "current",
            "parent": "after-upgrade",
            "description": "You are here!",
        },
        {
            "name": "after-upgrade",
            "parent": "before-upgrade",
            "snaptime": 1700000100,
            "vmstate": 1,
            "description": "After upgrade",
        },
        {
            "name": "before-upgrade",
            "snaptime": 1700000000,
            "vmstate": 0,
            "description": "Before upgrade",
        },
    ],
    200: [
        {"name": "current", "parent": "base"},
        {"name": "base", "snaptime": 1700000200, "description": "Base"},
    ],
}

# /nodes/{node}/{type}/{vmid}/snapshot/{snapname}/config, keyed by VM ID and
# snapshot name. The cloud-init password is there to prove it is never stored.
MOCK_SNAPSHOT_CONFIGS = {
    100: {
        "before-upgrade": {
            "cores": 2,
            "sockets": 1,
            "memory": "4096",
            "machine": "pc-q35-8.1",
            "ostype": "l26",
            "cpu": "x86-64-v2-AES,flags=+aes",
            "scsi0": "local-lvm:vm-100-disk-0,size=10G",
            "ide2": "local-lvm:vm-100-cloudinit,media=cdrom",
            "net0": "virtio=BC:24:11:00:01:00,bridge=vmbr0",
            "cipassword": "$5$secret$hash",
            "snaptime": 1700000000,
            "description": "Before upgrade",
        },
        "after-upgrade": {
            "cores": 4,
            "sockets": 2,
            "memory": "8192",
            "machine": "pc-q35-9.2+pve1",
            "ostype": "l26",
            "cpu": "custom-avx,flags=+aes",
            "scsi0": "local-lvm:vm-100-disk-0,size=10G",
            "virtio1": "local-lvm:vm-100-disk-1,size=20G",
            "net0": "virtio=BC:24:11:00:01:00,bridge=vmbr0",
            "net1": "virtio=BC:24:11:00:01:01,bridge=vmbr1",
            "snaptime": 1700000100,
            "vmstate": "local-lvm:vm-100-state-after-upgrade",
        },
    },
    200: {
        "base": {
            "arch": "amd64",
            "cores": 1,
            "memory": 512,
            "ostype": "debian",
            "rootfs": "local-lvm:vm-200-disk-0,size=8G",
            "mp0": "local-lvm:vm-200-disk-1,mp=/data,size=4G",
            "net0": "name=eth0,bridge=vmbr0,hwaddr=BC:24:11:00:02:00,ip=dhcp",
            "snaptime": 1700000200,
        },
    },
}

# /nodes/{node}/{type}/{vmid}/status/current of running guests. Runtime
# counters (cpu, mem, uptime, pid) must not be stored.
MOCK_GUEST_STATUS = {
    100: {
        "vmid": 100,
        "name": "web",
        "status": "running",
        "qmpstatus": "running",
        "pid": 12345,
        "uptime": 3600,
        "cpu": 0.02,
        "mem": 1073741824,
        "agent": 1,
        "spice": 1,
        "clipboard": "vnc",
        "running-machine": "pc-q35-9.2+pve1",
        "running-qemu": "9.2.0",
        "ha": {"managed": 1, "state": "started"},
        "proxmox-support": {
            "backup-fleecing": True,
            "backup-max-workers": True,
            "pbs-dirty-bitmap": True,
            "pbs-dirty-bitmap-migration": True,
            "pbs-dirty-bitmap-savevm": True,
            "pbs-library-version": "1.4.1 (UNKNOWN)",
            "pbs-masterkey": True,
            "query-bitmap-info": True,
        },
    },
    200: {
        "vmid": 200,
        "name": "ct",
        "status": "running",
        "pid": 23456,
        "uptime": 7200,
        "ha": {"managed": 0},
    },
}

# /nodes/{node}/qemu/{vmid}/cloudinit
MOCK_CLOUDINIT = {
    100: [
        {"key": "ciuser", "value": "ubuntu"},
        {"key": "cipassword", "value": "**********"},
        {"key": "citype", "value": "nocloud"},
        {"key": "ciupgrade", "value": 1},
        {"key": "nameserver", "value": "10.0.0.53"},
        {"key": "searchdomain", "value": "example.internal"},
        {"key": "ipconfig1", "value": "ip=dhcp"},
        {"key": "ipconfig0", "value": "ip=10.0.0.10/24,gw=10.0.0.1"},
        {
            "key": "sshkeys",
            "value": "ssh-ed25519%20AAAAC3NzaC1lZDI1NTE5AAAAIGCAYx0dg8vX9lsFLAXM4KpKrxWbY7mJKM6cKwWZW3ck%20test%40example%0A",
        },
        {"key": "cicustom", "pending": "user=local:snippets/user.yaml"},
    ],
}

# /nodes/{node}/lxc/{vmid}/interfaces
MOCK_CONTAINER_INTERFACES = {
    200: [
        {
            "name": "lo",
            "hwaddr": "00:00:00:00:00:00",
            "inet": "127.0.0.1/8",
            "inet6": "::1/128",
        },
        {
            "name": "eth0",
            "hwaddr": "bc:24:11:00:02:00",
            "inet": "10.0.0.20/24",
            "inet6": "fd00::20/64",
        },
    ],
    # Proxmox VE 9 shape: both the inet fields and ip-addresses, with the
    # address family as inet/inet6 and the prefix as a string.
    201: [
        {
            "name": "eth0",
            "hwaddr": "BC:24:11:00:02:01",
            "hardware-address": "BC:24:11:00:02:01",
            "inet": "10.0.0.21/24",
            "inet6": "fd00::21/64",
            "ip-addresses": [
                {"ip-address": "10.0.0.21", "prefix": "24", "ip-address-type": "inet"},
                {"ip-address": "fd00::21", "prefix": "64", "ip-address-type": "inet6"},
            ],
        },
    ],
}

# /nodes/{node}/qemu/{vmid}/agent/{command}, as the API wraps them
MOCK_AGENT_RESPONSES = {
    "get-osinfo": {"result": {"id": "ubuntu", "version-id": "24.04"}},
    "get-host-name": {"result": {"host-name": "web"}},
    "network-get-interfaces": {"result": []},
    "get-fsinfo": {
        "result": [
            {
                "name": "sda1",
                "mountpoint": "/",
                "type": "ext4",
                "total-bytes": 10000,
                "used-bytes": 4000,
                "disk": [{"serial": "drive-scsi0", "bus-type": "scsi"}],
            },
            {
                "name": "sda15",
                "mountpoint": "/boot/efi",
                "type": "vfat",
                "total-bytes": 100,
                "used-bytes": 10,
                "disk": [{"serial": "drive-scsi0"}],
            },
        ],
    },
    "get-users": {
        "result": [
            {"user": "ubuntu", "login-time": 1700000300.0},
            {"user": "ubuntu", "login-time": 1700000400.0},
            {"user": "admin", "domain": "CORP", "login-time": 1700000500.0},
        ],
    },
    "get-timezone": {"result": {"zone": "UTC", "offset": 0}},
}
