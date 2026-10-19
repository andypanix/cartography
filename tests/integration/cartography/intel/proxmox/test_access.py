"""
Integration tests for Proxmox access control sync.
"""

from contextlib import ExitStack
from typing import Any
from unittest.mock import patch

import pytest

import cartography.intel.proxmox.access
from cartography.analysis.proxmox.analysis import PROXMOX_EFFECTIVE_PERMISSIONS
from cartography.util import run_typed_analysis_job
from tests.data.proxmox.access import MOCK_ACL_DATA
from tests.data.proxmox.access import MOCK_GROUP_DATA
from tests.data.proxmox.access import MOCK_GROUP_MEMBERS_DATA
from tests.data.proxmox.access import MOCK_REALM_DATA
from tests.data.proxmox.access import MOCK_REALM_DETAILS
from tests.data.proxmox.access import MOCK_REALM_SYNC_JOB_DATA
from tests.data.proxmox.access import MOCK_ROLE_DATA
from tests.data.proxmox.access import MOCK_TFA_DATA
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

# root@pam!monitoring has an ACL on local-lvm, but that grant belongs to the
# token: root@pam itself does not reach local-lvm.
EXPECTED_USER_PERMISSIONS = {
    ("test-cluster/root@pam", TEST_CLUSTER_ID),
    ("test-cluster/admin@pve", TEST_CLUSTER_ID),
    ("test-cluster/readonly@pam", "test-cluster/node1/qemu/100"),
    ("test-cluster/readonly@pam", "test-cluster/local-lvm"),
    ("test-cluster/admin@pve", "test-cluster/production"),
    ("test-cluster/root@pam", "test-cluster/node1"),
}

EXPECTED_GROUP_PERMISSIONS = {
    ("test-cluster/admins", TEST_CLUSTER_ID),
    ("test-cluster/auditors", "test-cluster/local-lvm"),
    ("test-cluster/operators", "test-cluster/node1"),
}

TOKEN_ACL_ID = "test-cluster//storage/local-lvm:root@pam!monitoring:PVEAuditor"


@pytest.fixture
def access_api():
    """Mock every Proxmox access control API call with the shared test data."""
    module = cartography.intel.proxmox.access
    returns = {
        "get_realms": MOCK_REALM_DATA,
        "get_realm_details": MOCK_REALM_DETAILS,
        "get_realm_sync_jobs": MOCK_REALM_SYNC_JOB_DATA,
        "get_users": MOCK_USER_DATA,
        "get_tfa": MOCK_TFA_DATA,
        "get_groups": MOCK_GROUP_DATA,
        "get_roles": MOCK_ROLE_DATA,
        "get_acls": MOCK_ACL_DATA,
        "get_group_members": MOCK_GROUP_MEMBERS_DATA,
    }
    with ExitStack() as stack:
        for name, value in returns.items():
            stack.enter_context(patch.object(module, name, return_value=value))
        yield


def _common_job_parameters() -> dict[str, Any]:
    return {"UPDATE_TAG": TEST_UPDATE_TAG, "CLUSTER_ID": TEST_CLUSTER_ID}


def _seed_cluster(neo4j_session) -> None:
    neo4j_session.run("MATCH (n) DETACH DELETE n")
    neo4j_session.run(
        """
        MERGE (c:ProxmoxCluster {id: $cluster_id})
        SET c.name = $cluster_id, c.lastupdated = $update_tag
        """,
        cluster_id=TEST_CLUSTER_ID,
        update_tag=TEST_UPDATE_TAG,
    )


def _seed_acl_resources(neo4j_session) -> None:
    """Create the cluster resources the mock ACLs point at."""
    _seed_cluster(neo4j_session)
    neo4j_session.run(
        """
        MERGE (vm:ProxmoxVM {id: 'test-cluster/node1/qemu/100'})
        SET vm.vmid = 100, vm.cluster_id = $cluster_id, vm.name = 'test-vm',
            vm.lastupdated = $update_tag
        MERGE (s:ProxmoxStorage {id: 'test-cluster/local-lvm'})
        SET s.name = 'local-lvm', s.lastupdated = $update_tag
        MERGE (p:ProxmoxPool {id: 'test-cluster/production'})
        SET p.poolid = 'production', p.lastupdated = $update_tag
        MERGE (n:ProxmoxNode {id: 'test-cluster/node1'})
        SET n.name = 'node1', n.lastupdated = $update_tag
        """,
        cluster_id=TEST_CLUSTER_ID,
        update_tag=TEST_UPDATE_TAG,
    )


def _sync(neo4j_session) -> None:
    cartography.intel.proxmox.access.sync(
        neo4j_session,
        None,  # proxmox_client mocked
        TEST_CLUSTER_ID,
        TEST_UPDATE_TAG,
        _common_job_parameters(),
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


def test_sync_access_control(access_api, neo4j_session):
    """
    Test that access control (users, groups, roles, ACLs) sync correctly.
    """
    # Arrange
    _seed_cluster(neo4j_session)

    # Act
    _sync(neo4j_session)

    # Assert - Users exist
    expected_users = {
        ("test-cluster/root@pam", "root@example.com"),
        ("test-cluster/admin@pve", "admin@example.com"),
        ("test-cluster/readonly@pam", "readonly@example.com"),
        ("test-cluster/disabled@pam", "disabled@example.com"),
    }
    assert check_nodes(neo4j_session, "ProxmoxUser", ["id", "email"]) == expected_users

    # Assert - Groups exist
    expected_groups = {
        ("test-cluster/admins", "Administrator group"),
        ("test-cluster/operators", "Operator group"),
        ("test-cluster/auditors", "Read-only auditor group"),
    }
    assert (
        check_nodes(neo4j_session, "ProxmoxGroup", ["id", "comment"]) == expected_groups
    )

    # Assert - Roles exist
    expected_roles = {
        ("test-cluster/Administrator", True),
        ("test-cluster/PVEAuditor", True),
        ("test-cluster/CustomRole", False),
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
    assert result.single()["count"] == len(MOCK_ACL_DATA)

    # Assert - User to cluster relationships
    expected_user_rels = {
        ("test-cluster/root@pam", TEST_CLUSTER_ID),
        ("test-cluster/admin@pve", TEST_CLUSTER_ID),
        ("test-cluster/readonly@pam", TEST_CLUSTER_ID),
        ("test-cluster/disabled@pam", TEST_CLUSTER_ID),
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
        ("/storage/local-lvm", "PVEAuditor"),
        ("/vms", "PVEAuditor"),
        ("/vms/100", "CustomRole"),
    ]

    # Assert - ACL to user relationships; the token ACL is not among them
    assert check_rels(
        neo4j_session,
        "ProxmoxACL",
        "id",
        "ProxmoxUser",
        "id",
        "APPLIES_TO_USER",
        rel_direction_right=True,
    ) == {
        ("test-cluster//:root@pam:Administrator", "test-cluster/root@pam"),
        (
            "test-cluster//pool/production:admin@pve:CustomRole",
            "test-cluster/admin@pve",
        ),
        ("test-cluster//vms/100:readonly@pam:CustomRole", "test-cluster/readonly@pam"),
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
        ("test-cluster//:admins:Administrator", "test-cluster/admins"),
        ("test-cluster//nodes/node1:operators:PVEAuditor", "test-cluster/operators"),
        (
            "test-cluster//storage/local-lvm:auditors:PVEAuditor",
            "test-cluster/auditors",
        ),
        ("test-cluster//vms:auditors:PVEAuditor", "test-cluster/auditors"),
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


def test_sync_api_tokens(access_api, neo4j_session):
    """API tokens hang off their user, and token ACLs link to the token."""
    # Arrange
    _seed_cluster(neo4j_session)

    # Act
    _sync(neo4j_session)

    # Assert - tokens exist with their privilege separation flag
    assert check_nodes(
        neo4j_session,
        "ProxmoxAPIToken",
        ["id", "full_tokenid", "privsep", "cluster_id"],
    ) == {
        (
            "test-cluster/root@pam!monitoring",
            "root@pam!monitoring",
            True,
            TEST_CLUSTER_ID,
        ),
        (
            "test-cluster/root@pam!automation",
            "root@pam!automation",
            False,
            TEST_CLUSTER_ID,
        ),
    }
    assert check_rels(
        neo4j_session,
        "ProxmoxUser",
        "id",
        "ProxmoxAPIToken",
        "id",
        "HAS_API_TOKEN",
        rel_direction_right=True,
    ) == {
        ("test-cluster/root@pam", "test-cluster/root@pam!monitoring"),
        ("test-cluster/root@pam", "test-cluster/root@pam!automation"),
    }
    assert check_rels(
        neo4j_session,
        "ProxmoxAPIToken",
        "id",
        "ProxmoxCluster",
        "id",
        "RESOURCE",
        rel_direction_right=False,
    ) == {
        ("test-cluster/root@pam!monitoring", TEST_CLUSTER_ID),
        ("test-cluster/root@pam!automation", TEST_CLUSTER_ID),
    }

    # Assert - the token ACL applies to the token and not to its user
    assert check_rels(
        neo4j_session,
        "ProxmoxACL",
        "id",
        "ProxmoxAPIToken",
        "id",
        "APPLIES_TO_TOKEN",
        rel_direction_right=True,
    ) == {(TOKEN_ACL_ID, "test-cluster/root@pam!monitoring")}
    assert (TOKEN_ACL_ID, "token") in check_nodes(
        neo4j_session, "ProxmoxACL", ["id", "principal_type"]
    )


def test_sync_realms_and_tfa(access_api, neo4j_session):
    """Realms, realm sync jobs, and second factors load and link to users."""
    # Arrange
    _seed_cluster(neo4j_session)

    # Act
    _sync(neo4j_session)

    # Assert - realms, with details only for LDAP and OpenID, and no secrets
    assert check_nodes(
        neo4j_session,
        "ProxmoxRealm",
        ["id", "type", "default", "server1", "client_id"],
    ) == {
        ("test-cluster/pam", "pam", False, None, None),
        ("test-cluster/pve", "pve", True, None, None),
        ("test-cluster/corp", "ldap", False, "ldap1.example.com", None),
        ("test-cluster/sso", "openid", False, None, "proxmox"),
    }
    result = neo4j_session.run(
        """
        MATCH (r:ProxmoxRealm)
        UNWIND keys(r) AS key
        WITH r, key
        WHERE toString(r[key]) IN ['ldap-bind-secret', 'openid-client-secret']
        RETURN count(*) AS leaked
        """
    )
    assert result.single()["leaked"] == 0

    # Assert - users link to their realm
    assert check_rels(
        neo4j_session,
        "ProxmoxUser",
        "id",
        "ProxmoxRealm",
        "id",
        "IN_REALM",
        rel_direction_right=True,
    ) == {
        ("test-cluster/root@pam", "test-cluster/pam"),
        ("test-cluster/admin@pve", "test-cluster/pve"),
        ("test-cluster/readonly@pam", "test-cluster/pam"),
        ("test-cluster/disabled@pam", "test-cluster/pam"),
    }

    # Assert - realm sync job links to its realm
    assert check_rels(
        neo4j_session,
        "ProxmoxRealmSyncJob",
        "id",
        "ProxmoxRealm",
        "id",
        "SYNCS",
        rel_direction_right=True,
    ) == {("test-cluster/corp-nightly", "test-cluster/corp")}
    assert check_rels(
        neo4j_session,
        "ProxmoxRealmSyncJob",
        "id",
        "ProxmoxCluster",
        "id",
        "RESOURCE",
        rel_direction_right=False,
    ) == {("test-cluster/corp-nightly", TEST_CLUSTER_ID)}

    # Assert - TFA summary on users
    result = neo4j_session.run(
        """
        MATCH (u:ProxmoxUser)
        RETURN u.userid AS userid, u.tfa_enabled AS enabled,
               u.tfa_types AS types, u.totp_locked AS locked
        """
    )
    assert {
        (r["userid"], r["enabled"], tuple(r["types"]), r["locked"]) for r in result
    } == {
        ("root@pam", True, ("recovery", "totp"), None),
        ("admin@pve", False, (), None),
        ("readonly@pam", False, (), True),
        ("disabled@pam", False, (), None),
    }

    # Assert - each second factor links to its user
    assert check_rels(
        neo4j_session,
        "ProxmoxUser",
        "id",
        "ProxmoxTFAFactor",
        "id",
        "HAS_TFA_FACTOR",
        rel_direction_right=True,
    ) == {
        ("test-cluster/root@pam", "test-cluster/root@pam/totp-1"),
        ("test-cluster/root@pam", "test-cluster/root@pam/recovery"),
        ("test-cluster/root@pam", "test-cluster/root@pam/webauthn-1"),
    }


def test_acl_resource_relationships(access_api, neo4j_session):
    """
    Test that ACL-to-resource relationships are created correctly.
    """
    # Arrange
    _seed_acl_resources(neo4j_session)

    # Act
    _sync(neo4j_session)

    # Assert - ACL to resource relationships, one target label at a time
    expected_targets = {
        "ProxmoxCluster": {
            ("test-cluster//:root@pam:Administrator", TEST_CLUSTER_ID),
            ("test-cluster//:admins:Administrator", TEST_CLUSTER_ID),
        },
        "ProxmoxVM": {
            (
                "test-cluster//vms/100:readonly@pam:CustomRole",
                "test-cluster/node1/qemu/100",
            )
        },
        "ProxmoxStorage": {
            (
                "test-cluster//storage/local-lvm:auditors:PVEAuditor",
                "test-cluster/local-lvm",
            ),
            (TOKEN_ACL_ID, "test-cluster/local-lvm"),
        },
        "ProxmoxPool": {
            (
                "test-cluster//pool/production:admin@pve:CustomRole",
                "test-cluster/production",
            )
        },
        "ProxmoxNode": {
            ("test-cluster//nodes/node1:operators:PVEAuditor", "test-cluster/node1")
        },
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


def test_effective_permissions(access_api, neo4j_session):
    """
    Test that effective permission relationships are created correctly.
    """
    # Arrange
    _seed_acl_resources(neo4j_session)

    # Act
    _sync(neo4j_session)
    run_typed_analysis_job(
        PROXMOX_EFFECTIVE_PERMISSIONS,
        neo4j_session,
        _common_job_parameters(),
    )

    # Assert - Users get permissions from their own ACLs and their groups' ACLs:
    # root@pam reaches node1 only through the operators group, and not
    # local-lvm, which only its monitoring token was granted.
    assert _permissions(neo4j_session, "ProxmoxUser") == EXPECTED_USER_PERMISSIONS

    # Assert - Groups get permissions from the ACLs that name them
    assert _permissions(neo4j_session, "ProxmoxGroup") == EXPECTED_GROUP_PERMISSIONS
