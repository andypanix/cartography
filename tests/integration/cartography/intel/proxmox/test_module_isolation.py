"""
Integration tests for the per-module error isolation of start_proxmox_ingestion.
"""

import logging
from unittest.mock import patch

import pytest

import cartography.intel.proxmox
import cartography.intel.proxmox.access
import cartography.intel.proxmox.ceph
import cartography.intel.proxmox.cluster
import cartography.intel.proxmox.compute
import cartography.intel.proxmox.firewall
import cartography.intel.proxmox.mapping
import cartography.intel.proxmox.pool
import cartography.intel.proxmox.sdn
import cartography.intel.proxmox.storage
import cartography.intel.proxmox.storage_content
from cartography.graph.job import GraphJob
from cartography.intel.proxmox import ProxmoxSyncError
from cartography.models.proxmox.compute import ProxmoxVMSchema
from cartography.models.proxmox.firewall import ProxmoxFirewallIPSetSchema
from cartography.models.proxmox.firewall import ProxmoxFirewallRuleSchema
from tests.data.proxmox.access import MOCK_ACL_DATA
from tests.data.proxmox.pool import MOCK_POOL_DETAILS
from tests.integration.cartography.intel.proxmox.test_relationship_cleanup import _rels
from tests.integration.cartography.intel.proxmox.test_relationship_cleanup import (
    _run_ingestion,
)
from tests.integration.cartography.intel.proxmox.test_relationship_cleanup import _wipe
from tests.integration.util import check_nodes

REAL_FROM_NODE_SCHEMA = GraphJob.from_node_schema

POOL_MEMBERS = {
    ("test-cluster/development", "test-cluster/node1/qemu/101"),
    ("test-cluster/production", "test-cluster/node1/qemu/100"),
    ("test-cluster/production", "test-cluster/node2/lxc/200"),
}


def test_failing_module_keeps_its_data_while_the_others_sync(neo4j_session, caplog):
    """
    A module that raises keeps its existing data, while the other modules still
    load and run their cleanup, and the sync reports the failed module at the end.
    """
    _wipe(neo4j_session)
    _run_ingestion(neo4j_session, 1, MOCK_POOL_DETAILS, MOCK_ACL_DATA)
    assert _rels(neo4j_session, "ProxmoxPool", "CONTAINS_VM", ("ProxmoxVM",)) == (
        POOL_MEMBERS
    )
    # The second sync no longer returns any ACL
    shrunk_acls: list[dict] = []

    # Act - the pool sync fails on the second sync
    with (
        patch.object(
            cartography.intel.proxmox.pool,
            "sync",
            side_effect=RuntimeError("pool API down"),
        ),
        caplog.at_level(logging.ERROR, logger="cartography.intel.proxmox"),
        pytest.raises(ProxmoxSyncError, match="modules: pool$"),
    ):
        _run_ingestion(neo4j_session, 2, MOCK_POOL_DETAILS, shrunk_acls)

    # Assert - the failure is logged with the module name and its traceback
    failure_logs = [
        r for r in caplog.records if "Proxmox pool sync failed" in r.getMessage()
    ]
    assert failure_logs and failure_logs[0].exc_info is not None

    # Assert - the pools of the first sync stay, because their cleanup was skipped
    assert check_nodes(neo4j_session, "ProxmoxPool", ["id", "lastupdated"]) == {
        ("test-cluster/backup-storage", 1),
        ("test-cluster/development", 1),
        ("test-cluster/production", 1),
    }
    assert _rels(neo4j_session, "ProxmoxPool", "CONTAINS_VM", ("ProxmoxVM",)) == (
        POOL_MEMBERS
    )

    # Assert - the modules after the failed one loaded, and their cleanup ran
    assert check_nodes(neo4j_session, "ProxmoxVM", ["id", "lastupdated"]) == {
        ("test-cluster/node1/qemu/100", 2),
        ("test-cluster/node1/qemu/101", 2),
        ("test-cluster/node2/lxc/200", 2),
    }
    assert check_nodes(neo4j_session, "ProxmoxACL", ["id"]) == set()


def test_failed_access_sync_skips_the_permission_analysis(neo4j_session):
    """
    The effective permissions analysis does not run on a partial access sync.
    """
    _wipe(neo4j_session)

    with (
        patch.object(
            cartography.intel.proxmox.access,
            "sync",
            side_effect=RuntimeError("access API down"),
        ),
        patch.object(cartography.intel.proxmox, "run_typed_analysis_job") as analysis,
        pytest.raises(ProxmoxSyncError, match="modules: access$"),
    ):
        _run_ingestion(neo4j_session, 1, MOCK_POOL_DETAILS, MOCK_ACL_DATA)

    analysis.assert_not_called()


def test_module_needing_a_failed_module_is_skipped(neo4j_session):
    """
    Storage content reads the storages listed by the storage sync, so it is
    skipped and reported failed when the storage sync fails.
    """
    _wipe(neo4j_session)

    with (
        patch.object(
            cartography.intel.proxmox.storage,
            "sync",
            side_effect=RuntimeError("storage API down"),
        ),
        patch.object(cartography.intel.proxmox.storage_content, "sync") as content,
        pytest.raises(
            ProxmoxSyncError,
            match="modules: storage, storage content$",
        ),
    ):
        _run_ingestion(neo4j_session, 1, MOCK_POOL_DETAILS, MOCK_ACL_DATA)

    content.assert_not_called()


def test_cluster_failure_aborts_the_sync(neo4j_session):
    """
    Every module needs the cluster ID, so a cluster sync failure stops the sync
    with the original error and no other module runs.
    """
    _wipe(neo4j_session)

    with (
        patch.object(
            cartography.intel.proxmox.cluster,
            "sync",
            side_effect=RuntimeError("cluster API down"),
        ),
        patch.object(cartography.intel.proxmox.storage, "sync") as storage_sync,
        pytest.raises(RuntimeError, match="cluster API down"),
    ):
        _run_ingestion(neo4j_session, 1, MOCK_POOL_DETAILS, MOCK_ACL_DATA)

    storage_sync.assert_not_called()
    assert check_nodes(neo4j_session, "ProxmoxNode", ["id"]) == set()


def _record_cleanups(cleaned: list[type], failing: type | None = None):
    """
    Patch the node schema cleanup so that it records each schema it cleans,
    and raises for the failing schema.
    """

    def from_node_schema(schema, common_job_parameters):
        if failing is not None and isinstance(schema, failing):
            raise RuntimeError(f"cleanup of {failing.__name__} failed")
        cleaned.append(type(schema))
        return REAL_FROM_NODE_SCHEMA(schema, common_job_parameters)

    return patch.object(GraphJob, "from_node_schema", side_effect=from_node_schema)


def _module_sync_metadata_ids(neo4j_session) -> set[str]:
    result = neo4j_session.run("MATCH (n:ModuleSyncMetadata) RETURN n.id AS id")
    return {record["id"] for record in result}


def test_failed_sync_does_not_write_sync_metadata(neo4j_session):
    """
    The sync metadata records a complete sync, so a sync in which a module
    failed does not write it.
    """
    _wipe(neo4j_session)

    with (
        patch.object(
            cartography.intel.proxmox.pool,
            "sync",
            side_effect=RuntimeError("pool API down"),
        ),
        pytest.raises(ProxmoxSyncError, match="modules: pool$"),
    ):
        _run_ingestion(neo4j_session, 1, MOCK_POOL_DETAILS, MOCK_ACL_DATA)

    assert _module_sync_metadata_ids(neo4j_session) == set()

    # A complete sync writes it
    _run_ingestion(neo4j_session, 2, MOCK_POOL_DETAILS, MOCK_ACL_DATA)
    assert _module_sync_metadata_ids(neo4j_session) == {
        "ProxmoxCluster_test-cluster_ProxmoxCluster",
    }


def test_compute_failure_skips_the_mapping_sync(neo4j_session):
    """
    Mappings link to the VMs returned by the compute sync, so they are skipped
    and reported failed when the compute sync fails.
    """
    _wipe(neo4j_session)

    with (
        patch.object(
            cartography.intel.proxmox.compute,
            "sync",
            side_effect=RuntimeError("compute API down"),
        ),
        patch.object(cartography.intel.proxmox.mapping, "sync") as mapping_sync,
        pytest.raises(ProxmoxSyncError, match="modules: compute, mapping$"),
    ):
        _run_ingestion(neo4j_session, 1, MOCK_POOL_DETAILS, MOCK_ACL_DATA)

    mapping_sync.assert_not_called()


@pytest.mark.parametrize("failing_module", ["firewall", "sdn"])
def test_firewall_or_sdn_failure_skips_the_rule_cleanup(
    neo4j_session,
    caplog,
    failing_module,
):
    """
    Firewall rules are loaded by both the firewall and the SDN sync, so their
    cleanup is skipped when either of them fails.
    """
    _wipe(neo4j_session)
    cleaned: list[type] = []

    with (
        patch.object(
            getattr(cartography.intel.proxmox, failing_module),
            "sync",
            side_effect=RuntimeError(f"{failing_module} API down"),
        ),
        _record_cleanups(cleaned),
        caplog.at_level(logging.WARNING, logger="cartography.intel.proxmox"),
        pytest.raises(ProxmoxSyncError, match=f"modules: {failing_module}$"),
    ):
        _run_ingestion(neo4j_session, 1, MOCK_POOL_DETAILS, MOCK_ACL_DATA)

    assert ProxmoxFirewallRuleSchema not in cleaned
    assert ProxmoxVMSchema in cleaned
    # The other firewall cleanups run only when the firewall sync succeeded
    assert (ProxmoxFirewallIPSetSchema in cleaned) is (failing_module == "sdn")
    assert (
        "Skipping cleanup of Proxmox firewall and sdn because the "
        f"{failing_module} sync failed"
    ) in caplog.text


def test_failing_rule_cleanup_is_reported_as_a_cleanup_failure(
    neo4j_session,
    caplog,
):
    """
    When the firewall rule cleanup raises, the later firewall cleanups are
    skipped and their log names the failed cleanup, not a failed module sync.
    """
    _wipe(neo4j_session)
    cleaned: list[type] = []

    with (
        _record_cleanups(cleaned, failing=ProxmoxFirewallRuleSchema),
        caplog.at_level(logging.WARNING, logger="cartography.intel.proxmox"),
        pytest.raises(ProxmoxSyncError, match="modules: firewall$"),
    ):
        _run_ingestion(neo4j_session, 1, MOCK_POOL_DETAILS, MOCK_ACL_DATA)

    assert ProxmoxFirewallIPSetSchema not in cleaned
    assert (
        "Skipping cleanup of Proxmox firewall because the firewall cleanup failed"
    ) in caplog.text
    assert "Proxmox firewall cleanup failed" in caplog.text
    assert "firewall sync failed" not in caplog.text


def test_raising_ceph_sync_skips_the_ceph_cleanup(neo4j_session, caplog):
    """
    A Ceph sync that raises skips the Ceph cleanup and is reported failed,
    unlike a cluster without Ceph, which only logs that Ceph could not be read.
    """
    _wipe(neo4j_session)

    with (
        patch.object(
            cartography.intel.proxmox.ceph,
            "sync",
            side_effect=RuntimeError("ceph API down"),
        ),
        patch.object(cartography.intel.proxmox.ceph, "cleanup") as ceph_cleanup,
        caplog.at_level(logging.WARNING, logger="cartography.intel.proxmox"),
        pytest.raises(ProxmoxSyncError, match="modules: ceph$"),
    ):
        _run_ingestion(neo4j_session, 1, MOCK_POOL_DETAILS, MOCK_ACL_DATA)

    ceph_cleanup.assert_not_called()
    assert "the Ceph data could not be read" not in caplog.text


@pytest.mark.parametrize("crush_current", [True, False])
def test_unreadable_crush_map_keeps_crush_buckets_only(neo4j_session, crush_current):
    """
    When the CRUSH map could not be read, the Ceph cleanup still runs but keeps
    the CRUSH buckets, and the sync does not fail.
    """
    _wipe(neo4j_session)
    result = cartography.intel.proxmox.ceph.CephSyncResult(
        current=True, crush_current=crush_current
    )

    with (
        patch.object(cartography.intel.proxmox.ceph, "sync", return_value=result),
        patch.object(cartography.intel.proxmox.ceph, "cleanup") as ceph_cleanup,
    ):
        _run_ingestion(neo4j_session, 1, MOCK_POOL_DETAILS, MOCK_ACL_DATA)

    ceph_cleanup.assert_called_once()
    assert ceph_cleanup.call_args.kwargs == {"include_crush": crush_current}


def test_analysis_failure_is_reported_with_the_other_failed_modules(
    neo4j_session,
    caplog,
):
    """
    A failing effective permissions analysis does not hide the modules that
    failed before it: the final error names all of them.
    """
    _wipe(neo4j_session)

    with (
        patch.object(
            cartography.intel.proxmox.pool,
            "sync",
            side_effect=RuntimeError("pool API down"),
        ),
        patch.object(
            cartography.intel.proxmox,
            "run_typed_analysis_job",
            side_effect=RuntimeError("analysis failed"),
        ),
        pytest.raises(
            ProxmoxSyncError,
            match="modules: pool, effective permissions$",
        ),
        caplog.at_level(logging.ERROR, logger="cartography.intel.proxmox"),
    ):
        _run_ingestion(neo4j_session, 1, MOCK_POOL_DETAILS, MOCK_ACL_DATA)

    assert "Proxmox effective permissions analysis failed" in caplog.text
