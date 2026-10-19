"""
Tests for the Proxmox notification, metric server, and ACME account module.
"""

from unittest.mock import MagicMock
from unittest.mock import patch

import pytest
from proxmoxer.core import ResourceException

import cartography.intel.proxmox.integrations as integrations
from cartography.intel.proxmox.integrations import transform_acme_accounts
from cartography.intel.proxmox.integrations import transform_metric_servers
from cartography.intel.proxmox.integrations import transform_notification_matchers
from cartography.intel.proxmox.integrations import transform_notification_targets
from tests.data.proxmox.integrations import MOCK_ACME_ACCOUNT_DETAILS
from tests.data.proxmox.integrations import MOCK_ACME_ACCOUNTS
from tests.data.proxmox.integrations import MOCK_METRIC_SERVERS
from tests.data.proxmox.integrations import MOCK_NOTIFICATION_ENDPOINTS
from tests.data.proxmox.integrations import MOCK_NOTIFICATION_MATCHERS
from tests.data.proxmox.integrations import MOCK_NOTIFICATION_TARGETS


def _forbidden() -> ResourceException:
    return ResourceException(403, "Forbidden", "Permission check failed")


def test_transform_notification_targets_merges_endpoints_without_secrets():
    result = {
        t["name"]: t
        for t in transform_notification_targets(
            MOCK_NOTIFICATION_TARGETS,
            MOCK_NOTIFICATION_ENDPOINTS,
            "c",
        )
    }

    assert set(result) == {"mail-to-root", "ops-smtp", "ops-gotify", "chat-webhook"}
    assert result["mail-to-root"]["mailto_user_ids"] == ["c/root@pam"]
    smtp = result["ops-smtp"]
    assert smtp["type"] == "smtp"
    assert smtp["server"] == "smtp.example.com"
    assert smtp["port"] == 587
    assert smtp["username"] == "pve-notify"
    assert smtp["from_address"] == "pve@example.com"
    assert result["ops-gotify"]["server"] == "https://gotify.example.com:8443"
    webhook = result["chat-webhook"]
    assert webhook["server"] == "https://hooks.example.com"
    assert webhook["method"] == "post"
    assert webhook["header_names"] == ["Authorization", "Content-Type"]
    assert webhook["secret_names"] == ["api-key"]

    # No secret value or token-bearing URL part survives the transform.
    flattened = repr(list(result.values()))
    for secret in (
        "must-not-be-stored",
        "QmVhcmVy",
        "c2VjcmV0",
        "/services/",
        "eyJ0ZXh0",
    ):
        assert secret not in flattened


def test_transform_notification_targets_keeps_targets_without_details():
    """A target whose endpoint list was not readable keeps its target fields."""
    result = transform_notification_targets(MOCK_NOTIFICATION_TARGETS[:1], {}, "c")

    assert result[0]["type"] == "sendmail"
    assert result[0]["origin"] == "builtin"
    assert result[0]["mailto_user_ids"] == []


def test_url_origin_drops_credentials_path_and_query():
    assert (
        integrations._url_origin("https://user:pw@hook.example.com/x?token=1")
        == "https://hook.example.com"
    )
    assert (
        integrations._url_origin("http://[fd00::1]:8080/a") == "http://[fd00::1]:8080"
    )
    assert integrations._url_origin("not a url") is None
    assert integrations._url_origin(None) is None


def test_transform_notification_matchers_builds_target_ids():
    result = {
        m["name"]: m
        for m in transform_notification_matchers(MOCK_NOTIFICATION_MATCHERS, "c")
    }

    assert result["critical-ops"]["target_ids"] == [
        "c/ops-smtp",
        "c/ops-gotify",
        "c/chat-webhook",
    ]
    assert result["critical-ops"]["match_severity"] == ["error", "warning"]
    assert result["default-matcher"]["match_field"] == []


def test_transform_metric_servers_keeps_documented_fields_only():
    result = transform_metric_servers(MOCK_METRIC_SERVERS, "c")

    assert result[0] == {
        "id": "c/influx",
        "server_id": "influx",
        "cluster_id": "c",
        "type": "influxdb",
        "server": "influx.example.com",
        "port": 8086,
        "disable": 0,
    }


def test_transform_acme_accounts_without_key():
    result = transform_acme_accounts(
        MOCK_ACME_ACCOUNTS,
        {"default": MOCK_ACME_ACCOUNT_DETAILS["default"]},
        "c",
    )

    assert result[0]["contact"] == ["mailto:admin@example.com"]
    assert result[0]["status"] == "valid"
    assert "must-not-be-stored" not in repr(result)
    assert result[1] == {
        "id": "c/staging",
        "name": "staging",
        "cluster_id": "c",
        "directory": None,
        "location": None,
        "tos": None,
        "contact": [],
        "status": None,
    }


@patch.object(integrations, "_load")
@patch.object(integrations, "get_acme_account", side_effect=_forbidden())
@patch.object(integrations, "get_acme_accounts", return_value=MOCK_ACME_ACCOUNTS)
def test_sync_acme_accounts_keeps_names_when_details_are_forbidden(
    mock_accounts,
    mock_account,
    mock_load,
):
    integrations.sync_acme_accounts(MagicMock(), MagicMock(), "c", 1)

    # The first 403 stops further detail calls.
    assert mock_account.call_count == 1
    loaded = mock_load.call_args.args[2]
    assert [a["name"] for a in loaded] == ["default", "staging"]
    assert all(a["directory"] is None for a in loaded)


@patch.object(integrations, "get_acme_account")
@patch.object(integrations, "get_acme_accounts", return_value=MOCK_ACME_ACCOUNTS)
def test_sync_acme_accounts_raises_unrelated_errors(mock_accounts, mock_account):
    mock_account.side_effect = ResourceException(500, "Internal", "boom")

    with pytest.raises(ResourceException):
        integrations.sync_acme_accounts(MagicMock(), MagicMock(), "c", 1)


@patch.object(integrations, "_load")
@patch.object(integrations, "get_notification_endpoints", side_effect=_forbidden())
@patch.object(integrations, "get_notification_matchers", side_effect=_forbidden())
@patch.object(integrations, "get_notification_targets", side_effect=_forbidden())
def test_sync_notifications_skips_forbidden_area(
    mock_targets,
    mock_matchers,
    mock_endpoints,
    mock_load,
):
    integrations.sync_notifications(MagicMock(), MagicMock(), "c", 1)

    mock_endpoints.assert_not_called()
    assert all(call.args[2] == [] for call in mock_load.call_args_list)


@patch.object(integrations, "_load")
@patch.object(integrations, "get_notification_endpoints", side_effect=_forbidden())
@patch.object(
    integrations,
    "get_notification_matchers",
    return_value=MOCK_NOTIFICATION_MATCHERS,
)
@patch.object(
    integrations,
    "get_notification_targets",
    return_value=MOCK_NOTIFICATION_TARGETS,
)
def test_sync_notifications_keeps_targets_when_endpoints_are_forbidden(
    mock_targets,
    mock_matchers,
    mock_endpoints,
    mock_load,
):
    integrations.sync_notifications(MagicMock(), MagicMock(), "c", 1)

    assert mock_endpoints.call_count == 4
    targets = mock_load.call_args_list[0].args[2]
    assert {t["name"] for t in targets} == {
        "mail-to-root",
        "ops-smtp",
        "ops-gotify",
        "chat-webhook",
    }
    assert all(t["server"] is None for t in targets)


@patch.object(integrations, "get_notification_targets")
def test_sync_notifications_raises_unrelated_errors(mock_targets):
    mock_targets.side_effect = ResourceException(500, "Internal", "boom")

    with pytest.raises(ResourceException):
        integrations.sync_notifications(MagicMock(), MagicMock(), "c", 1)
