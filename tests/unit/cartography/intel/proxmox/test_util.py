from unittest.mock import MagicMock

import pytest
import requests
from proxmoxer.core import ResourceException

from cartography.intel.proxmox.compute import get_guest_agent_info
from cartography.intel.proxmox.util import is_retryable_proxmox_error
from cartography.intel.proxmox.util import PROXMOX_API_MAX_TRIES
from cartography.intel.proxmox.util import proxmox_api_retry


def _resource_exception(status_code: int) -> ResourceException:
    return ResourceException(status_code, "error", "")


@pytest.mark.parametrize(
    "exc",
    [
        _resource_exception(429),
        _resource_exception(502),
        _resource_exception(503),
        _resource_exception(504),
        requests.exceptions.ConnectionError(),
        requests.exceptions.ReadTimeout(),
        requests.exceptions.ConnectTimeout(),
    ],
)
def test_transient_errors_are_retryable(exc):
    assert is_retryable_proxmox_error(exc)


@pytest.mark.parametrize(
    "exc",
    [
        _resource_exception(400),
        _resource_exception(401),
        _resource_exception(403),
        _resource_exception(404),
        _resource_exception(500),
        requests.exceptions.SSLError(),
        ValueError(),
    ],
)
def test_permanent_errors_are_not_retryable(exc):
    assert not is_retryable_proxmox_error(exc)


def test_retry_recovers_from_transient_error(mocker):
    mocker.patch("time.sleep")
    call = MagicMock(side_effect=[_resource_exception(503), ["ok"]])

    assert proxmox_api_retry(call)() == ["ok"]
    assert call.call_count == 2


def test_retry_gives_up_after_max_tries(mocker):
    mocker.patch("time.sleep")
    call = MagicMock(side_effect=requests.exceptions.ReadTimeout())

    with pytest.raises(requests.exceptions.ReadTimeout):
        proxmox_api_retry(call)()
    assert call.call_count == PROXMOX_API_MAX_TRIES


def test_retry_does_not_repeat_permanent_error(mocker):
    mocker.patch("time.sleep")
    call = MagicMock(side_effect=_resource_exception(403))

    with pytest.raises(ResourceException):
        proxmox_api_retry(call)()
    assert call.call_count == 1


def test_get_guest_agent_info_returns_empty_on_agent_timeout():
    client = MagicMock()
    agent = client.nodes.return_value.qemu.return_value.agent
    agent.return_value.get.side_effect = [
        {"result": {"name": "Debian"}},
        requests.exceptions.ReadTimeout(),
    ]

    assert get_guest_agent_info(client, "node1", 100) == {}
