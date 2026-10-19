"""
Helpers shared by the Proxmox sync modules.
"""

import functools
import logging
import re
from typing import Any
from typing import Callable
from typing import cast
from typing import TypeVar
from urllib.parse import unquote
from urllib.parse import urlsplit
from urllib.parse import urlunsplit

import backoff
import requests
from proxmoxer.core import ResourceException

logger = logging.getLogger(__name__)

PROXMOX_API_MAX_TRIES = 3
PROXMOX_API_BACKOFF_BASE = 2
PROXMOX_API_BACKOFF_MAX = 30
# 500 is not retried: Proxmox returns it for deterministic failures too, such
# as a stopped guest agent or a missing VM configuration file.
PROXMOX_RETRYABLE_STATUS_CODES = frozenset({429, 502, 503, 504})

# Proxmox resource names (node, storage, user, role, VM ID, ...) are only
# unique inside one cluster. Every non-cluster node ID is prefixed with the
# cluster ID so several clusters can share one graph. The cluster ID is the
# cluster name (letters, digits and dashes) or the API hostname with dots
# replaced by dashes, so it never contains "/" and the first "/" of an ID
# always ends the cluster prefix.
CLUSTER_ID_SEPARATOR = "/"


def cluster_scoped_id(cluster_id: str, natural_id: Any) -> str:
    """
    Build the graph ID of a Proxmox resource that is unique only in its cluster.

    :param cluster_id: ID of the cluster that owns the resource
    :param natural_id: Resource ID inside the cluster, such as pve or local
    :return: ID in the form cluster_id/natural_id
    """
    return f"{cluster_id}{CLUSTER_ID_SEPARATOR}{natural_id}"


def is_retryable_proxmox_error(exc: Exception) -> bool:
    """
    Check if a Proxmox API error is transient and worth retrying.

    :param exc: The exception raised by the Proxmox API client
    :return: True for timeouts, connection errors, and 429/502/503/504 responses
    """
    if isinstance(exc, ResourceException):
        return exc.status_code in PROXMOX_RETRYABLE_STATUS_CODES
    # requests raises SSLError as a ConnectionError, but a TLS validation
    # failure does not go away on retry.
    if isinstance(exc, requests.exceptions.SSLError):
        return False
    return isinstance(
        exc,
        (requests.exceptions.ConnectionError, requests.exceptions.Timeout),
    )


def _proxmox_api_backoff_handler(details: dict[str, Any]) -> None:
    logger.warning(
        "Proxmox API call %s failed on try %s, retrying in %0.1fs: %s",
        getattr(details.get("target"), "__name__", "<unknown>"),
        details.get("tries"),
        details.get("wait") or 0,
        details.get("exception"),
    )


_proxmox_api_backoff = backoff.on_exception(
    backoff.expo,
    (ResourceException, requests.exceptions.RequestException),
    max_tries=PROXMOX_API_MAX_TRIES,
    giveup=lambda e: not is_retryable_proxmox_error(e),
    on_backoff=_proxmox_api_backoff_handler,
    logger=None,
    base=PROXMOX_API_BACKOFF_BASE,
    max_value=PROXMOX_API_BACKOFF_MAX,
)

F = TypeVar("F", bound=Callable[..., Any])


def proxmox_api_retry(func: F) -> F:
    """
    Retry transient Proxmox API failures with exponential backoff.

    Any other error, or a transient one that outlasts the retries, propagates
    to the caller.
    """
    return cast(F, _proxmox_api_backoff(func))


# Proxmox answers 501 for an API path the installed version does not have,
# such as an endpoint added in Proxmox VE 9 called on 8.4.
PROXMOX_UNAVAILABLE_STATUS_CODES = frozenset({404, 501})


def is_unavailable_endpoint(exc: Exception) -> bool:
    """
    Check if a Proxmox API error means the endpoint does not exist on this host.

    :param exc: The exception raised by the Proxmox API client
    :return: True for 404 and 501 responses
    """
    return (
        isinstance(exc, ResourceException)
        and exc.status_code in PROXMOX_UNAVAILABLE_STATUS_CODES
    )


def proxmox_optional_endpoint(default: Callable[[], Any]) -> Callable[[F], F]:
    """
    Return a default value when the endpoint does not exist on this Proxmox host.

    Use it for endpoints that only some supported versions provide. Apply it
    outside proxmox_api_retry so transient errors are still retried first.

    :param default: Factory for the value to return, such as list or dict
    """

    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                return func(*args, **kwargs)
            except ResourceException as e:
                if not is_unavailable_endpoint(e):
                    raise
                logger.info(
                    "Proxmox API endpoint for %s is not available on this host, skipping: %s",
                    func.__name__,
                    e,
                )
                return default()

        return cast(F, wrapper)

    return decorator


# Query parameters of a URI that can carry a credential.
URI_SECRET_QUERY_PARAM = re.compile(
    r"token|key|pass|secret|auth|sig|credential|session",
    re.IGNORECASE,
)
# userinfo in a URI embedded in free text, such as an APT parse error.
URI_USERINFO_IN_TEXT = re.compile(r"(?P<scheme>[A-Za-z][A-Za-z0-9+.-]*://)[^/\s@]+@")


def strip_uri_credentials(uri: Any) -> Any:
    """
    Remove credentials from a URI, such as an APT repository or a proxy URL.

    Drops the userinfo (user:password@) and the query parameters whose name
    suggests a credential, such as token, key, auth or signature.

    :param uri: Repository URI, such as https://user:token@repo.example.com/debian
    :return: URI without credentials; non-string values are returned unchanged
    """
    if not isinstance(uri, str):
        return uri
    try:
        parts = urlsplit(uri)
    except ValueError:
        return URI_USERINFO_IN_TEXT.sub(r"\g<scheme>", uri)
    netloc = parts.netloc.rpartition("@")[2]
    # Split by hand to keep the encoding of the parameters that stay.
    query = "&".join(
        param
        for param in parts.query.split("&")
        if param and not URI_SECRET_QUERY_PARAM.search(unquote(param.split("=")[0]))
    )
    return urlunsplit((parts.scheme, netloc, parts.path, query, parts.fragment))
