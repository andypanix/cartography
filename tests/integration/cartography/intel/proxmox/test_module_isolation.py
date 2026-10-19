"""
Integration tests for the per-module error isolation of start_proxmox_ingestion.
"""

import logging
from unittest.mock import patch

import pytest

import cartography.intel.proxmox
import cartography.intel.proxmox.access
import cartography.intel.proxmox.cluster
import cartography.intel.proxmox.pool
import cartography.intel.proxmox.storage
import cartography.intel.proxmox.storage_content
from cartography.intel.proxmox import ProxmoxSyncError
from tests.data.proxmox.access import MOCK_ACL_DATA
from tests.data.proxmox.pool import MOCK_POOL_DETAILS
from tests.integration.cartography.intel.proxmox.test_relationship_cleanup import _rels
from tests.integration.cartography.intel.proxmox.test_relationship_cleanup import (
    _run_ingestion,
)
from tests.integration.cartography.intel.proxmox.test_relationship_cleanup import _wipe
from tests.integration.util import check_nodes

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
