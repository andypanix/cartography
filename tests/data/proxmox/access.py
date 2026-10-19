"""
Mock data for Proxmox access control tests.
"""

MOCK_USER_DATA = [
    {
        "userid": "root@pam",
        "enable": 1,
        "expire": 0,
        "firstname": "Root",
        "lastname": "User",
        "email": "root@example.com",
        "comment": "Root user account",
        "groups": "admins,operators",
        "realm-type": "pam",
        "tokens": [
            {
                "tokenid": "monitoring",
                "comment": "Monitoring token",
                "expire": 0,
                "privsep": 1,
            },
            {"tokenid": "automation", "expire": 1893456000, "privsep": 0},
        ],
    },
    {
        "userid": "admin@pve",
        "enable": 1,
        "expire": 0,
        "email": "admin@example.com",
        "comment": "Administrator account",
        "groups": "admins",
    },
    {
        "userid": "readonly@pam",
        "enable": 1,
        "expire": 1735689600,  # Future date
        "email": "readonly@example.com",
        "groups": "auditors",
        "totp-locked": 1,
        "tfa-locked-until": 1767225600,
    },
    {
        "userid": "disabled@pam",
        "enable": 0,
        "email": "disabled@example.com",
        "groups": "",
    },
]

MOCK_GROUP_DATA = [
    {
        "groupid": "admins",
        "comment": "Administrator group",
    },
    {
        "groupid": "operators",
        "comment": "Operator group",
    },
    {
        "groupid": "auditors",
        "comment": "Read-only auditor group",
    },
]

MOCK_ROLE_DATA = [
    {
        "roleid": "Administrator",
        "privs": "VM.Allocate,VM.Config,Sys.Modify,Datastore.Allocate",
        "special": 1,
    },
    {
        "roleid": "PVEAuditor",
        "privs": "VM.Audit,Sys.Audit,Datastore.Audit",
        "special": 1,
    },
    {
        "roleid": "CustomRole",
        "privs": "VM.Config,VM.PowerMgmt",
        "special": 0,
    },
]

MOCK_ACL_DATA = [
    {
        "path": "/",
        "roleid": "Administrator",
        "ugid": "root@pam",
        "propagate": 1,
    },
    {
        "path": "/",
        "roleid": "Administrator",
        "ugid": "admins",
        "propagate": 1,
    },
    {
        "path": "/vms",
        "roleid": "PVEAuditor",
        "ugid": "auditors",
        "propagate": 1,
    },
    {
        "path": "/vms/100",
        "roleid": "CustomRole",
        "ugid": "readonly@pam",
        "propagate": 0,
    },
    {
        "path": "/storage/local-lvm",
        "roleid": "PVEAuditor",
        "ugid": "auditors",
        "propagate": 1,
    },
    {
        # Grants the token, not root@pam: it must not widen root@pam's permissions.
        "path": "/storage/local-lvm",
        "roleid": "PVEAuditor",
        "ugid": "root@pam!monitoring",
        "type": "token",
        "propagate": 1,
    },
    {
        "path": "/pool/production",
        "roleid": "CustomRole",
        "ugid": "admin@pve",
        "propagate": 1,
    },
    {
        "path": "/nodes/node1",
        "roleid": "PVEAuditor",
        "ugid": "operators",
        "propagate": 0,
    },
]

MOCK_GROUP_MEMBERS_DATA = {
    "admins": ["root@pam", "admin@pve"],
    "operators": ["root@pam"],
    "auditors": ["readonly@pam"],
}

MOCK_REALM_DATA = [
    {"realm": "pam", "type": "pam", "comment": "Linux PAM standard authentication"},
    {
        "realm": "pve",
        "type": "pve",
        "comment": "Proxmox VE authentication server",
        "default": 1,
    },
    {"realm": "corp", "type": "ldap", "comment": "Corporate LDAP", "tfa": "oath"},
    {"realm": "sso", "type": "openid", "comment": "Single sign-on"},
]

# Raw realm configurations, as /access/domains/{realm} returns them. They hold
# secrets the sync must never store.
MOCK_REALM_DETAILS = {
    "corp": {
        "type": "ldap",
        "server1": "ldap1.example.com",
        "server2": "ldap2.example.com",
        "port": 636,
        "mode": "ldaps",
        "verify": 1,
        "base_dn": "ou=people,dc=example,dc=com",
        "bind_dn": "cn=proxmox,dc=example,dc=com",
        "user_attr": "uid",
        "password": "ldap-bind-secret",
        "digest": "abc123",
    },
    "sso": {
        "type": "openid",
        "issuer-url": "https://sso.example.com/realms/corp",
        "client-id": "proxmox",
        "client-key": "openid-client-secret",
        "autocreate": 1,
        "digest": "abc123",
    },
}

MOCK_REALM_SYNC_JOB_DATA = [
    {
        "id": "corp-nightly",
        "realm": "corp",
        "enabled": 1,
        "schedule": "daily",
        "scope": "both",
        "remove-vanished": "acl;entry",
        "comment": "Nightly LDAP sync",
        "last-run": 1767139200,
        "next-run": 1767225600,
    },
]

MOCK_TFA_DATA = [
    {
        "userid": "root@pam",
        "entries": [
            {
                "id": "totp-1",
                "type": "totp",
                "description": "Phone",
                "enable": 1,
                "created": 1700000000,
            },
            {
                "id": "recovery",
                "type": "recovery",
                "description": "",
                "created": 1700000100,
            },
            {
                "id": "webauthn-1",
                "type": "webauthn",
                "description": "Old key",
                "enable": 0,
                "created": 1690000000,
            },
        ],
    },
    {
        "userid": "readonly@pam",
        "entries": [],
        "totp-locked": 1,
    },
]
