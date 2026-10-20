"""
Unit tests for the Proxmox guest details module.
"""

from typing import Any

import pytest
from proxmoxer.core import ResourceException

from cartography.intel.proxmox import guests
from cartography.intel.proxmox.compute import enrich_interfaces_with_guest_data
from tests.data.proxmox.guests import MOCK_AGENT_RESPONSES
from tests.data.proxmox.guests import MOCK_CLOUDINIT
from tests.data.proxmox.guests import MOCK_CONTAINER_INTERFACES
from tests.data.proxmox.guests import MOCK_CUSTOM_CPU_MODELS
from tests.data.proxmox.guests import MOCK_GUEST_CONFIG
from tests.data.proxmox.guests import MOCK_GUEST_RESOURCES
from tests.data.proxmox.guests import MOCK_GUEST_STATUS
from tests.data.proxmox.guests import MOCK_SNAPSHOT_CONFIGS
from tests.data.proxmox.guests import MOCK_SNAPSHOTS
from tests.data.proxmox.guests import MOCK_SSH_FINGERPRINT
from tests.data.proxmox.guests import MOCK_SSH_PUBLIC_KEY

CLUSTER_ID = "prod"


class RecordingClient:
    """Fake proxmoxer client that records each GET path and answers from a dict."""

    def __init__(self, responses: dict[str, Any], path: str = "", calls=None):
        self._responses = responses
        self._path = path
        self.calls: list[str] = [] if calls is None else calls

    def _child(self, segment: Any) -> "RecordingClient":
        return RecordingClient(self._responses, f"{self._path}/{segment}", self.calls)

    def __getattr__(self, name: str) -> "RecordingClient":
        return self._child(name)

    def __call__(self, segment: Any) -> "RecordingClient":
        return self._child(segment)

    def get(self, **params: Any) -> Any:
        self.calls.append(self._path)
        response = self._responses.get(self._path)
        if isinstance(response, Exception):
            raise response
        return response


def test_custom_cpu_model_name():
    assert guests.custom_cpu_model_name("custom-avx,flags=+aes") == "avx"
    assert guests.custom_cpu_model_name("flags=+aes,cputype=custom-avx") == "avx"
    assert guests.custom_cpu_model_name("host") is None
    assert guests.custom_cpu_model_name("x86-64-v2-AES,flags=+aes") is None
    assert guests.custom_cpu_model_name(None) is None


def test_ssh_key_fingerprint_matches_ssh_keygen():
    assert guests.ssh_key_fingerprint(MOCK_SSH_PUBLIC_KEY) == MOCK_SSH_FINGERPRINT
    # authorized_keys options before the key type are skipped
    assert (
        guests.ssh_key_fingerprint(f'from="10.0.0.0/8" {MOCK_SSH_PUBLIC_KEY}')
        == MOCK_SSH_FINGERPRINT
    )
    assert guests.ssh_key_fingerprint("not a key") is None


def test_transform_cloudinit_keeps_current_values_and_no_secrets():
    props = guests.transform_cloudinit(MOCK_CLOUDINIT[100])

    assert props == {
        "cloudinit_user": "ubuntu",
        "cloudinit_type": "nocloud",
        # only pending, so not part of the current image
        "cloudinit_custom": None,
        "cloudinit_upgrade": True,
        "cloudinit_nameserver": "10.0.0.53",
        "cloudinit_searchdomain": "example.internal",
        "cloudinit_ipconfig": [
            "ipconfig0=ip=10.0.0.10/24,gw=10.0.0.1",
            "ipconfig1=ip=dhcp",
        ],
        "cloudinit_password_set": True,
        "cloudinit_ssh_key_count": 1,
        "cloudinit_ssh_key_fingerprints": [MOCK_SSH_FINGERPRINT],
    }
    assert "**********" not in str(props)
    assert "AAAAC3" not in str(props)


def test_transform_cloudinit_empty():
    props = guests.transform_cloudinit([])
    assert props["cloudinit_password_set"] is False
    assert props["cloudinit_ssh_key_count"] == 0
    assert props["cloudinit_ssh_key_fingerprints"] is None
    assert props["cloudinit_ipconfig"] is None


def test_has_cloudinit_drive():
    assert guests.has_cloudinit_drive(MOCK_GUEST_CONFIG[100])
    assert not guests.has_cloudinit_drive(MOCK_GUEST_CONFIG[200])
    assert not guests.has_cloudinit_drive({"ide2": "local:iso/ubuntu.iso,media=cdrom"})


def test_transform_snapshots_orders_parents_first_and_drops_current():
    snapshots = guests.transform_snapshots(
        MOCK_SNAPSHOTS[100], "node1/qemu/100", CLUSTER_ID
    )

    assert [s["name"] for s in snapshots] == ["before-upgrade", "after-upgrade"]
    before, after = snapshots
    assert before == {
        "id": "prod/node1/qemu/100/snapshot/before-upgrade",
        "name": "before-upgrade",
        "cluster_id": CLUSTER_ID,
        "vmid": 100,
        "vm_id": "prod/node1/qemu/100",
        "description": "Before upgrade",
        "snaptime": 1700000000,
        "vmstate": False,
        "parent": None,
        "parent_id": None,
        **dict.fromkeys(guests.SNAPSHOT_CONFIG_PROPERTIES),
    }
    assert after["parent_id"] == "prod/node1/qemu/100/snapshot/before-upgrade"
    assert after["vmstate"] is True


def test_transform_snapshots_adds_config_facts():
    snapshots = guests.transform_snapshots(
        MOCK_SNAPSHOTS[100], "node1/qemu/100", CLUSTER_ID, MOCK_SNAPSHOT_CONFIGS[100]
    )

    after = next(s for s in snapshots if s["name"] == "after-upgrade")
    assert after["config_cores"] == 4
    assert after["config_sockets"] == 2
    assert after["config_memory"] == "8192"
    assert after["config_machine"] == "pc-q35-9.2+pve1"
    assert after["config_cpu_type"] == "custom-avx"
    assert after["config_disk_count"] == 2
    assert after["config_nic_count"] == 2


def test_transform_snapshots_tolerates_missing_parent_and_cycles():
    snapshots = guests.transform_snapshots(
        [
            {"name": "a", "parent": "b"},
            {"name": "b", "parent": "a"},
            {"name": "c", "parent": "gone"},
        ],
        "n/lxc/200",
        CLUSTER_ID,
    )
    assert sorted(s["name"] for s in snapshots) == ["a", "b", "c"]
    c = next(s for s in snapshots if s["name"] == "c")
    assert c["parent"] == "gone"
    assert c["parent_id"] is None
    assert c["vmstate"] is None


def test_normalize_container_interfaces_from_inet_fields():
    normalized = guests.normalize_container_interfaces(MOCK_CONTAINER_INTERFACES[200])

    assert normalized[1] == {
        "name": "eth0",
        "hardware-address": "bc:24:11:00:02:00",
        "ip-addresses": [
            {"ip-address": "10.0.0.20", "prefix": 24, "ip-address-type": "ipv4"},
            {"ip-address": "fd00::20", "prefix": 64, "ip-address-type": "ipv6"},
        ],
    }


def test_normalize_container_interfaces_converts_pve9_ip_addresses():
    """Proxmox VE 9 names the family inet/inet6 and returns the prefix as a string."""
    normalized = guests.normalize_container_interfaces(MOCK_CONTAINER_INTERFACES[201])

    assert normalized[0] == {
        "name": "eth0",
        "hardware-address": "BC:24:11:00:02:01",
        "ip-addresses": [
            {"ip-address": "10.0.0.21", "prefix": 24, "ip-address-type": "ipv4"},
            {"ip-address": "fd00::21", "prefix": 64, "ip-address-type": "ipv6"},
        ],
    }


def test_container_interface_ips_reach_configured_interface():
    """Normalized container addresses fill the actual IPs of the configured NIC."""
    interfaces = [{"mac_address": "BC:24:11:00:02:01"}]

    enrich_interfaces_with_guest_data(
        interfaces,
        guests.normalize_container_interfaces(MOCK_CONTAINER_INTERFACES[201]),
    )

    assert interfaces[0]["actual_ipv4"] == "10.0.0.21/24"
    assert interfaces[0]["actual_ipv6"] == "fd00::21/64"
    assert interfaces[0]["guest_interface_name"] == "eth0"


def test_transform_filesystems():
    filesystems = guests.transform_filesystems(
        MOCK_AGENT_RESPONSES["get-fsinfo"]["result"]
        + [{"name": "dup", "mountpoint": "/"}],
        "node1/qemu/100",
        CLUSTER_ID,
    )
    assert filesystems[0] == {
        "id": "prod/node1/qemu/100:fs:/",
        "mountpoint": "/",
        "cluster_id": CLUSTER_ID,
        "vmid": 100,
        "vm_id": "prod/node1/qemu/100",
        "name": "sda1",
        "type": "ext4",
        "total_bytes": 10000,
        "used_bytes": 4000,
        "disk_serials": ["drive-scsi0"],
    }
    assert [f["mountpoint"] for f in filesystems] == ["/", "/boot/efi"]


def test_transform_guest_users():
    users = guests.transform_guest_users(MOCK_AGENT_RESPONSES["get-users"]["result"])
    assert users == ["CORP\\admin", "ubuntu"]
    assert guests.transform_guest_users([]) is None


def test_transform_custom_cpu_models():
    assert guests.transform_custom_cpu_models(MOCK_CUSTOM_CPU_MODELS, CLUSTER_ID) == [
        {
            "id": "prod/avx",
            "name": "avx",
            "cluster_id": CLUSTER_ID,
            "reported_model": "kvm64",
            "flags": "+avx;+avx2",
            "hidden": False,
            "phys_bits": "host",
            "guest_phys_bits": None,
            "hv_vendor_id": "proxmox",
            "level": None,
        },
    ]


def test_index_guest_resources():
    indexed = guests.index_guest_resources(
        MOCK_GUEST_RESOURCES + [{"type": "storage", "id": "storage/pve/local"}],
    )
    assert set(indexed) == {100, 200}
    assert indexed[100]["hastate"] == "started"


def _vm(vmid: int, vm_type: str, status: str, **extra: Any) -> dict[str, Any]:
    return {"vmid": vmid, "type": vm_type, "node": "pve", "status": status, **extra}


def _responses() -> dict[str, Any]:
    responses: dict[str, Any] = {
        "/nodes/pve/qemu/100/snapshot": MOCK_SNAPSHOTS[100],
        "/nodes/pve/qemu/100/cloudinit": MOCK_CLOUDINIT[100],
        "/nodes/pve/lxc/200/snapshot": MOCK_SNAPSHOTS[200],
        "/nodes/pve/lxc/200/interfaces": MOCK_CONTAINER_INTERFACES[200],
    }
    for command, response in MOCK_AGENT_RESPONSES.items():
        responses[f"/nodes/pve/qemu/100/agent/{command}"] = response
    for vmid, vm_type in ((100, "qemu"), (200, "lxc")):
        responses[f"/nodes/pve/{vm_type}/{vmid}/status/current"] = MOCK_GUEST_STATUS[
            vmid
        ]
        for name, config in MOCK_SNAPSHOT_CONFIGS[vmid].items():
            responses[f"/nodes/pve/{vm_type}/{vmid}/snapshot/{name}/config"] = config
    return responses


@pytest.mark.parametrize("agent", [False, True])
def test_collect_guest_details_vm_api_calls(agent):
    client = RecordingClient(_responses())
    vm = _vm(100, "qemu", "running", agent_enabled=agent)

    details = guests.collect_guest_details(
        client,
        vm,
        MOCK_GUEST_CONFIG[100],
        CLUSTER_ID,
        guests.index_guest_resources(MOCK_GUEST_RESOURCES),
        enable_guest_agent=agent,
    )

    expected_calls = [
        "/nodes/pve/qemu/100/status/current",
        "/nodes/pve/qemu/100/snapshot",
        "/nodes/pve/qemu/100/snapshot/after-upgrade/config",
        "/nodes/pve/qemu/100/snapshot/before-upgrade/config",
        "/nodes/pve/qemu/100/cloudinit",
    ]
    if agent:
        expected_calls += [
            "/nodes/pve/qemu/100/agent/get-fsinfo",
            "/nodes/pve/qemu/100/agent/get-users",
            "/nodes/pve/qemu/100/agent/get-timezone",
        ]
    assert client.calls == expected_calls
    assert len(details.snapshots) == 2
    assert vm["hastate"] == "started"
    assert vm["pool"] == "prod"
    assert vm["custom_cpu_model"] == "avx"
    assert vm["custom_cpu_model_id"] == "prod/avx"
    assert vm["cloudinit_user"] == "ubuntu"
    if agent:
        assert len(details.filesystems) == 2
        assert vm["guest_users"] == ["CORP\\admin", "ubuntu"]
        assert vm["guest_timezone"] == "UTC"
        assert vm["guest_timezone_offset"] == 0
    else:
        assert details.filesystems == []
        assert vm["guest_users"] is None


def test_collect_guest_details_container_api_calls():
    client = RecordingClient(_responses())
    ct = _vm(200, "lxc", "running")

    details = guests.collect_guest_details(
        client,
        ct,
        MOCK_GUEST_CONFIG[200],
        CLUSTER_ID,
        {},
        enable_guest_agent=True,
    )

    assert client.calls == [
        "/nodes/pve/lxc/200/status/current",
        "/nodes/pve/lxc/200/snapshot",
        "/nodes/pve/lxc/200/snapshot/base/config",
        "/nodes/pve/lxc/200/interfaces",
    ]
    assert [i["name"] for i in details.container_interfaces] == ["lo", "eth0"]
    assert ct["hastate"] is None
    assert ct["cloudinit_user"] is None
    assert ct["ha_managed"] is False
    assert ct["ha_state"] is None
    assert ct["spice"] is None
    assert details.snapshots[0]["config_disk_count"] == 2
    assert details.snapshots[0]["config_nic_count"] == 1
    assert details.snapshots[0]["config_cpu_type"] is None


def test_collect_guest_details_stopped_guests_skip_runtime_calls():
    client = RecordingClient(_responses())
    guests.collect_guest_details(
        client,
        _vm(200, "lxc", "stopped"),
        MOCK_GUEST_CONFIG[200],
        CLUSTER_ID,
        {},
        enable_guest_agent=True,
    )
    assert client.calls == [
        "/nodes/pve/lxc/200/snapshot",
        "/nodes/pve/lxc/200/snapshot/base/config",
    ]


def test_collect_guest_details_reads_status_of_stopped_ha_guest():
    # A stopped guest that HA manages, here in the error state, still gets its
    # HA status; a stopped guest without HA does not (see the test above).
    responses = _responses()
    responses["/nodes/pve/qemu/100/status/current"] = {
        "status": "stopped",
        "ha": {"managed": 1, "state": "error", "group": "prod-ha"},
    }
    client = RecordingClient(responses)
    vm = _vm(100, "qemu", "stopped")

    guests.collect_guest_details(
        client,
        vm,
        MOCK_GUEST_CONFIG[100],
        CLUSTER_ID,
        guests.index_guest_resources(
            [{"type": "qemu", "vmid": 100, "node": "pve", "hastate": "error"}],
        ),
        enable_guest_agent=False,
    )

    assert client.calls[0] == "/nodes/pve/qemu/100/status/current"
    assert vm["hastate"] == "error"
    assert vm["ha_managed"] is True
    assert vm["ha_state"] == "error"
    assert vm["ha_group"] == "prod-ha"


def test_collect_guest_details_reads_status_of_running_vm():
    client = RecordingClient(_responses())
    # The list already has the running machine; the status fills the rest.
    vm = _vm(100, "qemu", "running", **{"running-machine": "pc-q35-9.0"})

    guests.collect_guest_details(
        client, vm, MOCK_GUEST_CONFIG[100], CLUSTER_ID, {}, enable_guest_agent=False
    )

    assert vm["ha_managed"] is True
    assert vm["ha_state"] == "started"
    assert vm["ha_group"] is None
    assert vm["ha_request"] is None
    assert vm["spice"] is True
    assert vm["clipboard"] == "vnc"
    assert vm["running_machine"] == "pc-q35-9.0"
    assert vm["running_qemu"] == "9.2.0"
    assert vm["pbs_library_version"] == "1.4.1 (UNKNOWN)"
    assert vm["proxmox_support"] == [
        "backup-fleecing",
        "backup-max-workers",
        "pbs-dirty-bitmap",
        "pbs-dirty-bitmap-migration",
        "pbs-dirty-bitmap-savevm",
        "pbs-masterkey",
        "query-bitmap-info",
    ]
    # Runtime counters are not copied
    assert "pid" not in guests.GUEST_DETAIL_PROPERTIES
    assert vm.get("uptime") is None


def test_transform_guest_status_older_ha_manager_fields():
    result = guests.transform_guest_status(
        {"ha": {"managed": 1, "state": "started", "group": "g1", "request": "x"}},
    )
    assert result["ha_group"] == "g1"
    assert result["ha_request"] == "x"
    assert result["proxmox_support"] is None
    assert guests.transform_guest_status({})["ha_managed"] is None


def test_collect_guest_details_status_and_snapshot_config_errors_are_skipped(caplog):
    responses = _responses()
    responses["/nodes/pve/qemu/100/status/current"] = ResourceException(
        500, "Internal Server Error", "VM 100 not running"
    )
    responses["/nodes/pve/qemu/100/snapshot/before-upgrade/config"] = ResourceException(
        500, "Internal Server Error", "snapshot does not exist"
    )
    vm = _vm(100, "qemu", "running")

    details = guests.collect_guest_details(
        RecordingClient(responses),
        vm,
        MOCK_GUEST_CONFIG[100],
        CLUSTER_ID,
        {},
        enable_guest_agent=False,
    )

    assert vm["ha_managed"] is None
    assert vm["spice"] is None
    by_name = {s["name"]: s for s in details.snapshots}
    assert by_name["before-upgrade"]["config_cores"] is None
    assert by_name["after-upgrade"]["config_cores"] == 4
    assert "Could not read the status of qemu guest 100" in caplog.text
    assert "Could not read the configuration of snapshot before-upgrade" in caplog.text


def test_transform_snapshot_config_vm_keeps_facts_only():
    result = guests.transform_snapshot_config(
        MOCK_SNAPSHOT_CONFIGS[100]["before-upgrade"], "qemu"
    )
    assert result == {
        "config_cores": 2,
        "config_sockets": 1,
        "config_memory": "4096",
        "config_machine": "pc-q35-8.1",
        "config_ostype": "l26",
        "config_cpu_type": "x86-64-v2-AES",
        # ide2 is a CD-ROM (cloud-init drive) and is not counted
        "config_disk_count": 1,
        "config_nic_count": 1,
    }
    assert "$5$secret$hash" not in str(result)


def test_cpu_type():
    assert guests.cpu_type("x86-64-v2-AES,flags=+aes") == "x86-64-v2-AES"
    assert guests.cpu_type("flags=+aes,cputype=host") == "host"
    assert guests.cpu_type(None) is None
    assert guests.cpu_type("") is None


def test_collect_guest_details_agent_errors_are_skipped():
    responses = _responses()
    responses["/nodes/pve/qemu/100/agent/get-users"] = ResourceException(
        500, "Internal Server Error", "command not supported"
    )
    client = RecordingClient(responses)
    vm = _vm(100, "qemu", "running", agent_enabled=True)

    details = guests.collect_guest_details(
        client,
        vm,
        MOCK_GUEST_CONFIG[100],
        CLUSTER_ID,
        {},
        enable_guest_agent=True,
    )

    assert vm["guest_users"] is None
    assert vm["guest_timezone"] == "UTC"
    assert len(details.filesystems) == 2


def test_collect_guest_details_snapshot_errors_propagate():
    responses = _responses()
    responses["/nodes/pve/qemu/100/snapshot"] = ResourceException(
        403, "Forbidden", "Permission check failed"
    )
    with pytest.raises(ResourceException):
        guests.collect_guest_details(
            RecordingClient(responses),
            _vm(100, "qemu", "stopped"),
            {},
            CLUSTER_ID,
            {},
            enable_guest_agent=False,
        )


def test_get_custom_cpu_models_missing_on_proxmox_8():
    client = RecordingClient(
        {
            "/cluster/qemu/custom-cpu-models": ResourceException(
                501, "Not Implemented", "Method not implemented"
            ),
        },
    )
    assert guests.get_custom_cpu_models(client) == []
