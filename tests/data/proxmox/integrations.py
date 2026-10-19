"""
Mock data for Proxmox notification, metric server, and ACME account tests.
"""

MOCK_NOTIFICATION_TARGETS = [
    {
        "name": "mail-to-root",
        "type": "sendmail",
        "origin": "builtin",
        "comment": "Send mails to root@pam's email address",
    },
    {"name": "ops-smtp", "type": "smtp", "origin": "user-created"},
    {"name": "ops-gotify", "type": "gotify", "origin": "user-created", "disable": 1},
    {"name": "chat-webhook", "type": "webhook", "origin": "user-created"},
]

MOCK_NOTIFICATION_ENDPOINTS = {
    "sendmail": [
        {
            "name": "mail-to-root",
            "mailto-user": ["root@pam"],
            "origin": "builtin",
            "comment": "Send mails to root@pam's email address",
        },
    ],
    "smtp": [
        {
            "name": "ops-smtp",
            "server": "smtp.example.com",
            "port": 587,
            "mode": "starttls",
            "username": "pve-notify",
            "password": "smtp-password-must-not-be-stored",
            "from-address": "pve@example.com",
            "author": "Proxmox VE",
            "mailto": ["ops@example.com"],
            "mailto-user": ["admin@pve"],
            "origin": "user-created",
        },
    ],
    "gotify": [
        {
            "name": "ops-gotify",
            "server": "https://gotify.example.com:8443/gotify",
            "token": "gotify-token-must-not-be-stored",
            "origin": "user-created",
            "disable": 1,
        },
    ],
    "webhook": [
        {
            "name": "chat-webhook",
            "url": "https://hooks.example.com/services/T000/B000/webhook-token-must-not-be-stored",
            "method": "post",
            "header": [
                "name=Authorization,value=QmVhcmVyIGhlYWRlci12YWx1ZS1zZWNyZXQ=",
                "name=Content-Type,value=YXBwbGljYXRpb24vanNvbg==",
            ],
            "secret": ["name=api-key,value=c2VjcmV0LXZhbHVl"],
            "body": "eyJ0ZXh0IjogInt7IG1lc3NhZ2UgfX0ifQ==",
            "origin": "user-created",
        },
    ],
}

MOCK_NOTIFICATION_MATCHERS = [
    {
        "name": "default-matcher",
        "target": ["mail-to-root"],
        "origin": "builtin",
        "comment": "Route all notifications to mail-to-root",
    },
    {
        "name": "critical-ops",
        "target": ["ops-smtp", "ops-gotify", "chat-webhook"],
        "match-severity": ["error", "warning"],
        "match-field": ["exact:type=vzdump"],
        "mode": "all",
        "origin": "user-created",
    },
]

MOCK_METRIC_SERVERS = [
    {
        "id": "influx",
        "type": "influxdb",
        "server": "influx.example.com",
        "port": 8086,
        "disable": 0,
        "token": "influx-token-must-not-be-stored",
    },
    {"id": "graphite", "type": "graphite", "server": "10.0.0.5", "port": 2003},
]

MOCK_ACME_ACCOUNTS = [{"name": "default"}, {"name": "staging"}]

MOCK_ACME_ACCOUNT_DETAILS = {
    "default": {
        "directory": "https://acme-v02.api.letsencrypt.org/directory",
        "location": "https://acme-v02.api.letsencrypt.org/acme/acct/123456",
        "tos": "https://letsencrypt.org/documents/LE-SA-v1.4-April-3-2024.pdf",
        "account": {
            "status": "valid",
            "contact": ["mailto:admin@example.com"],
            "key": {"kty": "RSA", "n": "key-material-must-not-be-stored", "e": "AQAB"},
        },
    },
    "staging": {
        "directory": "https://acme-staging-v02.api.letsencrypt.org/directory",
        "location": "https://acme-staging-v02.api.letsencrypt.org/acme/acct/42",
        "account": {"status": "deactivated", "contact": []},
    },
}
