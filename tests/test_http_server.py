"""Tests for ``smartusbhub_cli.http_server``."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from smartusbhub_cli import http_server
from smartusbhub_cli.commit import get_commit_hash


@pytest.fixture
def client(mock_hub, monkeypatch):
    """Return a TestClient with the hub protocol mocked."""
    from smartusbhub_cli import config as config_module

    original_load_config = config_module.load_config

    def fake_load_config(path=None):
        cfg = original_load_config(path)
        cfg.device = "/dev/fakehub"
        return cfg

    # Patch the module-level config loader used by http_server.
    monkeypatch.setattr(config_module, "load_config", fake_load_config)

    # Reset server state.
    http_server._server_state.protocol = None

    with TestClient(
        http_server.app,
        headers={"X-Commit-Hash": get_commit_hash()},
    ) as test_client:
        yield test_client

    http_server._server_state.protocol = None


def test_root(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert resp.json()["name"] == "smartusbhub-cli-api"


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["success"] is True


def test_power_set_and_get(client):
    resp = client.post("/power", json={"channels": [1, 3], "state": True})
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["data"] == {"set": True}

    resp = client.get("/power?channels=1,2,3,4")
    body = resp.json()
    assert body["data"]["1"] is True
    assert body["data"]["2"] is False


def test_interlock(client):
    resp = client.post("/interlock/2")
    assert resp.status_code == 200
    assert resp.json()["success"] is True


def test_dataline(client):
    resp = client.post("/dataline", json={"channels": [2], "state": True})
    assert resp.status_code == 200
    assert resp.json()["data"] == {"set": True}


def test_voltage(client):
    resp = client.get("/voltage/1")
    body = resp.json()
    assert body["success"] is True
    assert body["data"]["voltage"] == 5.1


def test_current(client):
    resp = client.get("/current/4")
    body = resp.json()
    assert body["success"] is True
    assert body["data"]["current"] == 0.4


def test_default_power(client):
    resp = client.post(
        "/config/default-power",
        json={"channels": [1], "enable": True, "state": True},
    )
    body = resp.json()
    assert body["success"] is True
    assert body["data"] == {"set": True}

    resp = client.get("/config/default-power?channels=1,2")
    body = resp.json()
    assert body["data"]["1"] == {"enabled": True, "value": True}


def test_auto_restore(client):
    resp = client.post("/config/auto-restore", json={"enable": True})
    assert resp.json()["data"]["enabled"] is True
    resp = client.get("/config/auto-restore")
    assert resp.json()["data"]["enabled"] is True


def test_button_control(client):
    resp = client.post("/config/button-control", json={"enable": False})
    assert resp.json()["data"]["enabled"] is False
    resp = client.get("/config/button-control")
    assert resp.json()["data"]["enabled"] is False


def test_operate_mode(client):
    resp = client.post("/config/operate-mode", json={"mode": "interlock"})
    assert resp.json()["data"]["mode"] == "interlock"
    resp = client.get("/config/operate-mode")
    assert resp.json()["data"]["mode"] == "interlock"


def test_device_address(client):
    resp = client.post("/config/device-address", json={"address": 4660})
    assert resp.json()["data"]["address"] == 4660
    resp = client.get("/config/device-address")
    assert resp.json()["data"]["address"] == 4660


def test_factory_reset(client):
    resp = client.post("/factory-reset")
    assert resp.status_code == 200
    assert resp.json()["success"] is True


def test_versions(client):
    assert client.get("/version/firmware").json()["data"]["version"] == "V1.15"
    assert client.get("/version/hardware").json()["data"]["version"] == "V1.3"


def test_device_info(client):
    resp = client.get("/device-info")
    body = resp.json()
    assert body["success"] is True
    assert body["data"]["hardware_version"] == "V1.3"


def test_invalid_channel(client):
    resp = client.get("/power?channels=1,9")
    assert resp.status_code == 400
    assert resp.json()["success"] is False


def test_missing_commit_hash_rejected(client):
    """Requests without X-Commit-Hash must be rejected."""
    from fastapi.testclient import TestClient

    with TestClient(client.app) as bare_client:
        resp = bare_client.get("/health")
        assert resp.status_code == 400
        assert "Commit hash mismatch" in resp.json()["error"]


def test_wrong_commit_hash_rejected(client):
    """Requests with a mismatched X-Commit-Hash must be rejected."""
    from fastapi.testclient import TestClient

    with TestClient(
        client.app,
        headers={"X-Commit-Hash": "mismatch"},
    ) as bad_client:
        resp = bad_client.get("/health")
        assert resp.status_code == 400
        assert "Commit hash mismatch" in resp.json()["error"]
