"""
Integration tests for Proxmox access control sync.
"""

from typing import Any
from unittest.mock import patch

import cartography.intel.proxmox.access
from cartography.analysis.proxmox.analysis import PROXMOX_EFFECTIVE_PERMISSIONS
from cartography.util import run_typed_analysis_job
from tests.data.proxmox.access import MOCK_ACL_DATA
from tests.data.proxmox.access import MOCK_GROUP_DATA
from tests.data.proxmox.access import MOCK_GROUP_MEMBERS_DATA
from tests.data.proxmox.access import MOCK_ROLE_DATA
from tests.data.proxmox.access import MOCK_USER_DATA
from tests.integration.util import check_nodes
from tests.integration.util import check_rels

TEST_UPDATE_TAG = 123456789
TEST_CLUSTER_ID = "test-cluster"

PERMISSION_TARGET_LABELS = (
    "ProxmoxCluster",
    "ProxmoxVM",
    "ProxmoxStorage",
    "ProxmoxPool",
    "ProxmoxNode",
)

EXPECTED_USER_PERMISSIONS = {
    ("root@pam", TEST_CLUSTER_ID),
    ("admin@pve", TEST_CLUSTER_ID),
    ("readonly@pam", "node1/qemu/100"),
    ("readonly@pam", "local-lvm"),
    ("admin@pve", "production"),
    ("root@pam", "node1"),
}

EXPECTED_GROUP_PERMISSIONS = {
    ("admins", TEST_CLUSTER_ID),
    ("auditors", "local-lvm"),
    ("operators", "node1"),
}


def _seed_acl_resources(neo4j_session) -> None:
    """Create the cluster resources the mock ACLs point at."""
    neo4j_session.run(
        """
        MERGE (c:ProxmoxCluster {id: $cluster_id})
        SET c.name = $cluster_id, c.lastupdated = $update_tag
        MERGE (vm:ProxmoxVM {id: 'node1/qemu/100'})
        SET vm.vmid = 100, vm.cluster_id = $cluster_id, vm.name = 'test-vm',
            vm.lastupdated = $update_tag
        MERGE (s:ProxmoxStorage {id: 'local-lvm'})
        SET s.name = 'local-lvm', s.lastupdated = $update_tag
        MERGE (p:ProxmoxPool {id: 'production'})
        SET p.poolid = 'production', p.lastupdated = $update_tag
        MERGE (n:ProxmoxNode {id: 'node1'})
        SET n.name = 'node1', n.lastupdated = $update_tag
        """,
        cluster_id=TEST_CLUSTER_ID,
        update_tag=TEST_UPDATE_TAG,
    )


def _permissions(neo4j_session, principal_label: str) -> set[tuple[str, str]]:
    """Return every HAS_PERMISSION edge from a principal label, as id pairs."""
    permissions: set[tuple[str, str]] = set()
    for target_label in PERMISSION_TARGET_LABELS:
        permissions |= check_rels(
            neo4j_session,
            principal_label,
            "id",
            target_label,
            "id",
            "HAS_PERMISSION",
            rel_direction_right=True,
        )
    return permissions


@patch.object(
    cartography.intel.proxmox.access, "get_users", return_value=MOCK_USER_DATA
)
@patch.object(
    cartography.intel.proxmox.access, "get_groups", return_value=MOCK_GROUP_DATA
)
@patch.object(
    cartography.intel.proxmox.access, "get_roles", return_value=MOCK_ROLE_DATA
)
@patch.object(cartography.intel.proxmox.access, "get_acls", return_value=MOCK_ACL_DATA)
@patch.object(
    cartography.intel.proxmox.access,
    "get_group_members",
    return_value=MOCK_GROUP_MEMBERS_DATA,
)
def test_sync_access_control(
    mock_get_group_members,
    mock_get_acls,
    mock_get_roles,
    mock_get_groups,
    mock_get_users,
    neo4j_session,
):
    """
    Test that access control (users, groups, roles, ACLs) sync correctly.
    """
    # Arrange
    common_job_parameters: dict[str, Any] = {
        "UPDATE_TAG": TEST_UPDATE_TAG,
        "CLUSTER_ID": TEST_CLUSTER_ID,
    }

    # Create cluster first
    neo4j_session.run(
        """
        MERGE (c:ProxmoxCluster {id: $cluster_id})
        SET c.name = $cluster_id,
            c.lastupdated = $update_tag
        """,
        cluster_id=TEST_CLUSTER_ID,
        update_tag=TEST_UPDATE_TAG,
    )

    # Act
    cartography.intel.proxmox.access.sync(
        neo4j_session,
        None,  # proxmox_client mocked
        TEST_CLUSTER_ID,
        TEST_UPDATE_TAG,
        common_job_parameters,
    )

    # Assert - Users exist
    expected_users = {
        ("root@pam", "root@example.com"),
        ("admin@pve", "admin@example.com"),
        ("readonly@pam", "readonly@example.com"),
        ("disabled@pam", "disabled@example.com"),
    }
    assert check_nodes(neo4j_session, "ProxmoxUser", ["id", "email"]) == expected_users

    # Assert - Groups exist
    expected_groups = {
        ("admins", "Administrator group"),
        ("operators", "Operator group"),
        ("auditors", "Read-only auditor group"),
    }
    assert (
        check_nodes(neo4j_session, "ProxmoxGroup", ["id", "comment"]) == expected_groups
    )

    # Assert - Roles exist
    expected_roles = {
        ("Administrator", True),
        ("PVEAuditor", True),
        ("CustomRole", False),
    }
    assert (
        check_nodes(neo4j_session, "ProxmoxRole", ["id", "special"]) == expected_roles
    )

    # Assert - ACLs exist
    result = neo4j_session.run(
        """
        MATCH (acl:ProxmoxACL)
        RETURN count(acl) as count
        """
    )
    assert result.single()["count"] == 7  # Updated to match new test data

    # Assert - User to cluster relationships
    expected_user_rels = {
        ("root@pam", TEST_CLUSTER_ID),
        ("admin@pve", TEST_CLUSTER_ID),
        ("readonly@pam", TEST_CLUSTER_ID),
        ("disabled@pam", TEST_CLUSTER_ID),
    }
    assert (
        check_rels(
            neo4j_session,
            "ProxmoxUser",
            "id",
            "ProxmoxCluster",
            "id",
            "RESOURCE",
            rel_direction_right=False,
        )
        == expected_user_rels
    )

    # Assert - User to group relationships
    result = neo4j_session.run(
        """
        MATCH (u:ProxmoxUser)-[:MEMBER_OF_GROUP]->(g:ProxmoxGroup)
        RETURN u.userid as userid, g.groupid as groupid
        ORDER BY userid, groupid
        """
    )
    user_group_rels = [(r["userid"], r["groupid"]) for r in result]
    assert user_group_rels == [
        ("admin@pve", "admins"),
        ("readonly@pam", "auditors"),
        ("root@pam", "admins"),
        ("root@pam", "operators"),
    ]

    # Assert - ACL to role relationships
    result = neo4j_session.run(
        """
        MATCH (acl:ProxmoxACL)-[:GRANTS_ROLE]->(r:ProxmoxRole)
        RETURN acl.path as path, r.roleid as roleid
        ORDER BY path, roleid
        """
    )
    acl_role_rels = [(r["path"], r["roleid"]) for r in result]
    assert acl_role_rels == [
        ("/", "Administrator"),
        ("/", "Administrator"),
        ("/nodes/node1", "PVEAuditor"),
        ("/pool/production", "CustomRole"),
        ("/storage/local-lvm", "PVEAuditor"),
        ("/vms", "PVEAuditor"),
        ("/vms/100", "CustomRole"),
    ]

    # Assert - ACL to user relationships
    assert check_rels(
        neo4j_session,
        "ProxmoxACL",
        "id",
        "ProxmoxUser",
        "id",
        "APPLIES_TO_USER",
        rel_direction_right=True,
    ) == {
        ("/:root@pam:Administrator", "root@pam"),
        ("/pool/production:admin@pve:CustomRole", "admin@pve"),
        ("/vms/100:readonly@pam:CustomRole", "readonly@pam"),
    }

    # Assert - ACL to group relationships
    assert check_rels(
        neo4j_session,
        "ProxmoxACL",
        "id",
        "ProxmoxGroup",
        "id",
        "APPLIES_TO_GROUP",
        rel_direction_right=True,
    ) == {
        ("/:admins:Administrator", "admins"),
        ("/nodes/node1:operators:PVEAuditor", "operators"),
        ("/storage/local-lvm:auditors:PVEAuditor", "auditors"),
        ("/vms:auditors:PVEAuditor", "auditors"),
    }

    # Assert - User properties
    result = neo4j_session.run(
        """
        MATCH (u:ProxmoxUser {userid: 'root@pam'})
        RETURN u.enable as enable, u.firstname as firstname
        """
    )
    user_props = result.single()
    assert user_props["enable"] is True
    assert user_props["firstname"] == "Root"


@patch.object(
    cartography.intel.proxmox.access, "get_users", return_value=MOCK_USER_DATA
)
@patch.object(
    cartography.intel.proxmox.access, "get_groups", return_value=MOCK_GROUP_DATA
)
@patch.object(
    cartography.intel.proxmox.access, "get_roles", return_value=MOCK_ROLE_DATA
)
@patch.object(cartography.intel.proxmox.access, "get_acls", return_value=MOCK_ACL_DATA)
@patch.object(
    cartography.intel.proxmox.access,
    "get_group_members",
    return_value=MOCK_GROUP_MEMBERS_DATA,
)
def test_acl_resource_relationships(
    mock_get_group_members,
    mock_get_acls,
    mock_get_roles,
    mock_get_groups,
    mock_get_users,
    neo4j_session,
):
    """
    Test that ACL-to-resource relationships are created correctly.
    """
    # Arrange
    common_job_parameters: dict[str, Any] = {
        "UPDATE_TAG": TEST_UPDATE_TAG,
        "CLUSTER_ID": TEST_CLUSTER_ID,
    }

    _seed_acl_resources(neo4j_session)

    # Act
    cartography.intel.proxmox.access.sync(
        neo4j_session,
        None,  # proxmox_client mocked
        TEST_CLUSTER_ID,
        TEST_UPDATE_TAG,
        common_job_parameters,
    )

    # Assert - ACL to resource relationships, one target label at a time
    expected_targets = {
        "ProxmoxCluster": {
            ("/:root@pam:Administrator", TEST_CLUSTER_ID),
            ("/:admins:Administrator", TEST_CLUSTER_ID),
        },
        "ProxmoxVM": {("/vms/100:readonly@pam:CustomRole", "node1/qemu/100")},
        "ProxmoxStorage": {("/storage/local-lvm:auditors:PVEAuditor", "local-lvm")},
        "ProxmoxPool": {("/pool/production:admin@pve:CustomRole", "production")},
        "ProxmoxNode": {("/nodes/node1:operators:PVEAuditor", "node1")},
    }
    for target_label, expected in expected_targets.items():
        assert (
            check_rels(
                neo4j_session,
                "ProxmoxACL",
                "id",
                target_label,
                "id",
                "GRANTS_ACCESS_TO",
                rel_direction_right=True,
            )
            == expected
        ), target_label

    # Assert - ACL properties include resource metadata
    result = neo4j_session.run(
        """
        MATCH (acl:ProxmoxACL {path: '/vms/100'})
        RETURN acl.resource_type as resource_type, acl.resource_id as resource_id
        """
    )
    acl_props = result.single()
    assert acl_props["resource_type"] == "vm"
    assert acl_props["resource_id"] == "100"


@patch.object(
    cartography.intel.proxmox.access, "get_users", return_value=MOCK_USER_DATA
)
@patch.object(
    cartography.intel.proxmox.access, "get_groups", return_value=MOCK_GROUP_DATA
)
@patch.object(
    cartography.intel.proxmox.access, "get_roles", return_value=MOCK_ROLE_DATA
)
@patch.object(cartography.intel.proxmox.access, "get_acls", return_value=MOCK_ACL_DATA)
@patch.object(
    cartography.intel.proxmox.access,
    "get_group_members",
    return_value=MOCK_GROUP_MEMBERS_DATA,
)
def test_effective_permissions(
    mock_get_group_members,
    mock_get_acls,
    mock_get_roles,
    mock_get_groups,
    mock_get_users,
    neo4j_session,
):
    """
    Test that effective permission relationships are created correctly.
    """
    # Arrange
    common_job_parameters: dict[str, Any] = {
        "UPDATE_TAG": TEST_UPDATE_TAG,
        "CLUSTER_ID": TEST_CLUSTER_ID,
    }

    _seed_acl_resources(neo4j_session)

    # Act
    cartography.intel.proxmox.access.sync(
        neo4j_session,
        None,  # proxmox_client mocked
        TEST_CLUSTER_ID,
        TEST_UPDATE_TAG,
        common_job_parameters,
    )
    run_typed_analysis_job(
        PROXMOX_EFFECTIVE_PERMISSIONS,
        neo4j_session,
        common_job_parameters,
    )

    # Assert - Users get permissions from their own ACLs and their groups' ACLs:
    # root@pam reaches node1 only through the operators group.
    assert _permissions(neo4j_session, "ProxmoxUser") == EXPECTED_USER_PERMISSIONS

    # Assert - Groups get permissions from the ACLs that name them
    assert _permissions(neo4j_session, "ProxmoxGroup") == EXPECTED_GROUP_PERMISSIONS
