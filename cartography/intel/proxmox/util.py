"""
Helpers shared by the Proxmox sync modules.
"""

import logging
from typing import Any
from typing import Callable
from typing import cast
from typing import TypeVar

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
