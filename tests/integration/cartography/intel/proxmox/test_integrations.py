"""
Integration tests for Proxmox notification, metric server, and ACME account sync.
"""

from typing import Any
from unittest.mock import MagicMock
from unittest.mock import patch

import cartography.intel.proxmox.integrations
from tests.data.proxmox.integrations import MOCK_ACME_ACCOUNT_DETAILS
from tests.data.proxmox.integrations import MOCK_ACME_ACCOUNTS
from tests.data.proxmox.integrations import MOCK_METRIC_SERVERS
from tests.data.proxmox.integrations import MOCK_NOTIFICATION_ENDPOINTS
from tests.data.proxmox.integrations import MOCK_NOTIFICATION_MATCHERS
from tests.data.proxmox.integrations import MOCK_NOTIFICATION_TARGETS
from tests.integration.util import check_nodes
from tests.integration.util import check_rels

TEST_UPDATE_TAG = 123456789
TEST_CLUSTER_ID = "test-cluster"

integrations = cartography.intel.proxmox.integrations


@patch.object(
    integrations,
    "get_acme_account",
    side_effect=lambda _c, name: MOCK_ACME_ACCOUNT_DETAILS[name],
)
@patch.object(integrations, "get_acme_accounts", return_value=MOCK_ACME_ACCOUNTS)
@patch.object(integrations, "get_metric_servers", return_value=MOCK_METRIC_SERVERS)
@patch.object(
    integrations,
    "get_notification_matchers",
    return_value=MOCK_NOTIFICATION_MATCHERS,
)
@patch.object(
    integrations,
    "get_notification_endpoints",
    side_effect=lambda _c, endpoint_type: MOCK_NOTIFICATION_ENDPOINTS[endpoint_type],
)
@patch.object(
    integrations,
    "get_notification_targets",
    return_value=MOCK_NOTIFICATION_TARGETS,
)
def test_sync_integrations(
    mock_targets,
    mock_endpoints,
    mock_matchers,
    mock_metrics,
    mock_acme_accounts,
    mock_acme_account,
    neo4j_session,
):
    """
    Notification targets, matchers, metric servers, and ACME accounts are
    loaded with their relationships and without any secret value.
    """
    neo4j_session.run("MATCH (n) DETACH DELETE n")
    neo4j_session.run(
        """
        MERGE (c:ProxmoxCluster {id: $cluster_id})
        MERGE (:ProxmoxUser {id: $cluster_id + '/root@pam'})
        MERGE (:ProxmoxUser {id: $cluster_id + '/admin@pve'})
        """,
        cluster_id=TEST_CLUSTER_ID,
    )
    common_job_parameters: dict[str, Any] = {
        "UPDATE_TAG": TEST_UPDATE_TAG,
        "CLUSTER_ID": TEST_CLUSTER_ID,
    }

    # Act
    integrations.sync(
        neo4j_session,
        MagicMock(),
        TEST_CLUSTER_ID,
        TEST_UPDATE_TAG,
        common_job_parameters,
    )

    # Assert - notification targets with their endpoint details
    assert check_nodes(
        neo4j_session,
        "ProxmoxNotificationTarget",
        ["id", "type", "server"],
    ) == {
        ("test-cluster/mail-to-root", "sendmail", None),
        ("test-cluster/ops-smtp", "smtp", "smtp.example.com"),
        ("test-cluster/ops-gotify", "gotify", "https://gotify.example.com:8443"),
        ("test-cluster/chat-webhook", "webhook", "https://hooks.example.com"),
    }
    record = neo4j_session.run(
        """
        MATCH (t:ProxmoxNotificationTarget {id: 'test-cluster/chat-webhook'})
        RETURN t.header_names AS headers, t.secret_names AS secrets
        """,
    ).single()
    assert record["headers"] == ["Authorization", "Content-Type"]
    assert record["secrets"] == ["api-key"]

    # Assert - no secret value is stored on any node
    stored = neo4j_session.run(
        """
        MATCH (n)
        WHERE n:ProxmoxNotificationTarget OR n:ProxmoxNotificationMatcher
           OR n:ProxmoxMetricServer OR n:ProxmoxACMEAccount
        RETURN properties(n) AS props
        """,
    ).data()
    flattened = repr([r["props"] for r in stored])
    for secret in ("must-not-be-stored", "QmVhcmVy", "c2VjcmV0", "/services/"):
        assert secret not in flattened
    for key in ("password", "token", "key", "body", "url"):
        assert all(key not in r["props"] for r in stored), key

    # Assert - mail targets notify the Proxmox users they list
    assert check_rels(
        neo4j_session,
        "ProxmoxNotificationTarget",
        "id",
        "ProxmoxUser",
        "id",
        "NOTIFIES",
        rel_direction_right=True,
    ) == {
        ("test-cluster/mail-to-root", "test-cluster/root@pam"),
        ("test-cluster/ops-smtp", "test-cluster/admin@pve"),
    }

    # Assert - matchers route to their targets
    assert check_rels(
        neo4j_session,
        "ProxmoxNotificationMatcher",
        "id",
        "ProxmoxNotificationTarget",
        "id",
        "ROUTES_TO",
        rel_direction_right=True,
    ) == {
        ("test-cluster/default-matcher", "test-cluster/mail-to-root"),
        ("test-cluster/critical-ops", "test-cluster/ops-smtp"),
        ("test-cluster/critical-ops", "test-cluster/ops-gotify"),
        ("test-cluster/critical-ops", "test-cluster/chat-webhook"),
    }

    # Assert - metric servers and ACME accounts
    assert check_nodes(
        neo4j_session,
        "ProxmoxMetricServer",
        ["id", "type", "server", "port"],
    ) == {
        ("test-cluster/influx", "influxdb", "influx.example.com", 8086),
        ("test-cluster/graphite", "graphite", "10.0.0.5", 2003),
    }
    assert check_nodes(
        neo4j_session,
        "ProxmoxACMEAccount",
        ["id", "status", "directory"],
    ) == {
        (
            "test-cluster/default",
            "valid",
            "https://acme-v02.api.letsencrypt.org/directory",
        ),
        (
            "test-cluster/staging",
            "deactivated",
            "https://acme-staging-v02.api.letsencrypt.org/directory",
        ),
    }

    # Assert - every node is attached to the cluster
    for label, count in (
        ("ProxmoxNotificationTarget", 4),
        ("ProxmoxNotificationMatcher", 2),
        ("ProxmoxMetricServer", 2),
        ("ProxmoxACMEAccount", 2),
    ):
        rels = check_rels(
            neo4j_session,
            "ProxmoxCluster",
            "id",
            label,
            "id",
            "RESOURCE",
            rel_direction_right=True,
        )
        assert len(rels) == count, label
        assert {cluster for cluster, _ in rels} == {TEST_CLUSTER_ID}, label
