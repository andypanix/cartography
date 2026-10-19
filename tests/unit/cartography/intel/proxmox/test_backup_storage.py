"""
Unit tests for Proxmox backup coverage, storage content, and replication transforms.
"""

from unittest.mock import MagicMock
from unittest.mock import patch

import requests
from proxmoxer.core import ResourceException

import cartography.intel.proxmox.replication as replication
import cartography.intel.proxmox.storage as storage
from cartography.intel.proxmox.backup_coverage import transform_backup_coverage
from cartography.intel.proxmox.backup_coverage import transform_included_volumes
from cartography.intel.proxmox.backup_coverage import transform_vzdump_defaults
from cartography.intel.proxmox.storage_content import listable_storage_keys
from cartography.intel.proxmox.storage_content import plan_content_reads
from cartography.intel.proxmox.storage_content import transform_storage_content
from tests.data.proxmox.backup_coverage import MOCK_INCLUDED_VOLUMES
from tests.data.proxmox.backup_coverage import MOCK_NOT_BACKED_UP
from tests.data.proxmox.backup_coverage import MOCK_VZDUMP_DEFAULTS
from tests.data.proxmox.replication import MOCK_NODE_REPLICATION
from tests.data.proxmox.replication import MOCK_REPLICATION_JOBS
from tests.data.proxmox.replication import MOCK_REPLICATION_STATUS
from tests.data.proxmox.storage_content import MOCK_NODE_STORAGE_STATUS
from tests.data.proxmox.storage_content import MOCK_STORAGE_CONTENT

CLUSTER_ID = "c1"


def test_transform_included_volumes_skips_unknown_guests_and_excluded_disks():
    guests, disks = transform_included_volumes(
        "backup-all",
        MOCK_INCLUDED_VOLUMES["backup-all"],
        CLUSTER_ID,
    )

    assert guests == [
        {"job_id": "c1/backup-all", "vmid": 100, "cluster_id": CLUSTER_ID},
        {"job_id": "c1/backup-all", "vmid": 200, "cluster_id": CLUSTER_ID},
    ]
    assert disks == [
        {
            "job_id": "c1/backup-all",
            "vmid": 100,
            "disk_id": "scsi0",
            "cluster_id": CLUSTER_ID,
        },
        {
            "job_id": "c1/backup-all",
            "vmid": 200,
            "disk_id": "rootfs",
            "cluster_id": CLUSTER_ID,
        },
    ]


def test_transform_included_volumes_handles_empty_tree():
    assert transform_included_volumes("job", {}, CLUSTER_ID) == ([], [])


def test_transform_backup_coverage_flags_uncovered_guests():
    guests = [
        {"id": "c1/n/qemu/100", "vmid": 100},
        {"id": "c1/n/qemu/101", "vmid": 101},
    ]

    assert transform_backup_coverage(guests, MOCK_NOT_BACKED_UP) == [
        {"id": "c1/n/qemu/100", "backup_covered": True},
        {"id": "c1/n/qemu/101", "backup_covered": False},
    ]


def test_transform_vzdump_defaults_parses_prune_settings_and_flags():
    by_node = {
        d["node"]: d
        for d in transform_vzdump_defaults(MOCK_VZDUMP_DEFAULTS, CLUSTER_ID)
    }

    node1 = by_node["node1"]
    assert node1["id"] == "c1/node1"
    assert node1["node_id"] == "c1/node1"
    assert node1["storage_id"] == "c1/pbs"
    assert node1["prune_keep_daily"] == 7
    assert node1["prune_keep_last"] == 3
    assert node1["prune_keep_all"] is None
    assert node1["protected"] is False
    assert node1["remove"] is True
    assert node1["exclude_path"] == ["/tmp/?*", "/var/tmp/?*"]
    assert node1["notes_template"] == "{{guestname}}"
    assert node1["fleecing_enabled"] is True
    assert node1["fleecing_storage"] == "local-lvm"
    assert node1["performance_max_workers"] == 16
    assert node1["performance_pbs_entries_max"] == 1048576
    for value in node1.values():
        assert not isinstance(value, dict)

    node2 = by_node["node2"]
    assert node2["storage_id"] is None
    assert node2["prune_keep_all"] is True
    assert node2["protected"] is None
    assert node2["fleecing_enabled"] is False
    assert node2["fleecing_storage"] is None
    assert node2["performance_max_workers"] is None


def test_plan_content_reads_lists_shared_storage_once_and_skips_guest_only_storage():
    assert plan_content_reads(MOCK_NODE_STORAGE_STATUS) == [
        ("node1", "local", False),
        ("node1", "pbs", True),
        ("node2", "local", False),
    ]


def test_listable_storage_keys_include_inactive_storage_and_skip_guest_only_storage():
    assert listable_storage_keys(MOCK_NODE_STORAGE_STATUS) == {
        ("node1", "local"),
        ("node2", "local"),
        (None, "pbs"),
        (None, "nfs-old"),
    }


def test_transform_storage_content_scopes_local_ids_by_node():
    archives, templates = transform_storage_content(
        MOCK_STORAGE_CONTENT[("node2", "local")],
        "node2",
        "local",
        False,
        CLUSTER_ID,
    )

    # The rootdir volume is not ingested; the backup without a content field
    # is recognised from its volume ID.
    assert templates == []
    assert [a["id"] for a in archives] == [
        "c1/node2/local:backup/vzdump-qemu-100-2026_10_01-02_00_00.vma.zst",
    ]
    assert archives[0]["node"] == "node2"
    assert archives[0]["storage_id"] == "c1/local"


def test_transform_storage_content_reads_pbs_encryption_and_verification():
    archives, templates = transform_storage_content(
        MOCK_STORAGE_CONTENT[("node1", "pbs")],
        "node1",
        "pbs",
        True,
        CLUSTER_ID,
    )

    assert templates == []
    by_vmid = {a["vmid"]: a for a in archives}
    assert by_vmid[200]["id"] == "c1/pbs:backup/ct/200/2026-10-01T03:00:00Z"
    assert by_vmid[200]["node"] is None
    assert by_vmid[200]["encrypted"] is True
    assert by_vmid[200]["encryption_key_fingerprint"] == "aa:bb:cc"
    assert by_vmid[200]["verification_state"] == "ok"
    assert by_vmid[100]["encrypted"] is True
    assert by_vmid[100]["encryption_key_fingerprint"] is None
    assert by_vmid[100]["size"] == 4294967296
    assert by_vmid[100]["verification_state"] == "failed"


def test_transform_storage_content_splits_templates():
    archives, templates = transform_storage_content(
        MOCK_STORAGE_CONTENT[("node1", "local")],
        "node1",
        "local",
        False,
        CLUSTER_ID,
    )

    assert [(a["vmid"], a["protected"], a["encrypted"]) for a in archives] == [
        (100, True, False),
    ]
    assert {(t["content"], t["volid"]) for t in templates} == {
        ("iso", "local:iso/debian-13.iso"),
        ("vztmpl", "local:vztmpl/debian-13-standard_13.0-1_amd64.tar.zst"),
    }


def test_transform_replication_jobs_merges_state():
    states = {
        "100-0": MOCK_NODE_REPLICATION["node1"][0],
        "200-0": MOCK_REPLICATION_STATUS[("node2", "200-0")],
    }

    jobs = {
        j["job_id"]: j
        for j in replication.transform_replication_jobs(
            MOCK_REPLICATION_JOBS,
            states,
            CLUSTER_ID,
        )
    }

    assert jobs["100-0"]["id"] == "c1/100-0"
    assert jobs["100-0"]["target_node_id"] == "c1/node2"
    assert jobs["100-0"]["enabled"] is True
    assert jobs["100-0"]["fail_count"] == 2
    assert jobs["100-0"]["error"].startswith("storage 'local-zfs'")
    assert jobs["200-0"]["enabled"] is False
    assert jobs["200-0"]["schedule"] == "*/15"
    assert jobs["200-0"]["last_sync"] == 1790800000
    assert jobs["200-0"]["duration"] is None


def test_read_states_calls_job_status_only_for_id_only_entries():
    with (
        patch.object(
            replication.cluster,
            "get_nodes",
            return_value=[
                {"node": "node1", "status": "online"},
                {"node": "node2", "status": "online"},
                {"node": "node3", "status": "offline"},
            ],
        ),
        patch.object(
            replication,
            "get_node_replication_status",
            side_effect=lambda _c, node: MOCK_NODE_REPLICATION[node],
        ) as node_status,
        patch.object(
            replication,
            "get_replication_job_status",
            side_effect=lambda _c, node, job: MOCK_REPLICATION_STATUS[(node, job)],
        ) as job_status,
    ):
        states = replication._read_states(MagicMock())

    assert [c.args[1] for c in node_status.call_args_list] == ["node1", "node2"]
    job_status.assert_called_once()
    assert states["200-0"]["last_sync"] == 1790800000
    assert states["100-0"]["fail_count"] == 2


def test_shared_storage_identity_stops_on_unavailable_endpoint():
    client = MagicMock()
    client.nodes.return_value.storage.return_value.identity.get.side_effect = (
        ResourceException(501, "Not Implemented", "")
    )
    storage_list = [
        {"storage": "pbs", "shared": 1},
        {"storage": "ceph", "shared": 1},
        {"storage": "local", "shared": 0},
    ]
    status_map = {
        "node1": [
            {"storage": "pbs", "active": 1},
            {"storage": "ceph", "active": 1},
            {"storage": "local", "active": 1},
        ],
    }

    assert storage.get_shared_storage_identities(client, storage_list, status_map) == {}
    assert client.nodes.return_value.storage.return_value.identity.get.call_count == 1


def test_shared_storage_identity_reads_active_shared_storage_only():
    client = MagicMock()
    client.nodes.return_value.storage.return_value.identity.get.return_value = {
        "id": "pbs-store-id",
        "type": "pbs",
    }
    storage_list = [
        {"storage": "pbs", "shared": 1},
        {"storage": "offline", "shared": 1},
        {"storage": "local", "shared": 0},
    ]
    status_map = {
        "node1": [
            {"storage": "pbs", "active": 1},
            {"storage": "offline", "active": 0},
        ],
    }

    assert storage.get_shared_storage_identities(client, storage_list, status_map) == {
        "pbs": "pbs-store-id",
    }
    client.nodes.assert_called_once_with("node1")
    client.nodes.return_value.storage.assert_called_once_with("pbs")


def test_shared_storage_identity_skips_plugins_without_identity():
    """A storage plugin without identity answers 500; the other storages are still read."""
    client = MagicMock()
    client.nodes.return_value.storage.return_value.identity.get.side_effect = [
        ResourceException(
            500,
            "Internal Server Error",
            "get_identity not implemented for this plugin at "
            "/usr/share/perl5/PVE/Storage/Plugin.pm line 2687.",
        ),
        {"id": "pbs-store-id", "type": "pbs"},
    ]
    storage_list = [
        {"storage": "nfs-share", "shared": 1},
        {"storage": "pbs", "shared": 1},
    ]
    status_map = {
        "node1": [
            {"storage": "nfs-share", "active": 1},
            {"storage": "pbs", "active": 1},
        ],
    }

    assert storage.get_shared_storage_identities(client, storage_list, status_map) == {
        "pbs": "pbs-store-id",
    }


def test_shared_storage_identity_skips_failing_storage_and_reads_the_rest():
    """A 404 or another error on one storage does not stop the identity reads."""
    client = MagicMock()
    client.nodes.return_value.storage.return_value.identity.get.side_effect = [
        ResourceException(404, "Not Found", "storage 'gone' does not exist"),
        ResourceException(500, "Internal Server Error", "storage is not online"),
        requests.exceptions.TooManyRedirects("too many redirects"),
        {"id": "pbs-store-id", "type": "pbs"},
    ]
    storage_list = [
        {"storage": "gone", "shared": 1},
        {"storage": "down", "shared": 1},
        {"storage": "redirect", "shared": 1},
        {"storage": "pbs", "shared": 1},
    ]
    status_map = {
        "node1": [
            {"storage": name, "active": 1}
            for name in ("gone", "down", "redirect", "pbs")
        ],
    }

    assert storage.get_shared_storage_identities(client, storage_list, status_map) == {
        "pbs": "pbs-store-id",
    }
