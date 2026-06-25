"""Tests for ``smartusbhub_cli.cli``."""

from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from smartusbhub_cli.cli import app

runner = CliRunner()


@pytest.fixture(autouse=True)
def _mock_hub(mock_hub, monkeypatch):
    """Ensure the CLI uses the fake hub for local commands."""
    from smartusbhub_cli import config as config_module

    original_load_config = config_module.load_config

    def fake_load_config(path=None):
        cfg = original_load_config(path)
        cfg.port = "/dev/fakehub"
        return cfg

    monkeypatch.setattr(config_module, "load_config", fake_load_config)


def test_help():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "CLI for SmartUSBHub" in result.output


def test_power_on():
    result = runner.invoke(app, ["power", "on", "--ch", "1", "--ch", "3"])
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)["data"]
    assert data["1"] is True
    assert data["3"] is True


def test_power_off_all():
    result = runner.invoke(app, ["power", "off", "--all"])
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)["data"]
    assert all(v is False for v in data.values())


def test_power_status():
    runner.invoke(app, ["power", "on", "--ch", "2"])
    result = runner.invoke(app, ["power", "status", "--ch", "2"])
    assert result.exit_code == 0
    assert json.loads(result.output)["data"]["2"] is True


def test_interlock():
    result = runner.invoke(app, ["interlock", "1"])
    assert result.exit_code == 0
    assert json.loads(result.output)["data"]["interlock"] is True


def test_dataline_on():
    result = runner.invoke(app, ["dataline", "on", "--ch", "4"])
    assert result.exit_code == 0
    assert json.loads(result.output)["data"]["4"] is True


def test_voltage():
    result = runner.invoke(app, ["voltage", "1"])
    assert result.exit_code == 0
    data = json.loads(result.output)["data"]
    assert data["channel"] == 1
    assert data["voltage"] == 5.1


def test_current():
    result = runner.invoke(app, ["current", "4"])
    assert result.exit_code == 0
    data = json.loads(result.output)["data"]
    assert data["current"] == 0.4


def test_config_default_power():
    result = runner.invoke(
        app,
        ["config", "default-power", "--ch", "1", "--enable", "--on"],
    )
    assert result.exit_code == 0
    data = json.loads(result.output)["data"]
    assert data["1"] == {"enabled": True, "value": True}


def test_config_auto_restore():
    result = runner.invoke(app, ["config", "auto-restore", "--enable"])
    assert result.exit_code == 0
    assert json.loads(result.output)["data"]["enabled"] is True


def test_config_operate_mode():
    result = runner.invoke(app, ["config", "operate-mode", "--mode", "interlock"])
    assert result.exit_code == 0
    assert json.loads(result.output)["data"]["mode"] == "interlock"


def test_config_device_address():
    result = runner.invoke(app, ["config", "device-address", "--address", "0x1234"])
    assert result.exit_code == 0
    assert json.loads(result.output)["data"]["address"] == 0x1234


def test_factory_reset():
    result = runner.invoke(app, ["config", "factory-reset"])
    assert result.exit_code == 0
    assert json.loads(result.output)["data"]["reset"] is True


def test_info():
    result = runner.invoke(app, ["info"])
    assert result.exit_code == 0
    data = json.loads(result.output)["data"]
    assert data["hardware_version"] == "V1.3"


def test_human_output():
    result = runner.invoke(app, ["--human", "config", "auto-restore", "--enable"])
    assert result.exit_code == 0
    assert "Success: True" in result.output


def test_invalid_channel():
    result = runner.invoke(app, ["power", "on", "--ch", "9"])
    assert result.exit_code != 0
    assert "Invalid channel" in result.output


def test_remote_power(mock_http_server):
    result = runner.invoke(
        app,
        ["--remote", mock_http_server, "power", "on", "--ch", "1"],
    )
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["data"]["1"] is True


def test_remote_voltage(mock_http_server):
    result = runner.invoke(
        app,
        ["--remote", mock_http_server, "voltage", "1"],
    )
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)["data"]
    assert data["channel"] == 1
    assert data["voltage"] == 5.1


def test_remote_config_operate_mode(mock_http_server):
    result = runner.invoke(
        app,
        ["--remote", mock_http_server, "config", "operate-mode", "--mode", "interlock"],
    )
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["data"]["mode"] == "interlock"


def test_remote_firmware_version(mock_http_server):
    result = runner.invoke(
        app,
        ["--remote", mock_http_server, "firmware-version"],
    )
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["data"]["version"] == "V1.15"


@pytest.fixture
def mock_http_server(mock_hub, monkeypatch):
    """Start a local HTTP server in a thread and return its base URL."""
    import threading
    import time
    import socket

    import uvicorn

    from smartusbhub_cli.http_server import app, _server_state
    from smartusbhub_cli.protocol import HubProtocol

    # Inject a HubProtocol backed by the fake hub class.  Because lifespan now
    # preserves an already-set protocol, the server thread will reuse it even
    # though it cannot see the test-process monkeypatches.
    _server_state.protocol = HubProtocol("/dev/fakehub")

    port = 18765
    server = uvicorn.Server(
        config=uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    for _ in range(50):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                break
        except OSError:
            time.sleep(0.1)
    else:
        server.should_exit = True
        thread.join(timeout=2)
        raise RuntimeError("Test HTTP server failed to start")

    yield f"http://127.0.0.1:{port}"

    server.should_exit = True
    thread.join(timeout=5)
    _server_state.protocol = None
