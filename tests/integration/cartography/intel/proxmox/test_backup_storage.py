"""
Integration tests for Proxmox backup coverage, storage content, and replication.
"""

from typing import Any
from unittest.mock import MagicMock
from unittest.mock import patch

import cartography.intel.proxmox.backup
import cartography.intel.proxmox.backup_coverage as backup_coverage
import cartography.intel.proxmox.cluster
import cartography.intel.proxmox.replication as replication
import cartography.intel.proxmox.storage_content as storage_content
from tests.data.proxmox.backup_coverage import MOCK_COVERAGE_BACKUP_JOBS
from tests.data.proxmox.backup_coverage import MOCK_INCLUDED_VOLUMES
from tests.data.proxmox.backup_coverage import MOCK_NOT_BACKED_UP
from tests.data.proxmox.backup_coverage import MOCK_VZDUMP_DEFAULTS
from tests.data.proxmox.replication import MOCK_NODE_REPLICATION
from tests.data.proxmox.replication import MOCK_REPLICATION_JOBS
from tests.data.proxmox.replication import MOCK_REPLICATION_STATUS
from tests.data.proxmox.storage_content import MOCK_NODE_STORAGE_STATUS
from tests.data.proxmox.storage_content import MOCK_STORAGE_CONTENT
from tests.integration.util import check_nodes
from tests.integration.util import check_rels

TEST_UPDATE_TAG = 123456789
CLUSTER = "test-cluster"
NODES = [
    {"node": "node1", "status": "online"},
    {"node": "node2", "status": "online"},
]


def _seed(neo4j_session, update_tag: int) -> None:
    """Create the cluster, nodes, guests, disks, storage and jobs the syncs link to."""
    neo4j_session.run("MATCH (n) DETACH DELETE n")
    neo4j_session.run(
        """
        MERGE (c:ProxmoxCluster {id: $c})
        WITH c
        UNWIND ['node1', 'node2'] AS n
        MERGE (node:ProxmoxNode {id: $c + '/' + n})
        SET node.name = n, node.lastupdated = $tag
        MERGE (c)-[:RESOURCE]->(node)
        WITH DISTINCT c
        UNWIND ['local', 'local-lvm', 'pbs'] AS s
        MERGE (st:ProxmoxStorage {id: $c + '/' + s})
        SET st.name = s, st.lastupdated = $tag
        MERGE (c)-[:RESOURCE]->(st)
        WITH DISTINCT c
        UNWIND [
            {id: 'node1/qemu/100', vmid: 100},
            {id: 'node1/qemu/101', vmid: 101},
            {id: 'node2/lxc/200', vmid: 200}
        ] AS g
        MERGE (vm:ProxmoxVM {id: $c + '/' + g.id})
        SET vm.vmid = g.vmid, vm.cluster_id = $c, vm.lastupdated = $tag
        MERGE (c)-[:RESOURCE]->(vm)
        WITH DISTINCT c
        UNWIND [
            {vm: 'node1/qemu/100', vmid: 100, disk: 'scsi0'},
            {vm: 'node1/qemu/100', vmid: 100, disk: 'scsi1'},
            {vm: 'node2/lxc/200', vmid: 200, disk: 'rootfs'}
        ] AS d
        MERGE (disk:ProxmoxDisk {id: $c + '/' + d.vm + ':' + d.disk})
        SET disk.vmid = d.vmid, disk.disk_id = d.disk, disk.cluster_id = $c,
            disk.lastupdated = $tag
        WITH DISTINCT c
        UNWIND ['backup-all', 'backup-web'] AS j
        MERGE (job:ProxmoxBackupJob {id: $c + '/' + j})
        SET job.job_id = j, job.lastupdated = $tag
        MERGE (c)-[:RESOURCE]->(job)
        """,
        c=CLUSTER,
        tag=update_tag,
    )


def _sync(
    neo4j_session,
    update_tag: int,
    included: dict[str, Any],
    content: dict[tuple[str, str], list[dict[str, Any]]],
    replication_jobs: list[dict[str, Any]],
) -> None:
    params = {"UPDATE_TAG": update_tag, "CLUSTER_ID": CLUSTER}
    client = MagicMock()
    with (
        patch.object(
            cartography.intel.proxmox.cluster, "get_nodes", return_value=NODES
        ),
        patch.object(
            cartography.intel.proxmox.backup,
            "get_backup_jobs",
            return_value=MOCK_COVERAGE_BACKUP_JOBS,
        ),
        patch.object(
            backup_coverage,
            "get_included_volumes",
            side_effect=lambda _c, job_id: included.get(job_id, {}),
        ),
        patch.object(
            backup_coverage,
            "get_not_backed_up",
            return_value=MOCK_NOT_BACKED_UP,
        ),
        patch.object(
            backup_coverage,
            "get_vzdump_defaults",
            side_effect=lambda _c, node: MOCK_VZDUMP_DEFAULTS[node],
        ),
        patch.object(
            storage_content,
            "get_storage_content",
            side_effect=lambda _c, node, storage: content.get((node, storage), []),
        ),
        patch.object(
            replication,
            "get_cluster_replication_jobs",
            return_value=replication_jobs,
        ),
        patch.object(
            replication,
            "get_node_replication_status",
            side_effect=lambda _c, node: MOCK_NODE_REPLICATION[node],
        ),
        patch.object(
            replication,
            "get_replication_job_status",
            side_effect=lambda _c, node, job: MOCK_REPLICATION_STATUS[(node, job)],
        ),
    ):
        backup_coverage.sync(neo4j_session, client, CLUSTER, update_tag, params)
        storage_content.sync(
            neo4j_session,
            client,
            CLUSTER,
            update_tag,
            params,
            MOCK_NODE_STORAGE_STATUS,
        )
        replication.sync(neo4j_session, client, CLUSTER, update_tag, params)
        backup_coverage.cleanup(neo4j_session, params)
        storage_content.cleanup(neo4j_session, params)
        replication.cleanup(neo4j_session, params)


def _rels(neo4j_session, source: str, rel: str, target: str) -> set:
    return check_rels(
        neo4j_session,
        source,
        "id",
        target,
        "id",
        rel,
        rel_direction_right=True,
    )


def test_sync_backup_coverage(neo4j_session):
    _seed(neo4j_session, TEST_UPDATE_TAG)

    _sync(
        neo4j_session,
        TEST_UPDATE_TAG,
        MOCK_INCLUDED_VOLUMES,
        MOCK_STORAGE_CONTENT,
        MOCK_REPLICATION_JOBS,
    )

    # Jobs cover the guests Proxmox resolves, including "all" selections
    assert _rels(neo4j_session, "ProxmoxBackupJob", "COVERS", "ProxmoxVM") == {
        ("test-cluster/backup-all", "test-cluster/node1/qemu/100"),
        ("test-cluster/backup-all", "test-cluster/node2/lxc/200"),
        ("test-cluster/backup-web", "test-cluster/node1/qemu/100"),
    }
    # Only included volumes link to their disk
    assert _rels(neo4j_session, "ProxmoxBackupJob", "INCLUDES_DISK", "ProxmoxDisk") == {
        ("test-cluster/backup-all", "test-cluster/node1/qemu/100:scsi0"),
        ("test-cluster/backup-all", "test-cluster/node2/lxc/200:rootfs"),
        ("test-cluster/backup-web", "test-cluster/node1/qemu/100:scsi0"),
    }
    assert check_nodes(neo4j_session, "ProxmoxVM", ["id", "backup_covered"]) == {
        ("test-cluster/node1/qemu/100", True),
        ("test-cluster/node1/qemu/101", False),
        ("test-cluster/node2/lxc/200", True),
    }

    # Node defaults
    assert check_nodes(
        neo4j_session,
        "ProxmoxBackupDefaults",
        ["id", "mode", "prune_keep_daily", "prune_keep_all"],
    ) == {
        ("test-cluster/node1", "snapshot", 7, None),
        ("test-cluster/node2", "stop", None, True),
    }
    assert _rels(
        neo4j_session, "ProxmoxNode", "HAS_BACKUP_DEFAULTS", "ProxmoxBackupDefaults"
    ) == {
        ("test-cluster/node1", "test-cluster/node1"),
        ("test-cluster/node2", "test-cluster/node2"),
    }
    assert _rels(
        neo4j_session, "ProxmoxBackupDefaults", "BACKS_UP_TO", "ProxmoxStorage"
    ) == {("test-cluster/node1", "test-cluster/pbs")}


def test_sync_storage_content(neo4j_session):
    _seed(neo4j_session, TEST_UPDATE_TAG)

    _sync(
        neo4j_session,
        TEST_UPDATE_TAG,
        MOCK_INCLUDED_VOLUMES,
        MOCK_STORAGE_CONTENT,
        MOCK_REPLICATION_JOBS,
    )

    local_backup = "local:backup/vzdump-qemu-100-2026_10_01-02_00_00.vma.zst"
    assert check_nodes(
        neo4j_session,
        "ProxmoxBackupArchive",
        ["id", "vmid", "node", "verification_state"],
    ) == {
        (f"test-cluster/node1/{local_backup}", 100, "node1", None),
        (f"test-cluster/node2/{local_backup}", 100, "node2", None),
        ("test-cluster/pbs:backup/ct/200/2026-10-01T03:00:00Z", 200, None, "ok"),
        ("test-cluster/pbs:backup/vm/100/2026-10-01T02:00:00Z", 100, None, "failed"),
    }
    assert _rels(neo4j_session, "ProxmoxBackupArchive", "BACKUP_OF", "ProxmoxVM") == {
        (f"test-cluster/node1/{local_backup}", "test-cluster/node1/qemu/100"),
        (f"test-cluster/node2/{local_backup}", "test-cluster/node1/qemu/100"),
        (
            "test-cluster/pbs:backup/ct/200/2026-10-01T03:00:00Z",
            "test-cluster/node2/lxc/200",
        ),
        (
            "test-cluster/pbs:backup/vm/100/2026-10-01T02:00:00Z",
            "test-cluster/node1/qemu/100",
        ),
    }
    assert _rels(
        neo4j_session, "ProxmoxBackupArchive", "STORED_ON", "ProxmoxStorage"
    ) == {
        (f"test-cluster/node1/{local_backup}", "test-cluster/local"),
        (f"test-cluster/node2/{local_backup}", "test-cluster/local"),
        ("test-cluster/pbs:backup/ct/200/2026-10-01T03:00:00Z", "test-cluster/pbs"),
        ("test-cluster/pbs:backup/vm/100/2026-10-01T02:00:00Z", "test-cluster/pbs"),
    }
    assert _rels(
        neo4j_session, "ProxmoxStorageTemplate", "STORED_ON", "ProxmoxStorage"
    ) == {
        ("test-cluster/node1/local:iso/debian-13.iso", "test-cluster/local"),
        (
            "test-cluster/node1/local:vztmpl/debian-13-standard_13.0-1_amd64.tar.zst",
            "test-cluster/local",
        ),
    }


def test_sync_replication(neo4j_session):
    _seed(neo4j_session, TEST_UPDATE_TAG)

    _sync(
        neo4j_session,
        TEST_UPDATE_TAG,
        MOCK_INCLUDED_VOLUMES,
        MOCK_STORAGE_CONTENT,
        MOCK_REPLICATION_JOBS,
    )

    assert check_nodes(
        neo4j_session,
        "ProxmoxReplicationJob",
        ["id", "enabled", "fail_count", "last_sync"],
    ) == {
        ("test-cluster/100-0", True, 2, 1790820000),
        ("test-cluster/200-0", False, 0, 1790800000),
    }
    assert _rels(neo4j_session, "ProxmoxReplicationJob", "REPLICATES", "ProxmoxVM") == {
        ("test-cluster/100-0", "test-cluster/node1/qemu/100"),
        ("test-cluster/200-0", "test-cluster/node2/lxc/200"),
    }
    assert _rels(
        neo4j_session, "ProxmoxReplicationJob", "REPLICATES_TO", "ProxmoxNode"
    ) == {
        ("test-cluster/100-0", "test-cluster/node2"),
        ("test-cluster/200-0", "test-cluster/node1"),
    }


def test_cleanup_removes_stale_coverage_content_and_replication(neo4j_session):
    _seed(neo4j_session, TEST_UPDATE_TAG)
    _sync(
        neo4j_session,
        TEST_UPDATE_TAG,
        MOCK_INCLUDED_VOLUMES,
        MOCK_STORAGE_CONTENT,
        MOCK_REPLICATION_JOBS,
    )

    # Act - the next run sees "backup-all" select nothing, the pbs archives
    # gone, and only the first replication job
    next_tag = TEST_UPDATE_TAG + 1
    neo4j_session.run(
        "MATCH (n) WHERE n:ProxmoxVM OR n:ProxmoxNode OR n:ProxmoxStorage "
        "OR n:ProxmoxDisk OR n:ProxmoxBackupJob SET n.lastupdated = $tag",
        tag=next_tag,
    )
    content = {k: v for k, v in MOCK_STORAGE_CONTENT.items() if k[1] != "pbs"}
    _sync(
        neo4j_session,
        next_tag,
        {"backup-web": MOCK_INCLUDED_VOLUMES["backup-web"]},
        content,
        MOCK_REPLICATION_JOBS[:1],
    )

    assert _rels(neo4j_session, "ProxmoxBackupJob", "COVERS", "ProxmoxVM") == {
        ("test-cluster/backup-web", "test-cluster/node1/qemu/100"),
    }
    assert _rels(neo4j_session, "ProxmoxBackupJob", "INCLUDES_DISK", "ProxmoxDisk") == {
        ("test-cluster/backup-web", "test-cluster/node1/qemu/100:scsi0"),
    }
    assert {
        node_id
        for (node_id,) in check_nodes(neo4j_session, "ProxmoxBackupArchive", ["id"])
    } == {
        "test-cluster/node1/local:backup/vzdump-qemu-100-2026_10_01-02_00_00.vma.zst",
        "test-cluster/node2/local:backup/vzdump-qemu-100-2026_10_01-02_00_00.vma.zst",
    }
    assert check_nodes(neo4j_session, "ProxmoxReplicationJob", ["id"]) == {
        ("test-cluster/100-0",),
    }
