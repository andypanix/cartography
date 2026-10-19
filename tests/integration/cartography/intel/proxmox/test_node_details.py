"""
Integration tests for the Proxmox node hardware, software and system details sync.
"""

from contextlib import ExitStack
from typing import Any
from unittest.mock import MagicMock
from unittest.mock import patch

from proxmoxer.core import ResourceException

import cartography.intel.proxmox.cluster
import cartography.intel.proxmox.node_details as node_details
from tests.data.proxmox import node_details as data
from tests.integration.util import check_nodes
from tests.integration.util import check_rels

TEST_UPDATE_TAG = 123456789
TEST_CLUSTER_ID = "test-cluster"
NODE_ID = "test-cluster/node1"


def _getters(nodes: list[dict[str, Any]]) -> list[tuple[Any, str, Any]]:
    """Mocked getters as (module, name, side effect or return value)."""
    return [
        (cartography.intel.proxmox.cluster, "get_nodes", nodes),
        (node_details, "get_node_disks", data.MOCK_DISKS),
        (
            node_details,
            "get_disk_smart",
            lambda client, node, devpath: data.MOCK_SMART[devpath],
        ),
        (node_details, "get_zfs_pools", data.MOCK_ZFS_POOLS),
        (
            node_details,
            "get_zfs_pool_details",
            lambda client, node, name: data.MOCK_ZFS_POOL_DETAILS[name],
        ),
        (node_details, "get_lvm_volume_groups", data.MOCK_LVM),
        (node_details, "get_lvm_thin_pools", data.MOCK_LVM_THIN),
        (node_details, "get_managed_directories", data.MOCK_DIRECTORIES),
        (node_details, "get_package_versions", data.MOCK_PACKAGE_VERSIONS),
        (node_details, "get_apt_repositories", data.MOCK_APT_REPOSITORIES),
        (node_details, "get_subscription", data.MOCK_SUBSCRIPTION),
        (node_details, "get_node_config", data.MOCK_NODE_CONFIG),
        (node_details, "get_node_dns", data.MOCK_NODE_DNS),
        (node_details, "get_node_time", data.MOCK_NODE_TIME),
        (node_details, "get_node_services", data.MOCK_SERVICES),
        (node_details, "get_pci_devices", data.MOCK_PCI_DEVICES),
        (
            node_details,
            "get_pci_mdev_types",
            lambda client, node, pci_id: data.MOCK_PCI_MDEV_TYPES[pci_id],
        ),
    ]


def _sync(
    neo4j_session,
    update_tag: int,
    nodes: list[dict[str, Any]],
    overrides: dict[str, Any] | None = None,
) -> dict:
    mocks = {}
    with ExitStack() as stack:
        for module, name, value in _getters(nodes):
            value = (overrides or {}).get(name, value)
            kwargs = (
                {"side_effect": value} if callable(value) else {"return_value": value}
            )
            mocks[name] = stack.enter_context(patch.object(module, name, **kwargs))
        node_details.sync(
            neo4j_session,
            MagicMock(),
            TEST_CLUSTER_ID,
            update_tag,
            {"UPDATE_TAG": update_tag, "CLUSTER_ID": TEST_CLUSTER_ID},
        )
    return mocks


def _seed(neo4j_session) -> None:
    neo4j_session.run("MATCH (n) DETACH DELETE n")
    neo4j_session.run(
        """
        MERGE (c:ProxmoxCluster {id: $cluster_id})
        SET c.lastupdated = $tag
        MERGE (n1:ProxmoxNode {id: 'test-cluster/node1'})
        SET n1.name = 'node1', n1.lastupdated = $tag
        MERGE (n2:ProxmoxNode {id: 'test-cluster/node2'})
        SET n2.name = 'node2', n2.lastupdated = $tag
        """,
        cluster_id=TEST_CLUSTER_ID,
        tag=TEST_UPDATE_TAG,
    )


def _node_rels(neo4j_session, rel: str, label: str) -> set[tuple[str, str]]:
    return check_rels(
        neo4j_session,
        "ProxmoxNode",
        "id",
        label,
        "id",
        rel,
        rel_direction_right=True,
    )


def test_sync_node_details(neo4j_session):
    # Arrange
    _seed(neo4j_session)

    # Act
    mocks = _sync(neo4j_session, TEST_UPDATE_TAG, data.MOCK_NODES)

    # Assert - the offline node is not queried
    assert {c.args[1] for c in mocks["get_node_disks"].call_args_list} == {"node1"}
    assert mocks["get_disk_smart"].call_count == len(data.MOCK_DISKS)
    # mdev types are read only for the mdev-capable GPU
    assert [c.args[2] for c in mocks["get_pci_mdev_types"].call_args_list] == [
        "0000:01:00.0",
    ]

    # Assert - disks
    assert check_nodes(
        neo4j_session,
        "ProxmoxPhysicalDisk",
        ["id", "name", "serial", "health", "power_on_hours", "percentage_used"],
    ) == {
        ("test-cluster/node1:/dev/sda", "sda", "S6PTNM0R123456", "PASSED", 12045, 2),
        ("test-cluster/node1:/dev/sdb", "sdb", "S6PTNM0R654321", "PASSED", 12001, 5),
        (
            "test-cluster/node1:/dev/nvme0n1",
            "nvme0n1",
            "S4EWNX0R111111",
            "PASSED",
            8760,
            3,
        ),
        ("test-cluster/node1:/dev/sdc", "sdc", "ZC1XYZ00", "PASSED", None, None),
    }
    disk_ids = {
        f"test-cluster/node1:/dev/{d}" for d in ("sda", "sdb", "nvme0n1", "sdc")
    }
    assert _node_rels(neo4j_session, "HAS_PHYSICAL_DISK", "ProxmoxPhysicalDisk") == {
        (NODE_ID, d) for d in disk_ids
    }

    # Assert - ZFS pool and its member disks
    assert check_nodes(
        neo4j_session,
        "ProxmoxZFSPool",
        ["id", "state", "health"],
    ) == {("test-cluster/node1:zfs:rpool", "DEGRADED", "DEGRADED")}
    assert neo4j_session.run(
        "MATCH (p:ProxmoxZFSPool) RETURN p.degraded_devices AS d",
    ).single()["d"] == ["wwn-0x5002538f4210dcba-part3"]
    assert _node_rels(neo4j_session, "HAS_ZFS_POOL", "ProxmoxZFSPool") == {
        (NODE_ID, "test-cluster/node1:zfs:rpool"),
    }
    assert check_rels(
        neo4j_session,
        "ProxmoxZFSPool",
        "id",
        "ProxmoxPhysicalDisk",
        "id",
        "USES_DISK",
        rel_direction_right=True,
    ) == {
        ("test-cluster/node1:zfs:rpool", "test-cluster/node1:/dev/sda"),
        ("test-cluster/node1:zfs:rpool", "test-cluster/node1:/dev/sdb"),
    }

    # Assert - LVM and managed directories
    assert check_rels(
        neo4j_session,
        "ProxmoxLVMVolumeGroup",
        "id",
        "ProxmoxPhysicalDisk",
        "id",
        "USES_DISK",
        rel_direction_right=True,
    ) == {("test-cluster/node1:lvm:pve", "test-cluster/node1:/dev/nvme0n1")}
    assert check_rels(
        neo4j_session,
        "ProxmoxLVMVolumeGroup",
        "id",
        "ProxmoxLVMThinPool",
        "id",
        "CONTAINS_THIN_POOL",
        rel_direction_right=True,
    ) == {("test-cluster/node1:lvm:pve", "test-cluster/node1:lvmthin:pve/data")}
    assert _node_rels(neo4j_session, "HAS_LVM_THIN_POOL", "ProxmoxLVMThinPool") == {
        (NODE_ID, "test-cluster/node1:lvmthin:pve/data"),
    }
    assert check_rels(
        neo4j_session,
        "ProxmoxManagedDirectory",
        "id",
        "ProxmoxPhysicalDisk",
        "id",
        "USES_DISK",
        rel_direction_right=True,
    ) == {
        (
            "test-cluster/node1:directory:/mnt/pve/backup",
            "test-cluster/node1:/dev/sdc",
        ),
    }

    # Assert - software
    assert check_nodes(
        neo4j_session,
        "ProxmoxPackage",
        ["name", "version", "running_kernel"],
    ) == {
        ("proxmox-ve", "9.0.0", "6.14.8-2-pve"),
        ("pve-manager", "9.0.10", None),
        ("qemu-server", "9.0.22", None),
    }
    assert len(_node_rels(neo4j_session, "HAS_PACKAGE", "ProxmoxPackage")) == 3
    assert check_nodes(
        neo4j_session,
        "ProxmoxAPTRepository",
        ["path", "index", "enabled"],
    ) == {
        ("/etc/apt/sources.list.d/pve-enterprise.sources", 0, False),
        ("/etc/apt/sources.list", 0, True),
        ("/etc/apt/sources.list", 1, True),
    }
    assert check_nodes(
        neo4j_session,
        "ProxmoxSubscription",
        ["id", "status", "level", "key_suffix"],
    ) == {("test-cluster/node1:subscription", "active", "c", "89ab")}
    stored = neo4j_session.run(
        "MATCH (s:ProxmoxSubscription) RETURN properties(s) AS p",
    ).single()["p"]
    assert "key" not in stored
    assert "signature" not in stored
    assert data.MOCK_SUBSCRIPTION["key"] not in stored.values()
    assert _node_rels(neo4j_session, "HAS_SUBSCRIPTION", "ProxmoxSubscription") == {
        (NODE_ID, "test-cluster/node1:subscription"),
    }

    # Assert - system
    assert check_nodes(
        neo4j_session,
        "ProxmoxNodeConfig",
        [
            "id",
            "timezone",
            "dns_search",
            "enterprise_repo_enabled",
            "no_subscription_repo_enabled",
        ],
    ) == {("test-cluster/node1:config", "Europe/Rome", "example.com", False, True)}
    assert _node_rels(neo4j_session, "HAS_CONFIG", "ProxmoxNodeConfig") == {
        (NODE_ID, "test-cluster/node1:config"),
    }
    assert check_nodes(
        neo4j_session,
        "ProxmoxService",
        ["name", "state", "active_state", "unit_state"],
    ) == {
        ("pveproxy", "running", "active", "enabled"),
        ("corosync", "dead", "inactive", "disabled"),
    }
    assert check_nodes(
        neo4j_session,
        "ProxmoxPCIDevice",
        ["pci_id", "iommu_group", "mdev", "mdev_available"],
    ) == {("0000:01:00.0", 14, True, 24), ("0000:02:00.0", 15, False, None)}
    assert len(_node_rels(neo4j_session, "HAS_PCI_DEVICE", "ProxmoxPCIDevice")) == 2

    # Assert - every new node hangs off the cluster
    for schema in node_details.NODE_DETAIL_SCHEMAS:
        rels = check_rels(
            neo4j_session,
            "ProxmoxCluster",
            "id",
            schema.label,
            "id",
            "RESOURCE",
            rel_direction_right=True,
        )
        assert rels, schema.label
        assert {c for c, _ in rels} == {TEST_CLUSTER_ID}, schema.label


def test_node_details_cleanup_when_node_goes_offline(neo4j_session):
    # Arrange
    _seed(neo4j_session)
    _sync(neo4j_session, TEST_UPDATE_TAG, [{"node": "node1", "status": "online"}])
    assert check_nodes(neo4j_session, "ProxmoxPhysicalDisk", ["id"])

    # Act - node1 is offline in the next sync
    _sync(neo4j_session, TEST_UPDATE_TAG + 1, [{"node": "node1", "status": "offline"}])

    # Assert - its details are removed
    for schema in node_details.NODE_DETAIL_SCHEMAS:
        assert check_nodes(neo4j_session, schema.label, ["id"]) == set(), schema.label


def _api_error(status_code: int) -> ResourceException:
    return ResourceException(status_code, "error", "mocked API error")


def test_smart_error_keeps_disk_without_smart_values(neo4j_session):
    # Arrange - smartctl cannot open the RAID virtual disk /dev/sdc
    _seed(neo4j_session)

    def smart(client, node, devpath):
        if devpath == "/dev/sdc":
            raise _api_error(500)
        return data.MOCK_SMART[devpath]

    # Act
    _sync(
        neo4j_session,
        TEST_UPDATE_TAG,
        [{"node": "node1", "status": "online"}],
        {"get_disk_smart": smart},
    )

    # Assert - every disk is loaded, sdc without SMART values
    assert check_nodes(
        neo4j_session,
        "ProxmoxPhysicalDisk",
        ["name", "smart_health", "power_on_hours"],
    ) == {
        ("sda", "PASSED", 12045),
        ("sdb", "PASSED", 12001),
        ("nvme0n1", "PASSED", 8760),
        ("sdc", None, None),
    }
    # The rest of the node is synced
    assert check_nodes(neo4j_session, "ProxmoxZFSPool", ["id"])
    assert check_nodes(neo4j_session, "ProxmoxPCIDevice", ["id"])


def test_mdev_error_keeps_pci_device_without_mdev_types(neo4j_session):
    # Arrange
    _seed(neo4j_session)

    def mdev(client, node, pci_id):
        raise _api_error(500)

    # Act
    _sync(
        neo4j_session,
        TEST_UPDATE_TAG,
        [{"node": "node1", "status": "online"}],
        {"get_pci_mdev_types": mdev},
    )

    # Assert - the GPU is loaded, without mdev types
    assert check_nodes(
        neo4j_session,
        "ProxmoxPCIDevice",
        ["pci_id", "mdev", "mdev_types", "mdev_available"],
    ) == {
        ("0000:01:00.0", True, None, None),
        ("0000:02:00.0", False, None, None),
    }


def test_node_error_keeps_previous_details_of_that_node(neo4j_session):
    # Arrange - both nodes synced once
    _seed(neo4j_session)
    both_online = [
        {"node": "node1", "status": "online"},
        {"node": "node2", "status": "online"},
    ]
    _sync(neo4j_session, TEST_UPDATE_TAG, both_online)
    node2_details = {
        schema.label: check_nodes(
            neo4j_session,
            schema.label,
            ["id", "node_name"],
        )
        for schema in node_details.NODE_DETAIL_SCHEMAS
    }

    # Act - node2 is unreachable in the next sync
    def disks(client, node):
        if node == "node2":
            raise _api_error(595)
        return data.MOCK_DISKS

    mocks = _sync(
        neo4j_session,
        TEST_UPDATE_TAG + 1,
        both_online,
        {"get_node_disks": disks},
    )

    # Assert - node1 is refreshed, node2 is not queried further and keeps its
    # previous details with the old update tag
    assert mocks["get_node_config"].call_count == 1
    for schema in node_details.NODE_DETAIL_SCHEMAS:
        assert (
            check_nodes(neo4j_session, schema.label, ["id", "node_name"])
            == node2_details[schema.label]
        ), schema.label
    assert check_nodes(
        neo4j_session,
        "ProxmoxPhysicalDisk",
        ["node_name", "lastupdated"],
    ) == {("node1", TEST_UPDATE_TAG + 1), ("node2", TEST_UPDATE_TAG)}

    # Act - node2 answers again but has no disks any more
    def disks_back(client, node):
        return [] if node == "node2" else data.MOCK_DISKS

    _sync(
        neo4j_session,
        TEST_UPDATE_TAG + 2,
        both_online,
        {"get_node_disks": disks_back},
    )

    # Assert - the cleanup runs again and removes the stale node2 disks
    assert check_nodes(neo4j_session, "ProxmoxPhysicalDisk", ["node_name"]) == {
        ("node1",),
    }


def test_apt_repository_credentials_are_not_stored(neo4j_session):
    # Arrange
    _seed(neo4j_session)

    # Act
    _sync(
        neo4j_session,
        TEST_UPDATE_TAG,
        [{"node": "node1", "status": "online"}],
        {"get_apt_repositories": data.MOCK_APT_REPOSITORIES_WITH_CREDENTIALS},
    )

    # Assert
    assert neo4j_session.run(
        "MATCH (r:ProxmoxAPTRepository) RETURN r.uris AS uris",
    ).single()["uris"] == [
        "https://repo.example.com/debian",
        "https://mirror.example.com/x?dist=1",
    ]
    stored = neo4j_session.run(
        "MATCH (n) WHERE n:ProxmoxAPTRepository OR n:ProxmoxNodeConfig "
        "RETURN properties(n) AS p",
    ).data()
    assert "s3cr3t" not in repr(stored)
