"""
Integration tests for Proxmox relationship cleanup and cluster scoping.
"""

import copy
from contextlib import ExitStack
from typing import Any
from unittest.mock import MagicMock
from unittest.mock import patch

import cartography.intel.proxmox
import cartography.intel.proxmox.access
import cartography.intel.proxmox.backup
import cartography.intel.proxmox.certificate
import cartography.intel.proxmox.cluster
import cartography.intel.proxmox.compute
import cartography.intel.proxmox.firewall
import cartography.intel.proxmox.ha
import cartography.intel.proxmox.pool
import cartography.intel.proxmox.storage
from cartography.config import Config
from tests.data.proxmox.access import MOCK_ACL_DATA
from tests.data.proxmox.access import MOCK_GROUP_DATA
from tests.data.proxmox.access import MOCK_GROUP_MEMBERS_DATA
from tests.data.proxmox.access import MOCK_ROLE_DATA
from tests.data.proxmox.access import MOCK_USER_DATA
from tests.data.proxmox.backup import MOCK_BACKUP_JOB_DATA
from tests.data.proxmox.cluster import MOCK_CLUSTER_CONFIG
from tests.data.proxmox.cluster import MOCK_CLUSTER_DATA
from tests.data.proxmox.cluster import MOCK_CLUSTER_OPTIONS
from tests.data.proxmox.cluster import MOCK_NODE_DATA
from tests.data.proxmox.cluster import MOCK_NODE_NETWORK_DATA
from tests.data.proxmox.compute import MOCK_STORAGE_DATA
from tests.data.proxmox.compute import MOCK_VM_CONFIG
from tests.data.proxmox.compute import MOCK_VM_DATA
from tests.data.proxmox.ha import MOCK_HA_GROUP_DATA
from tests.data.proxmox.ha import MOCK_HA_RESOURCE_DATA
from tests.data.proxmox.pool import MOCK_POOL_DATA
from tests.data.proxmox.pool import MOCK_POOL_DETAILS
from tests.integration.util import check_rels

TEST_CLUSTER_ID = "test-cluster"  # Name of the cluster in MOCK_CLUSTER_DATA

PERMISSION_TARGET_LABELS = (
    "ProxmoxCluster",
    "ProxmoxVM",
    "ProxmoxStorage",
    "ProxmoxPool",
    "ProxmoxNode",
)

# ACLs that the second sync no longer returns
REMOVED_VM_ACL = "/vms/100"
REMOVED_NODE_ACL = "/nodes/node1"


def _wipe(neo4j_session) -> None:
    neo4j_session.run("MATCH (n) DETACH DELETE n")


def _rels(
    neo4j_session,
    source_label: str,
    rel_label: str,
    target_labels: tuple[str, ...],
) -> set[tuple[str, str]]:
    """Return every rel_label edge from source_label to any target label, as id pairs."""
    rels: set[tuple[str, str]] = set()
    for target_label in target_labels:
        rels |= check_rels(
            neo4j_session,
            source_label,
            "id",
            target_label,
            "id",
            rel_label,
            rel_direction_right=True,
        )
    return rels


def _run_ingestion(
    neo4j_session,
    update_tag: int,
    pool_details: dict[str, Any],
    acls: list[dict[str, Any]],
) -> None:
    """Run start_proxmox_ingestion with every API getter mocked."""
    proxmox = MagicMock()
    proxmox.nodes.get.return_value = [{"node": "node1"}, {"node": "node2"}]

    def vms_of_type(vm_type: str):
        return lambda _client, node: [
            vm for vm in MOCK_VM_DATA.get(node, []) if vm["type"] == vm_type
        ]

    patches = [
        patch.object(
            cartography.intel.proxmox, "_get_proxmox_client", return_value=proxmox
        ),
        # Cluster and compute
        patch.object(
            cartography.intel.proxmox.cluster,
            "get_cluster_status",
            return_value=MOCK_CLUSTER_DATA,
        ),
        patch.object(
            cartography.intel.proxmox.cluster, "get_nodes", return_value=MOCK_NODE_DATA
        ),
        patch.object(
            cartography.intel.proxmox.cluster,
            "get_cluster_options",
            return_value=MOCK_CLUSTER_OPTIONS,
        ),
        patch.object(
            cartography.intel.proxmox.cluster,
            "get_cluster_config",
            return_value=MOCK_CLUSTER_CONFIG,
        ),
        patch.object(
            cartography.intel.proxmox.cluster,
            "get_node_network",
            side_effect=lambda _client, node: MOCK_NODE_NETWORK_DATA.get(node, []),
        ),
        patch.object(
            cartography.intel.proxmox.compute,
            "get_vms_for_node",
            side_effect=vms_of_type("qemu"),
        ),
        patch.object(
            cartography.intel.proxmox.compute,
            "get_containers_for_node",
            side_effect=vms_of_type("lxc"),
        ),
        patch.object(
            cartography.intel.proxmox.compute,
            "get_vm_config",
            side_effect=lambda _client, _node, vmid, _type: MOCK_VM_CONFIG.get(
                vmid, {}
            ),
        ),
        patch.object(
            cartography.intel.proxmox.storage,
            "get_storage",
            return_value=MOCK_STORAGE_DATA,
        ),
        patch.object(
            cartography.intel.proxmox.storage, "get_storage_status", return_value=[]
        ),
        # Pools, backups, HA
        patch.object(
            cartography.intel.proxmox.pool, "get_pools", return_value=MOCK_POOL_DATA
        ),
        patch.object(
            cartography.intel.proxmox.pool,
            "get_pool_details",
            side_effect=lambda _client, poolid: pool_details.get(poolid, {}),
        ),
        patch.object(
            cartography.intel.proxmox.backup,
            "get_backup_jobs",
            return_value=MOCK_BACKUP_JOB_DATA,
        ),
        patch.object(
            cartography.intel.proxmox.ha,
            "get_ha_groups",
            return_value=MOCK_HA_GROUP_DATA,
        ),
        patch.object(
            cartography.intel.proxmox.ha,
            "get_ha_resources",
            return_value=MOCK_HA_RESOURCE_DATA,
        ),
        # Access control
        patch.object(
            cartography.intel.proxmox.access, "get_users", return_value=MOCK_USER_DATA
        ),
        patch.object(
            cartography.intel.proxmox.access,
            "get_groups",
            return_value=MOCK_GROUP_DATA,
        ),
        patch.object(
            cartography.intel.proxmox.access, "get_roles", return_value=MOCK_ROLE_DATA
        ),
        patch.object(cartography.intel.proxmox.access, "get_acls", return_value=acls),
        patch.object(
            cartography.intel.proxmox.access,
            "get_group_members",
            return_value=MOCK_GROUP_MEMBERS_DATA,
        ),
        # Firewall and certificates are not under test
        patch.object(
            cartography.intel.proxmox.firewall,
            "get_cluster_firewall_rules",
            return_value=[],
        ),
        patch.object(
            cartography.intel.proxmox.firewall, "get_cluster_ipsets", return_value=[]
        ),
        patch.object(
            cartography.intel.proxmox.firewall,
            "get_node_firewall_rules",
            return_value=[],
        ),
        patch.object(
            cartography.intel.proxmox.certificate,
            "get_node_certificates",
            return_value=[],
        ),
    ]
    config = Config(
        neo4j_uri="bolt://localhost:7687",
        update_tag=update_tag,
        proxmox_host="pve.example.com",
    )
    with ExitStack() as stack:
        for p in patches:
            stack.enter_context(p)
        cartography.intel.proxmox.start_proxmox_ingestion(neo4j_session, config)


def test_resync_removes_stale_relationships(neo4j_session):
    """
    A second sync removes edges whose source data disappeared: a guest that left
    a pool, and ACL entries that were deleted together with the permissions
    derived from them.
    """
    _wipe(neo4j_session)

    # Arrange - second sync: VM 200 left the production pool and two ACLs are gone
    shrunk_pool_details = copy.deepcopy(MOCK_POOL_DETAILS)
    shrunk_pool_details["production"]["members"] = [
        member
        for member in shrunk_pool_details["production"]["members"]
        if member.get("vmid") != 200
    ]
    shrunk_acls = [
        acl
        for acl in MOCK_ACL_DATA
        if acl["path"] not in (REMOVED_VM_ACL, REMOVED_NODE_ACL)
    ]

    # Act - first sync
    _run_ingestion(neo4j_session, 1, MOCK_POOL_DETAILS, MOCK_ACL_DATA)

    # Assert - the edges under test exist after the first sync
    assert _rels(neo4j_session, "ProxmoxPool", "CONTAINS_VM", ("ProxmoxVM",)) == {
        ("development", "node1/qemu/101"),
        ("production", "node1/qemu/100"),
        ("production", "node2/lxc/200"),
    }
    assert _rels(
        neo4j_session, "ProxmoxACL", "GRANTS_ACCESS_TO", ("ProxmoxVM", "ProxmoxNode")
    ) == {
        ("/vms/100:readonly@pam:CustomRole", "node1/qemu/100"),
        ("/nodes/node1:operators:PVEAuditor", "node1"),
    }
    users_before = _rels(
        neo4j_session, "ProxmoxUser", "HAS_PERMISSION", PERMISSION_TARGET_LABELS
    )
    groups_before = _rels(
        neo4j_session, "ProxmoxGroup", "HAS_PERMISSION", PERMISSION_TARGET_LABELS
    )
    assert {
        ("readonly@pam", "node1/qemu/100"),
        ("root@pam", "node1"),  # Inherited through the operators group
    } <= users_before
    assert ("operators", "node1") in groups_before

    # Act - second sync with a later update tag
    _run_ingestion(neo4j_session, 2, shrunk_pool_details, shrunk_acls)

    # Assert - the guest that left the pool is no longer contained in it
    assert _rels(neo4j_session, "ProxmoxPool", "CONTAINS_VM", ("ProxmoxVM",)) == {
        ("development", "node1/qemu/101"),
        ("production", "node1/qemu/100"),
    }

    # Assert - the removed ACLs no longer grant access
    assert (
        _rels(
            neo4j_session,
            "ProxmoxACL",
            "GRANTS_ACCESS_TO",
            ("ProxmoxVM", "ProxmoxNode"),
        )
        == set()
    )

    # Assert - permissions derived only from the removed ACLs are gone, the rest stay
    assert _rels(
        neo4j_session, "ProxmoxUser", "HAS_PERMISSION", PERMISSION_TARGET_LABELS
    ) == users_before - {
        ("readonly@pam", "node1/qemu/100"),
        ("root@pam", "node1"),
    }
    assert _rels(
        neo4j_session, "ProxmoxGroup", "HAS_PERMISSION", PERMISSION_TARGET_LABELS
    ) == groups_before - {("operators", "node1")}


def test_guest_relationships_stay_in_their_cluster(neo4j_session):
    """
    VM IDs are only unique inside one cluster: edges matched by vmid must not
    reach the guest with the same vmid in another cluster.
    """
    _wipe(neo4j_session)

    # Arrange - two clusters that both run a guest with vmid 100
    neo4j_session.run(
        """
        UNWIND [['cluster-a', 'a1'], ['cluster-b', 'b1']] AS c
        MERGE (cluster:ProxmoxCluster {id: c[0]})
        MERGE (vm:ProxmoxVM {id: c[1] + '/qemu/100'})
        SET vm.vmid = 100, vm.cluster_id = c[0]
        MERGE (cluster)-[:RESOURCE]->(vm)
        """,
    )
    common_job_parameters = {"UPDATE_TAG": 1, "CLUSTER_ID": "cluster-a"}
    proxmox = MagicMock()
    proxmox.nodes.get.return_value = []

    access = cartography.intel.proxmox.access
    api_data = [
        (cartography.intel.proxmox.ha, "get_ha_groups", []),
        (
            cartography.intel.proxmox.ha,
            "get_ha_resources",
            [{"sid": "vm:100", "state": "started"}],
        ),
        (
            cartography.intel.proxmox.backup,
            "get_backup_jobs",
            [{"id": "nightly", "vmid": "100"}],
        ),
        (access, "get_users", []),
        (access, "get_groups", []),
        (access, "get_roles", []),
        (
            access,
            "get_acls",
            [{"path": "/vms/100", "roleid": "PVEAuditor", "ugid": "ops@pve"}],
        ),
        (access, "get_group_members", {}),
    ]

    # Act - sync cluster-a only
    with ExitStack() as stack:
        for module, getter, data in api_data:
            stack.enter_context(patch.object(module, getter, return_value=data))
        for module in (
            cartography.intel.proxmox.ha,
            cartography.intel.proxmox.backup,
            access,
        ):
            module.sync(neo4j_session, proxmox, "cluster-a", 1, common_job_parameters)
    cartography.intel.proxmox.firewall.load_firewall_rules(
        neo4j_session,
        cartography.intel.proxmox.firewall.transform_firewall_rule_data(
            [{"pos": 0, "action": "ACCEPT"}], "cluster-a", "vm", "100"
        ),
        "cluster-a",
        1,
    )

    # Assert - every vmid-matched edge reaches only cluster-a's guest
    expected = {
        ("ProxmoxHAResource", "PROTECTS", "vm:100"),
        ("ProxmoxBackupJob", "BACKS_UP", "nightly"),
        ("ProxmoxACL", "GRANTS_ACCESS_TO", "/vms/100:ops@pve:PVEAuditor"),
        ("ProxmoxFirewallRule", "APPLIES_TO_VM", "vm:100:0"),
    }
    for source_label, rel_label, source_id in expected:
        assert _rels(neo4j_session, source_label, rel_label, ("ProxmoxVM",)) == {
            (source_id, "a1/qemu/100"),
        }, rel_label
