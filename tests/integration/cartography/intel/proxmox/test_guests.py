"""
Integration tests for Proxmox guest details: snapshots, cloud-init, container
IP addresses, guest agent filesystems and users, and custom CPU models.
"""

from contextlib import ExitStack
from typing import Any
from unittest.mock import MagicMock
from unittest.mock import patch

from proxmoxer.core import ResourceException

import cartography.intel.proxmox.compute as compute
import cartography.intel.proxmox.guests as guests
from cartography.graph.job import GraphJob
from cartography.models.proxmox.guests import ProxmoxSnapshotSchema
from tests.data.proxmox.guests import MOCK_AGENT_RESPONSES
from tests.data.proxmox.guests import MOCK_CLOUDINIT
from tests.data.proxmox.guests import MOCK_CONTAINER_INTERFACES
from tests.data.proxmox.guests import MOCK_CUSTOM_CPU_MODELS
from tests.data.proxmox.guests import MOCK_GUEST_CONFIG
from tests.data.proxmox.guests import MOCK_GUEST_LIST
from tests.data.proxmox.guests import MOCK_GUEST_RESOURCES
from tests.data.proxmox.guests import MOCK_GUEST_STATUS
from tests.data.proxmox.guests import MOCK_SNAPSHOT_CONFIGS
from tests.data.proxmox.guests import MOCK_SNAPSHOTS
from tests.data.proxmox.guests import MOCK_SSH_FINGERPRINT
from tests.integration.util import check_nodes
from tests.integration.util import check_rels

TEST_UPDATE_TAG = 123456789
TEST_CLUSTER_ID = "test-cluster"
VM = f"{TEST_CLUSTER_ID}/node1/qemu/100"
CT = f"{TEST_CLUSTER_ID}/node2/lxc/200"


def _proxmox_client() -> MagicMock:
    """Client whose guest agent commands answer from MOCK_AGENT_RESPONSES."""
    proxmox = MagicMock()
    proxmox.nodes.get.return_value = [{"node": "node1"}, {"node": "node2"}]

    def agent(command: str) -> MagicMock:
        endpoint = MagicMock()
        endpoint.get.return_value = MOCK_AGENT_RESPONSES[command]
        return endpoint

    proxmox.nodes.return_value.qemu.return_value.agent.side_effect = agent
    return proxmox


def _snapshot_config(_c: Any, _n: str, vmid: int, _t: str, name: str) -> dict:
    return MOCK_SNAPSHOT_CONFIGS[vmid][name]


def _sync(
    neo4j_session,
    update_tag: int,
    snapshots: dict[int, list] | None = None,
    guest_status: Any = None,
    snapshot_config: Any = None,
):
    snapshots = MOCK_SNAPSHOTS if snapshots is None else snapshots
    guest_status = guest_status or (lambda c, n, vmid, t: MOCK_GUEST_STATUS[vmid])
    snapshot_config = snapshot_config or _snapshot_config
    proxmox = _proxmox_client()
    patches: list[tuple[Any, str, Any]] = [
        (
            compute,
            "get_vms_for_node",
            lambda c, node: [
                dict(g) for g in MOCK_GUEST_LIST[node] if g["type"] == "qemu"
            ],
        ),
        (
            compute,
            "get_containers_for_node",
            lambda c, node: [
                dict(g) for g in MOCK_GUEST_LIST[node] if g["type"] == "lxc"
            ],
        ),
        (compute, "get_vm_config", lambda c, n, vmid, t: MOCK_GUEST_CONFIG[vmid]),
        (guests, "get_guest_resources", lambda c: MOCK_GUEST_RESOURCES),
        (guests, "get_custom_cpu_models", lambda c: MOCK_CUSTOM_CPU_MODELS),
        (guests, "get_guest_snapshots", lambda c, n, vmid, t: snapshots[vmid]),
        (guests, "get_snapshot_config", snapshot_config),
        (guests, "get_guest_status", guest_status),
        (guests, "get_vm_cloudinit", lambda c, n, vmid: MOCK_CLOUDINIT[vmid]),
        (
            guests,
            "get_container_interfaces",
            lambda c, n, vmid: MOCK_CONTAINER_INTERFACES[vmid],
        ),
    ]
    with ExitStack() as stack:
        for module, name, fake in patches:
            stack.enter_context(patch.object(module, name, side_effect=fake))
        guests.sync_custom_cpu_models(
            neo4j_session, proxmox, TEST_CLUSTER_ID, update_tag
        )
        compute.sync(
            neo4j_session,
            proxmox,
            TEST_CLUSTER_ID,
            update_tag,
            {"UPDATE_TAG": update_tag, "CLUSTER_ID": TEST_CLUSTER_ID},
            enable_guest_agent=True,
        )


def vm_support(neo4j_session) -> list[str]:
    return neo4j_session.run(
        "MATCH (v:ProxmoxVM {id: $id}) RETURN v.proxmox_support AS s", id=VM
    ).single()["s"]


def test_guest_status_and_snapshot_config_errors_are_skipped(neo4j_session, caplog):
    # Arrange
    neo4j_session.run("MATCH (n) DETACH DELETE n")
    neo4j_session.run("MERGE (:ProxmoxCluster {id: $id})", id=TEST_CLUSTER_ID)

    def failing_status(_c: Any, _n: str, vmid: int, _t: str) -> dict:
        if vmid == 100:
            raise ResourceException(500, "Internal Server Error", "QMP timeout")
        return MOCK_GUEST_STATUS[vmid]

    def failing_config(c: Any, n: str, vmid: int, t: str, name: str) -> dict:
        if name == "base":
            raise ResourceException(403, "Forbidden", "Permission check failed")
        return _snapshot_config(c, n, vmid, t, name)

    # Act
    _sync(
        neo4j_session,
        TEST_UPDATE_TAG,
        guest_status=failing_status,
        snapshot_config=failing_config,
    )

    # Assert - every guest and snapshot is synced, without the failed values
    assert check_nodes(neo4j_session, "ProxmoxVM", ["id", "ha_managed"]) == {
        (VM, None),
        (CT, False),
    }
    assert check_nodes(neo4j_session, "ProxmoxSnapshot", ["name", "config_cores"]) == {
        ("before-upgrade", 2),
        ("after-upgrade", 4),
        ("base", None),
    }
    assert "Could not read the status of qemu guest 100" in caplog.text
    assert "Could not read the configuration of snapshot base" in caplog.text


def test_sync_guest_details(neo4j_session):
    # Arrange
    neo4j_session.run("MATCH (n) DETACH DELETE n")
    neo4j_session.run("MERGE (:ProxmoxCluster {id: $id})", id=TEST_CLUSTER_ID)

    # Act
    _sync(neo4j_session, TEST_UPDATE_TAG)

    # Assert - guest detail properties on the VM and the container
    assert check_nodes(
        neo4j_session,
        "ProxmoxVM",
        [
            "id",
            "hastate",
            "pool",
            "qmpstatus",
            "running_machine",
            "running_qemu",
            "custom_cpu_model",
        ],
    ) == {
        (VM, "started", "prod", "running", "pc-q35-9.2+pve1", "9.2.0", "avx"),
        (CT, None, None, None, None, None, None),
    }
    vm = neo4j_session.run("MATCH (v:ProxmoxVM {id: $id}) RETURN v", id=VM).single()[
        "v"
    ]
    assert vm["cloudinit_user"] == "ubuntu"
    assert vm["cloudinit_password_set"] is True
    assert vm["cloudinit_ssh_key_count"] == 1
    assert vm["cloudinit_ssh_key_fingerprints"] == [MOCK_SSH_FINGERPRINT]
    assert vm["cloudinit_ipconfig"] == [
        "ipconfig0=ip=10.0.0.10/24,gw=10.0.0.1",
        "ipconfig1=ip=dhcp",
    ]
    assert vm["guest_users"] == ["CORP\\admin", "ubuntu"]
    assert vm["guest_timezone"] == "UTC"
    assert vm["guest_timezone_offset"] == 0

    # Assert - snapshots, linked to their guest and their parent
    assert check_nodes(
        neo4j_session, "ProxmoxSnapshot", ["id", "name", "vmstate", "cluster_id"]
    ) == {
        (f"{VM}/snapshot/before-upgrade", "before-upgrade", False, TEST_CLUSTER_ID),
        (f"{VM}/snapshot/after-upgrade", "after-upgrade", True, TEST_CLUSTER_ID),
        (f"{CT}/snapshot/base", "base", None, TEST_CLUSTER_ID),
    }
    assert check_rels(
        neo4j_session,
        "ProxmoxVM",
        "id",
        "ProxmoxSnapshot",
        "id",
        "HAS_SNAPSHOT",
    ) == {
        (VM, f"{VM}/snapshot/before-upgrade"),
        (VM, f"{VM}/snapshot/after-upgrade"),
        (CT, f"{CT}/snapshot/base"),
    }
    assert check_rels(
        neo4j_session,
        "ProxmoxSnapshot",
        "id",
        "ProxmoxSnapshot",
        "id",
        "HAS_PARENT",
    ) == {(f"{VM}/snapshot/after-upgrade", f"{VM}/snapshot/before-upgrade")}

    # Assert - configuration facts saved with each snapshot, never secrets
    assert check_nodes(
        neo4j_session,
        "ProxmoxSnapshot",
        [
            "name",
            "config_cores",
            "config_memory",
            "config_ostype",
            "config_cpu_type",
            "config_disk_count",
            "config_nic_count",
        ],
    ) == {
        ("before-upgrade", 2, "4096", "l26", "x86-64-v2-AES", 1, 1),
        ("after-upgrade", 4, "8192", "l26", "custom-avx", 2, 2),
        ("base", 1, 512, "debian", None, 2, 1),
    }
    leaked = neo4j_session.run(
        """
        MATCH (s:ProxmoxSnapshot)
        UNWIND keys(s) AS key
        WITH s, key WHERE toString(s[key]) CONTAINS '$5$secret'
        RETURN count(*) AS n
        """,
    ).single()["n"]
    assert leaked == 0

    # Assert - status of the running guests: HA, display, QEMU features
    assert check_nodes(
        neo4j_session,
        "ProxmoxVM",
        ["id", "ha_managed", "ha_state", "spice", "clipboard", "pbs_library_version"],
    ) == {
        (VM, True, "started", True, "vnc", "1.4.1 (UNKNOWN)"),
        (CT, False, None, None, None, None),
    }
    assert "pbs-dirty-bitmap" in vm_support(neo4j_session)

    # Assert - container IP addresses on its configured interface
    assert check_nodes(
        neo4j_session,
        "ProxmoxNetworkInterface",
        ["id", "actual_ipv4", "actual_ipv6", "guest_interface_name"],
    ) == {
        (f"{VM}:net0", None, None, None),
        (f"{CT}:net0", "10.0.0.20/24", "fd00::20/64", "eth0"),
    }

    # Assert - guest agent filesystems
    assert check_nodes(
        neo4j_session,
        "ProxmoxGuestFilesystem",
        ["id", "type", "total_bytes", "used_bytes"],
    ) == {
        (f"{VM}:fs:/", "ext4", 10000, 4000),
        (f"{VM}:fs:/boot/efi", "vfat", 100, 10),
    }
    assert check_rels(
        neo4j_session,
        "ProxmoxVM",
        "id",
        "ProxmoxGuestFilesystem",
        "id",
        "HAS_FILESYSTEM",
    ) == {(VM, f"{VM}:fs:/"), (VM, f"{VM}:fs:/boot/efi")}

    # Assert - custom CPU model and the VM that uses it
    assert check_nodes(
        neo4j_session, "ProxmoxCustomCPUModel", ["id", "name", "reported_model"]
    ) == {(f"{TEST_CLUSTER_ID}/avx", "avx", "kvm64")}
    assert check_rels(
        neo4j_session,
        "ProxmoxVM",
        "id",
        "ProxmoxCustomCPUModel",
        "id",
        "USES_CPU_MODEL",
    ) == {(VM, f"{TEST_CLUSTER_ID}/avx")}

    # Assert - every new node belongs to the cluster
    for label in (
        "ProxmoxSnapshot",
        "ProxmoxGuestFilesystem",
        "ProxmoxCustomCPUModel",
    ):
        rels = check_rels(
            neo4j_session,
            "ProxmoxCluster",
            "id",
            label,
            "id",
            "RESOURCE",
        )
        assert rels and {cluster for cluster, _ in rels} == {TEST_CLUSTER_ID}, label


def test_cleanup_removes_deleted_snapshots(neo4j_session):
    # Arrange
    neo4j_session.run("MATCH (n) DETACH DELETE n")
    neo4j_session.run("MERGE (:ProxmoxCluster {id: $id})", id=TEST_CLUSTER_ID)
    _sync(neo4j_session, TEST_UPDATE_TAG)

    # Act - the VM's snapshots were deleted before the next sync
    new_tag = TEST_UPDATE_TAG + 1
    _sync(neo4j_session, new_tag, {100: [], 200: MOCK_SNAPSHOTS[200]})
    GraphJob.from_node_schema(
        ProxmoxSnapshotSchema(),
        {"UPDATE_TAG": new_tag, "CLUSTER_ID": TEST_CLUSTER_ID},
    ).run(neo4j_session)

    # Assert
    assert check_nodes(neo4j_session, "ProxmoxSnapshot", ["id"]) == {
        (f"{CT}/snapshot/base",),
    }
