"""Tests for ``smartusbhub_cli.client.HTTPClient``."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from smartusbhub_cli import http_server
from smartusbhub_cli.client import HTTPClient
from smartusbhub_cli.commit import get_commit_hash
from smartusbhub_cli.http_server import _server_state
from smartusbhub_cli.protocol import HubProtocol


@pytest.fixture
def http_client(mock_hub, monkeypatch):
    """Return an HTTPClient pointed at a mocked HTTP server."""
    from smartusbhub_cli import config as config_module

    original_load_config = config_module.load_config

    def fake_load_config(path=None):
        cfg = original_load_config(path)
        cfg.device = "/dev/fakehub"
        return cfg

    monkeypatch.setattr(config_module, "load_config", fake_load_config)

    _server_state.protocol = HubProtocol("/dev/fakehub")

    with TestClient(
        http_server.app,
        headers={"X-Commit-Hash": get_commit_hash()},
    ) as test_client:
        # HTTPClient uses httpx, but TestClient is ASGI-compatible.  We
        # monkeypatch the internal transport so HTTPClient talks to the app
        # without starting a real server.
        client = HTTPClient("http://testserver")
        client._client = test_client
        yield client

    _server_state.protocol = None


def test_client_set_power(http_client):
    assert http_client.set_power([1, 3], True) is True


def test_client_get_power(http_client):
    http_client.set_power([2], True)
    assert http_client.get_power([2]) == {2: True}


def test_client_set_interlock(http_client):
    assert http_client.set_interlock(1) is True


def test_client_set_dataline(http_client):
    assert http_client.set_dataline([4], True) is True


def test_client_get_dataline(http_client):
    http_client.set_dataline([1], True)
    assert http_client.get_dataline([1]) == {1: True}


def test_client_voltage(http_client):
    assert http_client.get_voltage(1) == 5.1


def test_client_current(http_client):
    assert http_client.get_current(4) == 0.4


def test_client_default_power(http_client):
    assert http_client.set_default_power([1], enable=True, state=True) is True
    assert http_client.get_default_power([1]) == {1: {"enabled": True, "value": True}}


def test_client_default_dataline(http_client):
    assert http_client.set_default_dataline([2], enable=True, state=False) is True
    assert http_client.get_default_dataline([2]) == {2: {"enabled": True, "value": False}}


def test_client_auto_restore(http_client):
    assert http_client.set_auto_restore(True) is True
    assert http_client.get_auto_restore() is True


def test_client_button_control(http_client):
    assert http_client.set_button_control(False) is False
    assert http_client.get_button_control() is False


def test_client_operate_mode(http_client):
    assert http_client.set_operate_mode("interlock") == "interlock"
    assert http_client.get_operate_mode() == "interlock"


def test_client_device_address(http_client):
    assert http_client.set_device_address(0x1234) == 0x1234
    assert http_client.get_device_address() == 0x1234


def test_client_factory_reset(http_client):
    assert http_client.factory_reset() is True


def test_client_firmware_version(http_client):
    assert http_client.get_firmware_version() == "V1.15"


def test_client_hardware_version(http_client):
    assert http_client.get_hardware_version() == "V1.3"


def test_client_device_info(http_client):
    info = http_client.get_device_info()
    assert info["hardware_version"] == "V1.3"
