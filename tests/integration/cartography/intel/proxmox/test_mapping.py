"""
Integration tests for Proxmox resource mapping sync.
"""

from typing import Any
from unittest.mock import MagicMock
from unittest.mock import patch

import cartography.intel.proxmox.compute
import cartography.intel.proxmox.mapping
from cartography.graph.job import GraphJob
from cartography.models.proxmox.mapping import ProxmoxResourceMappingSchema
from tests.data.proxmox.mapping import MOCK_DIR_MAPPINGS
from tests.data.proxmox.mapping import MOCK_GUEST_CONFIGS
from tests.data.proxmox.mapping import MOCK_PCI_MAPPINGS
from tests.data.proxmox.mapping import MOCK_USB_MAPPINGS
from tests.integration.util import check_nodes
from tests.integration.util import check_rels

TEST_UPDATE_TAG = 123456789
TEST_CLUSTER_ID = "test-cluster"

MOCK_GUESTS = {
    "node1": [{"vmid": 100, "name": "ml", "type": "qemu", "node": "node1"}],
    "node2": [{"vmid": 101, "name": "batch", "type": "qemu", "node": "node2"}],
}


def _sync_compute(neo4j_session, common_job_parameters: dict[str, Any]):
    proxmox = MagicMock()
    proxmox.nodes.get.return_value = [{"node": "node1"}, {"node": "node2"}]
    compute = cartography.intel.proxmox.compute
    with (
        patch.object(
            compute,
            "get_vms_for_node",
            side_effect=lambda _c, node: MOCK_GUESTS[node],
        ),
        patch.object(compute, "get_containers_for_node", return_value=[]),
        patch.object(
            compute,
            "get_vm_config",
            side_effect=lambda _c, node, vmid, vm_type: MOCK_GUEST_CONFIGS[
                f"{node}/{vm_type}/{vmid}"
            ],
        ),
    ):
        return compute.sync(
            neo4j_session,
            proxmox,
            TEST_CLUSTER_ID,
            TEST_UPDATE_TAG,
            common_job_parameters,
        )


@patch.object(
    cartography.intel.proxmox.mapping,
    "get_dir_mappings",
    return_value=MOCK_DIR_MAPPINGS,
)
@patch.object(
    cartography.intel.proxmox.mapping,
    "get_usb_mappings",
    return_value=MOCK_USB_MAPPINGS,
)
@patch.object(
    cartography.intel.proxmox.mapping,
    "get_pci_mappings",
    return_value=MOCK_PCI_MAPPINGS,
)
def test_sync_resource_mappings(mock_pci, mock_usb, mock_dir, neo4j_session):
    """
    Mappings link to the nodes in their map and to the VMs whose configuration
    references them, and are removed once they disappear from the API.
    """
    neo4j_session.run("MATCH (n) DETACH DELETE n")
    neo4j_session.run(
        """
        MERGE (c:ProxmoxCluster {id: $cluster_id})
        MERGE (n1:ProxmoxNode {id: $cluster_id + '/node1'})
        MERGE (n2:ProxmoxNode {id: $cluster_id + '/node2'})
        """,
        cluster_id=TEST_CLUSTER_ID,
    )
    common_job_parameters: dict[str, Any] = {
        "UPDATE_TAG": TEST_UPDATE_TAG,
        "CLUSTER_ID": TEST_CLUSTER_ID,
    }

    # Act - compute returns the mapping references found in VM configs
    refs = _sync_compute(neo4j_session, common_job_parameters)
    cartography.intel.proxmox.mapping.sync(
        neo4j_session,
        MagicMock(),
        TEST_CLUSTER_ID,
        TEST_UPDATE_TAG,
        common_job_parameters,
        guest_mapping_refs=refs,
    )

    # Assert - one node per mapping, attached to the cluster
    assert check_nodes(
        neo4j_session,
        "ProxmoxResourceMapping",
        ["id", "mapping_id", "type", "cluster_id"],
    ) == {
        ("test-cluster/pci/gpu", "gpu", "pci", TEST_CLUSTER_ID),
        ("test-cluster/usb/token", "token", "usb", TEST_CLUSTER_ID),
        ("test-cluster/dir/shared", "shared", "dir", TEST_CLUSTER_ID),
    }
    assert check_rels(
        neo4j_session,
        "ProxmoxCluster",
        "id",
        "ProxmoxResourceMapping",
        "id",
        "RESOURCE",
        rel_direction_right=True,
    ) == {
        (TEST_CLUSTER_ID, "test-cluster/pci/gpu"),
        (TEST_CLUSTER_ID, "test-cluster/usb/token"),
        (TEST_CLUSTER_ID, "test-cluster/dir/shared"),
    }

    # Assert - mappings are available on the nodes listed in their map
    assert check_rels(
        neo4j_session,
        "ProxmoxResourceMapping",
        "id",
        "ProxmoxNode",
        "id",
        "AVAILABLE_ON",
        rel_direction_right=True,
    ) == {
        ("test-cluster/pci/gpu", "test-cluster/node1"),
        ("test-cluster/pci/gpu", "test-cluster/node2"),
        ("test-cluster/usb/token", "test-cluster/node1"),
        ("test-cluster/dir/shared", "test-cluster/node1"),
        ("test-cluster/dir/shared", "test-cluster/node2"),
    }

    # Assert - VMs link to the mappings their config references; VM 101 uses
    # a raw PCI address and a host USB port, so only its virtiofs share counts
    assert check_rels(
        neo4j_session,
        "ProxmoxVM",
        "id",
        "ProxmoxResourceMapping",
        "id",
        "USES_MAPPING",
        rel_direction_right=True,
    ) == {
        ("test-cluster/node1/qemu/100", "test-cluster/pci/gpu"),
        ("test-cluster/node1/qemu/100", "test-cluster/usb/token"),
        ("test-cluster/node1/qemu/100", "test-cluster/dir/shared"),
        ("test-cluster/node2/qemu/101", "test-cluster/dir/shared"),
    }

    # Act - the USB mapping is deleted in Proxmox
    mock_usb.return_value = []
    common_job_parameters["UPDATE_TAG"] = TEST_UPDATE_TAG + 1
    cartography.intel.proxmox.mapping.sync(
        neo4j_session,
        MagicMock(),
        TEST_CLUSTER_ID,
        TEST_UPDATE_TAG + 1,
        common_job_parameters,
        guest_mapping_refs=refs,
    )
    GraphJob.from_node_schema(
        ProxmoxResourceMappingSchema(),
        common_job_parameters,
    ).run(neo4j_session)

    # Assert - the stale mapping and its edges are gone
    assert check_nodes(neo4j_session, "ProxmoxResourceMapping", ["id"]) == {
        ("test-cluster/pci/gpu",),
        ("test-cluster/dir/shared",),
    }
