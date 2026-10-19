"""
Sync the external integrations of a Proxmox cluster: notification targets and
matchers, metric servers, and ACME accounts.

Secrets are never stored: no SMTP password, gotify token, webhook header or
secret value, webhook URL path or body, metric server token, or ACME account
key.

Follows Cartography's Get → Transform → Load pattern.
"""

import logging
from typing import Any
from typing import Callable
from urllib.parse import urlsplit

import neo4j
from proxmoxer.core import ResourceException

from cartography.client.core.tx import load
from cartography.intel.proxmox.mapping import parse_property_string
from cartography.intel.proxmox.util import cluster_scoped_id
from cartography.intel.proxmox.util import proxmox_api_retry
from cartography.models.proxmox.integrations import ProxmoxACMEAccountSchema
from cartography.models.proxmox.integrations import ProxmoxMetricServerSchema
from cartography.models.proxmox.integrations import ProxmoxNotificationMatcherSchema
from cartography.models.proxmox.integrations import ProxmoxNotificationTargetSchema
from cartography.util import timeit

logger = logging.getLogger(__name__)

NOTIFICATION_ENDPOINT_TYPES = ("sendmail", "smtp", "gotify", "webhook")


# ============================================================================
# GET functions - retrieve data from Proxmox API
# ============================================================================


@timeit
@proxmox_api_retry
def get_notification_targets(proxmox_client: Any) -> list[dict[str, Any]]:
    """
    Get every entity that can be used as a notification target.

    :param proxmox_client: Proxmox API client
    :return: List of notification target dicts
    """
    return proxmox_client.cluster.notifications.targets.get()


@timeit
@proxmox_api_retry
def get_notification_endpoints(
    proxmox_client: Any,
    endpoint_type: str,
) -> list[dict[str, Any]]:
    """
    Get the notification endpoints of one type.

    :param proxmox_client: Proxmox API client
    :param endpoint_type: sendmail, smtp, gotify, or webhook
    :return: List of endpoint dicts
    """
    return proxmox_client.cluster.notifications.endpoints(endpoint_type).get()


@timeit
@proxmox_api_retry
def get_notification_matchers(proxmox_client: Any) -> list[dict[str, Any]]:
    """
    Get every notification matcher.

    :param proxmox_client: Proxmox API client
    :return: List of matcher dicts
    """
    return proxmox_client.cluster.notifications.matchers.get()


@timeit
@proxmox_api_retry
def get_metric_servers(proxmox_client: Any) -> list[dict[str, Any]]:
    """
    Get the configured external metric servers.

    :param proxmox_client: Proxmox API client
    :return: List of metric server dicts
    """
    return proxmox_client.cluster.metrics.server.get()


@timeit
@proxmox_api_retry
def get_acme_accounts(proxmox_client: Any) -> list[dict[str, Any]]:
    """
    Get the names of the registered ACME accounts.

    :param proxmox_client: Proxmox API client
    :return: List of dicts with the account name
    """
    return proxmox_client.cluster.acme.account.get()


@timeit
@proxmox_api_retry
def get_acme_account(proxmox_client: Any, name: str) -> dict[str, Any]:
    """
    Get the details of one ACME account. Proxmox allows this only to root@pam.

    :param proxmox_client: Proxmox API client
    :param name: Account name
    :return: Account dict with directory, location, tos, and account
    """
    return proxmox_client.cluster.acme.account(name).get()


# ============================================================================
# TRANSFORM functions - manipulate data for graph ingestion
# ============================================================================


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return list(value)
    return [value]


def _url_origin(url: str | None) -> str | None:
    """
    Keep only the scheme, host, and port of a URL.

    Webhook URLs often carry a token in their path or query, and any URL can
    carry credentials in its user info.

    :param url: URL from the API
    :return: scheme://host[:port], or None when the URL has no host
    """
    if not url:
        return None
    parts = urlsplit(str(url))
    host = parts.hostname
    if not parts.scheme or not host:
        return None
    if ":" in host:
        host = f"[{host}]"
    try:
        port = parts.port
    except ValueError:
        port = None
    return f"{parts.scheme}://{host}" + (f":{port}" if port else "")


def _property_names(entries: Any) -> list[str]:
    """
    Return the names of webhook headers or secrets, dropping their values.

    :param entries: Property strings in the form name=<name>,value=<base64>
    :return: Sorted list of names
    """
    names = {
        parse_property_string(entry, "name").get("name") for entry in _as_list(entries)
    }
    return sorted(n for n in names if n)


def transform_notification_targets(
    targets: list[dict[str, Any]],
    endpoints_by_type: dict[str, list[dict[str, Any]]],
    cluster_id: str,
) -> list[dict[str, Any]]:
    """
    Merge notification targets with their endpoint details.

    :param targets: Raw data of /cluster/notifications/targets
    :param endpoints_by_type: Raw endpoint data keyed by endpoint type
    :param cluster_id: Parent cluster ID
    :return: List of transformed target dicts, without secret values
    """
    merged: dict[str, dict[str, Any]] = {t["name"]: dict(t) for t in targets}
    for endpoint_type, endpoints in endpoints_by_type.items():
        for endpoint in endpoints:
            record = merged.setdefault(endpoint["name"], {})
            record.update(endpoint)
            record["type"] = endpoint_type

    transformed = []
    for name, record in merged.items():
        target_type = record.get("type")
        server: str | None
        if target_type == "smtp":
            server = record.get("server")
        elif target_type == "gotify":
            server = _url_origin(record.get("server"))
        elif target_type == "webhook":
            server = _url_origin(record.get("url"))
        else:
            server = None
        mailto_user = _as_list(record.get("mailto-user"))
        transformed.append(
            {
                "id": cluster_scoped_id(cluster_id, name),
                "name": name,
                "cluster_id": cluster_id,
                "type": target_type,
                "comment": record.get("comment"),
                "disable": record.get("disable"),
                "origin": record.get("origin"),
                "author": record.get("author"),
                "from_address": record.get("from-address"),
                "mailto": _as_list(record.get("mailto")),
                "mailto_user": mailto_user,
                "mailto_user_ids": [
                    cluster_scoped_id(cluster_id, u) for u in mailto_user
                ],
                "mode": record.get("mode"),
                "server": server,
                "port": record.get("port"),
                "username": record.get("username"),
                "method": record.get("method"),
                "header_names": _property_names(record.get("header")),
                "secret_names": _property_names(record.get("secret")),
            },
        )
    return transformed


def transform_notification_matchers(
    matchers: list[dict[str, Any]],
    cluster_id: str,
) -> list[dict[str, Any]]:
    """
    Transform notification matchers into standard format.

    :param matchers: Raw data of /cluster/notifications/matchers
    :param cluster_id: Parent cluster ID
    :return: List of transformed matcher dicts
    """
    transformed = []
    for matcher in matchers:
        name = matcher["name"]
        targets = _as_list(matcher.get("target"))
        transformed.append(
            {
                "id": cluster_scoped_id(cluster_id, name),
                "name": name,
                "cluster_id": cluster_id,
                "comment": matcher.get("comment"),
                "disable": matcher.get("disable"),
                "origin": matcher.get("origin"),
                "mode": matcher.get("mode"),
                "invert_match": matcher.get("invert-match"),
                "match_calendar": _as_list(matcher.get("match-calendar")),
                "match_field": _as_list(matcher.get("match-field")),
                "match_severity": _as_list(matcher.get("match-severity")),
                "targets": targets,
                "target_ids": [cluster_scoped_id(cluster_id, t) for t in targets],
            },
        )
    return transformed


def transform_metric_servers(
    servers: list[dict[str, Any]],
    cluster_id: str,
) -> list[dict[str, Any]]:
    """
    Transform metric servers into standard format, keeping documented fields only.

    :param servers: Raw data of /cluster/metrics/server
    :param cluster_id: Parent cluster ID
    :return: List of transformed metric server dicts
    """
    return [
        {
            "id": cluster_scoped_id(cluster_id, server["id"]),
            "server_id": server["id"],
            "cluster_id": cluster_id,
            "type": server.get("type"),
            "server": server.get("server"),
            "port": server.get("port"),
            "disable": server.get("disable"),
        }
        for server in servers
    ]


def transform_acme_accounts(
    accounts: list[dict[str, Any]],
    details_by_name: dict[str, dict[str, Any]],
    cluster_id: str,
) -> list[dict[str, Any]]:
    """
    Transform ACME accounts into standard format, without the account key.

    :param accounts: Raw data of /cluster/acme/account
    :param details_by_name: Raw data of /cluster/acme/account/{name}, when readable
    :param cluster_id: Parent cluster ID
    :return: List of transformed ACME account dicts
    """
    transformed = []
    for account in accounts:
        name = account["name"]
        details = details_by_name.get(name, {})
        acme_account = details.get("account") or {}
        transformed.append(
            {
                "id": cluster_scoped_id(cluster_id, name),
                "name": name,
                "cluster_id": cluster_id,
                "directory": details.get("directory"),
                "location": details.get("location"),
                "tos": details.get("tos"),
                "contact": _as_list(acme_account.get("contact")),
                "status": acme_account.get("status"),
            },
        )
    return transformed


# ============================================================================
# LOAD functions - ingest data to Neo4j using modern data model
# ============================================================================


def _load(
    neo4j_session: neo4j.Session,
    schema: Any,
    data: list[dict[str, Any]],
    cluster_id: str,
    update_tag: int,
) -> None:
    if data:
        load(
            neo4j_session,
            schema,
            data,
            lastupdated=update_tag,
            CLUSTER_ID=cluster_id,
        )


# ============================================================================
# SYNC functions - orchestrate Get → Transform → Load
# ============================================================================


def _is_forbidden(exc: ResourceException) -> bool:
    return exc.status_code == 403


def _get_unless_forbidden(
    getter: Callable[..., list[dict[str, Any]]],
    what: str,
    *args: Any,
) -> list[dict[str, Any]] | None:
    """
    Call a getter and return None when the token lacks the privilege for it.

    :param getter: get_* function to call
    :param what: Description of the data, for the log message
    :return: The getter result, or None on HTTP 403
    """
    try:
        return getter(*args)
    except ResourceException as e:
        if not _is_forbidden(e):
            raise
        logger.info("Not allowed to read Proxmox %s, skipping: %s", what, e)
        return None


def sync_notifications(
    neo4j_session: neo4j.Session,
    proxmox_client: Any,
    cluster_id: str,
    update_tag: int,
) -> None:
    """
    Sync notification targets and matchers.

    Every notification endpoint needs Mapping.Audit (or Mapping.Modify, or
    Mapping.Use for targets and matchers) on /mapping/notifications. A token
    without it gets 403; that part is skipped and logged.
    """
    targets = _get_unless_forbidden(
        get_notification_targets,
        "notification targets",
        proxmox_client,
    )
    matchers = _get_unless_forbidden(
        get_notification_matchers,
        "notification matchers",
        proxmox_client,
    )
    endpoints_by_type: dict[str, list[dict[str, Any]]] = {}
    if targets is not None:
        for endpoint_type in NOTIFICATION_ENDPOINT_TYPES:
            endpoints = _get_unless_forbidden(
                get_notification_endpoints,
                f"{endpoint_type} notification endpoints",
                proxmox_client,
                endpoint_type,
            )
            if endpoints is not None:
                endpoints_by_type[endpoint_type] = endpoints

    transformed_targets = transform_notification_targets(
        targets or [],
        endpoints_by_type,
        cluster_id,
    )
    transformed_matchers = transform_notification_matchers(
        matchers or [],
        cluster_id,
    )
    _load(
        neo4j_session,
        ProxmoxNotificationTargetSchema(),
        transformed_targets,
        cluster_id,
        update_tag,
    )
    _load(
        neo4j_session,
        ProxmoxNotificationMatcherSchema(),
        transformed_matchers,
        cluster_id,
        update_tag,
    )
    logger.info(
        "Synced %d Proxmox notification targets and %d matchers",
        len(transformed_targets),
        len(transformed_matchers),
    )


def sync_metric_servers(
    neo4j_session: neo4j.Session,
    proxmox_client: Any,
    cluster_id: str,
    update_tag: int,
) -> None:
    """Sync external metric servers. Needs Sys.Audit on /."""
    servers = transform_metric_servers(get_metric_servers(proxmox_client), cluster_id)
    _load(neo4j_session, ProxmoxMetricServerSchema(), servers, cluster_id, update_tag)
    logger.info("Synced %d Proxmox metric servers", len(servers))


def sync_acme_accounts(
    neo4j_session: neo4j.Session,
    proxmox_client: Any,
    cluster_id: str,
    update_tag: int,
) -> None:
    """
    Sync ACME accounts.

    Any user can list the account names, but only root@pam can read the
    account details. For other users the accounts are synced by name only.
    """
    accounts = get_acme_accounts(proxmox_client)
    details_by_name: dict[str, dict[str, Any]] = {}
    for account in accounts:
        try:
            details_by_name[account["name"]] = get_acme_account(
                proxmox_client,
                account["name"],
            )
        except ResourceException as e:
            if not _is_forbidden(e):
                raise
            logger.info(
                "Not allowed to read Proxmox ACME account details (root@pam only), "
                "syncing account names only: %s",
                e,
            )
            break

    transformed = transform_acme_accounts(accounts, details_by_name, cluster_id)
    _load(
        neo4j_session,
        ProxmoxACMEAccountSchema(),
        transformed,
        cluster_id,
        update_tag,
    )
    logger.info("Synced %d Proxmox ACME accounts", len(transformed))


@timeit
def sync(
    neo4j_session: neo4j.Session,
    proxmox_client: Any,
    cluster_id: str,
    update_tag: int,
    common_job_parameters: dict[str, Any],
) -> None:
    """
    Sync notification targets and matchers, metric servers, and ACME accounts.

    :param neo4j_session: Neo4j session
    :param proxmox_client: Proxmox API client
    :param cluster_id: Parent cluster ID
    :param update_tag: Sync timestamp
    :param common_job_parameters: Common parameters
    """
    logger.info("Syncing Proxmox external integrations")
    sync_notifications(neo4j_session, proxmox_client, cluster_id, update_tag)
    sync_metric_servers(neo4j_session, proxmox_client, cluster_id, update_tag)
    sync_acme_accounts(neo4j_session, proxmox_client, cluster_id, update_tag)
