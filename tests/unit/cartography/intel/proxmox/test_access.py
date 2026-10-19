"""
Tests for Proxmox access control module.
"""

from unittest.mock import MagicMock

import pytest
from proxmoxer.core import ResourceException

from cartography.intel.proxmox import access
from cartography.intel.proxmox.access import transform_acl_data
from cartography.intel.proxmox.access import transform_group_data
from cartography.intel.proxmox.access import transform_realm_data
from cartography.intel.proxmox.access import transform_realm_sync_job_data
from cartography.intel.proxmox.access import transform_role_data
from cartography.intel.proxmox.access import transform_tfa_factor_data
from cartography.intel.proxmox.access import transform_token_data
from cartography.intel.proxmox.access import transform_user_data
from tests.data.proxmox.access import MOCK_REALM_DATA
from tests.data.proxmox.access import MOCK_REALM_DETAILS
from tests.data.proxmox.access import MOCK_REALM_SYNC_JOB_DATA
from tests.data.proxmox.access import MOCK_TFA_DATA
from tests.data.proxmox.access import MOCK_USER_DATA


def test_transform_user_data():
    """Test user data transformation."""
    raw_users = [
        {
            "userid": "root@pam",
            "enable": 1,
            "expire": 0,
            "firstname": "Root",
            "lastname": "User",
            "email": "root@example.com",
            "comment": "Root user",
            "groups": "admins,operators",
        },
        {
            "userid": "test@pve",
            "enable": 0,
            "expire": 1735689600,
            "email": "test@example.com",
        },
        {
            "userid": "sso_user@entraid",
            "enable": 1,
            "expire": 0,
            "email": "sso@example.com",
            "comment": "SSO user",
            "groups": "",  # Empty groups for SSO users
        },
    ]

    group_members = {
        "admins": ["root@pam"],
        "operators": ["root@pam"],
        "sso_group": ["sso_user@entraid"],
    }

    cluster_id = "test-cluster"
    result = transform_user_data(raw_users, cluster_id, group_members)

    assert len(result) == 3

    # Test root user (groups from user data string)
    root = next(u for u in result if u["userid"] == "root@pam")
    assert root["id"] == "test-cluster/root@pam"
    assert root["enable"] is True
    assert root["expire"] == 0
    assert root["firstname"] == "Root"
    assert root["lastname"] == "User"
    assert root["email"] == "root@example.com"
    assert root["groups"] == ["admins", "operators"]
    assert root["group_ids"] == ["test-cluster/admins", "test-cluster/operators"]
    assert root["cluster_id"] == cluster_id

    # Test user with minimal fields (no groups)
    test_user = next(u for u in result if u["userid"] == "test@pve")
    assert test_user["enable"] is False
    assert test_user["expire"] == 1735689600
    assert test_user["firstname"] is None
    assert test_user["groups"] == []

    # Test SSO user (groups enriched from group_members)
    sso_user = next(u for u in result if u["userid"] == "sso_user@entraid")
    assert sso_user["enable"] is True
    assert sso_user["groups"] == ["sso_group"]  # Enriched from group_members
    assert sso_user["email"] == "sso@example.com"


def test_transform_group_data():
    """Test group data transformation."""
    raw_groups = [
        {
            "groupid": "admins",
            "comment": "Administrator group",
        },
        {
            "groupid": "operators",
        },
    ]

    cluster_id = "test-cluster"
    result = transform_group_data(raw_groups, cluster_id)

    assert len(result) == 2

    # Test admins group
    admins = next(g for g in result if g["groupid"] == "admins")
    assert admins["id"] == "test-cluster/admins"
    assert admins["comment"] == "Administrator group"
    assert admins["cluster_id"] == cluster_id

    # Test group without comment
    operators = next(g for g in result if g["groupid"] == "operators")
    assert operators["comment"] is None


def test_transform_role_data():
    """Test role data transformation."""
    raw_roles = [
        {
            "roleid": "Administrator",
            "privs": "VM.Allocate,VM.Config,Sys.Modify",
            "special": 1,
        },
        {
            "roleid": "CustomRole",
            "privs": "VM.Audit",
            "special": 0,
        },
    ]

    cluster_id = "test-cluster"
    result = transform_role_data(raw_roles, cluster_id)

    assert len(result) == 2

    # Test Administrator role
    admin = next(r for r in result if r["roleid"] == "Administrator")
    assert admin["id"] == "test-cluster/Administrator"
    assert admin["privs"] == ["VM.Allocate", "VM.Config", "Sys.Modify"]
    assert admin["special"] is True
    assert admin["cluster_id"] == cluster_id

    # Test custom role
    custom = next(r for r in result if r["roleid"] == "CustomRole")
    assert custom["privs"] == ["VM.Audit"]
    assert custom["special"] is False


def test_transform_acl_data():
    """Test ACL data transformation."""
    raw_acls = [
        {
            "path": "/",
            "roleid": "Administrator",
            "ugid": "root@pam",
            "propagate": 1,
        },
        {
            "path": "/vms/100",
            "roleid": "PVEAuditor",
            "ugid": "auditors",
            "propagate": 0,
        },
        {
            "path": "/storage/local-lvm",
            "roleid": "CustomRole",
            "ugid": "admin@pve",
            "propagate": 1,
        },
        {
            "path": "/pool/production",
            "roleid": "PVEAuditor",
            "ugid": "operators",
            "propagate": 1,
        },
        {
            "path": "/nodes/node1",
            "roleid": "CustomRole",
            "ugid": "admin@pve",
            "propagate": 0,
        },
    ]

    cluster_id = "test-cluster"
    result = transform_acl_data(raw_acls, cluster_id)

    assert len(result) == 5

    # Test root ACL with cluster resource type
    root_acl = next(a for a in result if a["ugid"] == "root@pam")
    assert root_acl["id"] == "test-cluster//:root@pam:Administrator"
    assert root_acl["path"] == "/"
    assert root_acl["roleid"] == "Administrator"
    assert root_acl["target_role_id"] == "test-cluster/Administrator"
    assert root_acl["propagate"] is True
    assert root_acl["cluster_id"] == cluster_id
    assert root_acl["principal_type"] == "user"
    assert root_acl["resource_type"] == "cluster"
    assert root_acl["resource_id"] is None

    # Test group ACL with VM resource type
    group_acl = next(a for a in result if a["path"] == "/vms/100")
    assert group_acl["id"] == "test-cluster//vms/100:auditors:PVEAuditor"
    assert group_acl["path"] == "/vms/100"
    assert group_acl["propagate"] is False
    assert group_acl["principal_type"] == "group"
    assert group_acl["resource_type"] == "vm"
    assert group_acl["resource_id"] == "100"

    # Test storage ACL
    storage_acl = next(a for a in result if a["path"] == "/storage/local-lvm")
    assert storage_acl["principal_type"] == "user"
    assert storage_acl["resource_type"] == "storage"
    assert storage_acl["resource_id"] == "local-lvm"

    # Test pool ACL
    pool_acl = next(a for a in result if a["path"] == "/pool/production")
    assert pool_acl["principal_type"] == "group"
    assert pool_acl["resource_type"] == "pool"
    assert pool_acl["resource_id"] == "production"

    # Test node ACL
    node_acl = next(a for a in result if a["path"] == "/nodes/node1")
    assert node_acl["principal_type"] == "user"
    assert node_acl["resource_type"] == "node"
    assert node_acl["resource_id"] == "node1"


def test_transform_acl_data_sets_relationship_targets():
    """Each ACL sets only the target fields that match its principal and path."""
    acls = [
        {"path": "/", "roleid": "Administrator", "ugid": "root@pam"},
        {"path": "/vms/100", "roleid": "PVEAuditor", "ugid": "ops@pve!ci"},
        {"path": "/storage/local", "roleid": "PVEAuditor", "ugid": "auditors"},
        {"path": "/pool/production", "roleid": "PVEAuditor", "ugid": "auditors"},
        {"path": "/nodes/node1", "roleid": "PVEAuditor", "ugid": "auditors"},
        {"path": "/access", "roleid": "PVEAuditor", "ugid": "auditors"},
    ]
    target_keys = (
        "target_user_id",
        "target_token_id",
        "target_group_id",
        "target_vmid",
        "target_storage_id",
        "target_pool_id",
        "target_node_id",
        "target_cluster_id",
    )

    result = transform_acl_data(acls, "test-cluster")

    targets = {
        acl["id"]: {key: acl[key] for key in target_keys if acl[key] is not None}
        for acl in result
    }
    assert targets == {
        "test-cluster//:root@pam:Administrator": {
            "target_user_id": "test-cluster/root@pam",
            "target_cluster_id": "test-cluster",
        },
        # A token ACL links to the token only, never to the user that owns it.
        "test-cluster//vms/100:ops@pve!ci:PVEAuditor": {
            "target_token_id": "test-cluster/ops@pve!ci",
            "target_vmid": 100,
        },
        "test-cluster//storage/local:auditors:PVEAuditor": {
            "target_group_id": "test-cluster/auditors",
            "target_storage_id": "test-cluster/local",
        },
        "test-cluster//pool/production:auditors:PVEAuditor": {
            "target_group_id": "test-cluster/auditors",
            "target_pool_id": "test-cluster/production",
        },
        "test-cluster//nodes/node1:auditors:PVEAuditor": {
            "target_group_id": "test-cluster/auditors",
            "target_node_id": "test-cluster/node1",
        },
        "test-cluster//access:auditors:PVEAuditor": {
            "target_group_id": "test-cluster/auditors",
        },
    }


def test_transform_acl_data_uses_api_principal_type():
    """The API type wins; the ID format is only a fallback."""
    # Arrange
    acls = [
        {"path": "/", "roleid": "R", "ugid": "u@pve!t", "type": "token"},
        {"path": "/", "roleid": "R", "ugid": "u@pve", "type": "user"},
        {"path": "/", "roleid": "R", "ugid": "ops", "type": "group"},
        {"path": "/", "roleid": "R", "ugid": "u@pve!t2"},
    ]

    # Act
    result = transform_acl_data(acls, "c")

    # Assert
    assert [(a["principal_type"], a["base_userid"]) for a in result] == [
        ("token", "u@pve"),
        ("user", "u@pve"),
        ("group", "ops"),
        ("token", "u@pve"),
    ]


def test_transform_user_data_adds_realm_and_tfa_summary():
    """Users get their realm and a TFA summary built from enabled factors only."""
    # Act
    result = {
        u["userid"]: u
        for u in transform_user_data(MOCK_USER_DATA, "c", None, MOCK_TFA_DATA)
    }

    # Assert
    root = result["root@pam"]
    assert root["realm"] == "pam"
    assert root["realm_id"] == "c/pam"
    assert root["realm_type"] == "pam"
    assert root["tfa_enabled"] is True
    # The disabled webauthn factor does not count.
    assert root["tfa_types"] == ["recovery", "totp"]
    assert root["totp_locked"] is None
    assert "tokens" not in root

    readonly = result["readonly@pam"]
    assert readonly["tfa_enabled"] is False
    assert readonly["tfa_types"] == []
    assert readonly["totp_locked"] is True
    assert readonly["tfa_locked_until"] == 1767225600

    admin = result["admin@pve"]
    assert admin["realm_id"] == "c/pve"
    assert admin["tfa_enabled"] is False


def test_transform_token_data():
    """Tokens listed under each user become one dict each, privsep defaulting on."""
    # Arrange
    users = MOCK_USER_DATA + [
        {"userid": "ci@pve", "tokens": [{"tokenid": "deploy"}]},
    ]

    # Act
    result = {t["id"]: t for t in transform_token_data(users, "c")}

    # Assert
    assert set(result) == {
        "c/root@pam!monitoring",
        "c/root@pam!automation",
        "c/ci@pve!deploy",
    }
    assert result["c/root@pam!monitoring"]["privsep"] is True
    assert result["c/root@pam!monitoring"]["user_id"] == "c/root@pam"
    assert result["c/root@pam!automation"]["privsep"] is False
    assert result["c/root@pam!automation"]["expire"] == 1893456000
    assert result["c/ci@pve!deploy"]["privsep"] is True
    assert result["c/ci@pve!deploy"]["expire"] is None
    assert result["c/ci@pve!deploy"]["full_tokenid"] == "ci@pve!deploy"


def test_transform_tfa_factor_data():
    """Each second factor keeps only its metadata."""
    # Act
    result = transform_tfa_factor_data(MOCK_TFA_DATA, "c")

    # Assert
    assert {(f["id"], f["type"], f["enable"]) for f in result} == {
        ("c/root@pam/totp-1", "totp", True),
        ("c/root@pam/recovery", "recovery", True),
        ("c/root@pam/webauthn-1", "webauthn", False),
    }
    assert set(result[0]) == {
        "id",
        "factor_id",
        "userid",
        "user_id",
        "cluster_id",
        "type",
        "description",
        "enable",
        "created",
    }


def test_transform_realm_data_keeps_only_non_secret_fields():
    """Realm details add server and client settings but never secrets."""
    # Act
    result = {
        r["realm"]: r
        for r in transform_realm_data(MOCK_REALM_DATA, MOCK_REALM_DETAILS, "c")
    }

    # Assert
    assert result["pve"]["default"] is True
    assert result["pam"]["default"] is False
    corp = result["corp"]
    assert corp["tfa"] == "oath"
    assert corp["server1"] == "ldap1.example.com"
    assert corp["mode"] == "ldaps"
    assert corp["verify"] is True
    assert corp["bind_dn"] == "cn=proxmox,dc=example,dc=com"
    sso = result["sso"]
    assert sso["issuer_url"] == "https://sso.example.com/realms/corp"
    assert sso["client_id"] == "proxmox"
    assert sso["autocreate"] is True
    for realm in result.values():
        values = set(map(str, realm.values()))
        assert "ldap-bind-secret" not in values
        assert "openid-client-secret" not in values
        assert not {"password", "client-key", "client_key", "digest"} & set(realm)


def test_transform_realm_sync_job_data():
    """Realm sync jobs point at their realm."""
    # Act
    (job,) = transform_realm_sync_job_data(MOCK_REALM_SYNC_JOB_DATA, "c")

    # Assert
    assert job["id"] == "c/corp-nightly"
    assert job["realm_id"] == "c/corp"
    assert job["enabled"] is True
    assert job["remove_vanished"] == "acl;entry"
    assert job["last_run"] == 1767139200


def test_get_realm_details_skips_pam_and_pve():
    """Only realms with extra configuration are read one by one."""
    # Arrange
    client = MagicMock()
    client.access.domains.return_value.get.return_value = {"server1": "x"}

    # Act
    details = access.get_realm_details(client, MOCK_REALM_DATA)

    # Assert
    assert set(details) == {"corp", "sso"}
    assert [c.args for c in client.access.domains.call_args_list] == [
        ("corp",),
        ("sso",),
    ]


def test_realm_details_forbidden_are_skipped(monkeypatch):
    """A 403 on realm details leaves the realms without details."""

    # Arrange
    def deny(_client, _realms):
        raise ResourceException(403, "Forbidden", "Permission check failed")

    monkeypatch.setattr(access, "get_realm_details", deny)

    # Act and assert
    assert access._get_realm_details_if_allowed(MagicMock(), MOCK_REALM_DATA) == {}


def test_realm_details_other_errors_propagate(monkeypatch):
    """Errors other than 403 on realm details are not swallowed."""

    # Arrange
    def fail(_client, _realms):
        raise ResourceException(500, "Internal Server Error", "boom")

    monkeypatch.setattr(access, "get_realm_details", fail)

    # Act and assert
    with pytest.raises(ResourceException):
        access._get_realm_details_if_allowed(MagicMock(), MOCK_REALM_DATA)
