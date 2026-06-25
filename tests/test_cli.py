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

    real_load_config = config_module.load_config

    def fake_load_config(path=None):
        cfg = real_load_config(path)
        # Use the fake serial hub for every test.
        cfg.device = "/dev/fakehub"
        # When no explicit config path is supplied, ignore any user config that
        # might enable client mode so tests never accidentally talk to a real
        # server or the default hardware.
        if path is None:
            cfg.server_host = None
            cfg.server_port = None
        return cfg

    monkeypatch.setattr(config_module, "load_config", fake_load_config)


def test_help():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "CLI for SmartUSBHub" in result.output
    # The global-options-position note should be visible at the top level.
    assert "before the subcommand" in " ".join(result.output.split())
    # Channel selection and subcommand help hints should be visible.
    assert "--ch N (repeatable)" in " ".join(result.output.split())
    assert "smartusbhub <command> --help" in " ".join(result.output.split())


def test_channel_help_text():
    result = runner.invoke(app, ["power", "on", "--help"])
    assert result.exit_code == 0
    assert "--ch" in result.output
    assert "Repeat --ch for multiple" in " ".join(result.output.split())
    assert "smartusbhub power on --ch 1" in " ".join(result.output.split())


def test_power_on():
    result = runner.invoke(app, ["--no-pretty", "power", "on", "--ch", "1", "--ch", "3"])
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)["data"]
    assert data["1"] is True
    assert data["3"] is True


def test_power_off_all():
    result = runner.invoke(app, ["--no-pretty", "power", "off", "--all"])
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)["data"]
    assert all(v is False for v in data.values())


def test_power_on_verification_failure(monkeypatch):
    from smartusbhub_cli.protocol import HubProtocol

    def fake_get_power(_self, channels):
        return {ch: False for ch in channels}

    monkeypatch.setattr(HubProtocol, "get_power", fake_get_power)
    result = runner.invoke(app, ["--no-pretty", "power", "on", "--ch", "1"])
    assert result.exit_code == 1
    assert "Power ON verification failed" in " ".join(result.output.split())


def test_power_status():
    runner.invoke(app, ["--no-pretty", "power", "on", "--ch", "2"])
    result = runner.invoke(app, ["--no-pretty", "power", "status", "--ch", "2"])
    assert result.exit_code == 0
    assert json.loads(result.output)["data"]["2"] is True


def test_interlock():
    result = runner.invoke(app, ["--no-pretty", "interlock", "1"])
    assert result.exit_code == 0
    data = json.loads(result.output)["data"]
    assert data["1"] is False


def test_dataline_on():
    result = runner.invoke(app, ["--no-pretty", "dataline", "on", "--ch", "4"])
    assert result.exit_code == 0
    assert json.loads(result.output)["data"]["4"] is True


def test_voltage():
    result = runner.invoke(app, ["--no-pretty", "voltage", "1"])
    assert result.exit_code == 0
    data = json.loads(result.output)["data"]
    assert data["1"] == 5.1


def test_current():
    result = runner.invoke(app, ["--no-pretty", "current", "4"])
    assert result.exit_code == 0
    data = json.loads(result.output)["data"]
    assert data["4"] == 0.4


def test_voltage_multiple():
    result = runner.invoke(app, ["--no-pretty", "voltage", "1", "3"])
    assert result.exit_code == 0
    data = json.loads(result.output)["data"]
    assert data["1"] == 5.1
    assert data["3"] == 4.9


def test_voltage_all():
    result = runner.invoke(app, ["--no-pretty", "voltage", "--all"])
    assert result.exit_code == 0
    data = json.loads(result.output)["data"]
    assert set(int(k) for k in data.keys()) == {1, 2, 3, 4}


def test_voltage_help():
    result = runner.invoke(app, ["voltage", "--help"])
    assert result.exit_code == 0
    assert "[CHANNELS]" in result.output
    assert "smartusbhub voltage 1" in " ".join(result.output.split())


def test_current_invalid_channel():
    result = runner.invoke(app, ["--no-pretty", "current", "9"])
    assert result.exit_code != 0
    assert "Invalid channel" in result.output
    assert "Channels must be integers from 1 to 4" in " ".join(result.output.split())


def test_interlock_invalid_channel():
    result = runner.invoke(app, ["--no-pretty", "interlock", "9"])
    assert result.exit_code != 0
    assert "Invalid channel" in result.output
    assert "0 (all-off) or an integer from 1 to 4" in " ".join(result.output.split())


def test_power_group_help():
    result = runner.invoke(app, ["power", "--help"])
    assert result.exit_code == 0
    assert "on" in result.output
    assert "off" in result.output
    assert "status" in result.output


def test_config_default_power():
    result = runner.invoke(
        app,
        ["--no-pretty", "config", "default-power", "--ch", "1", "--enable", "--on"],
    )
    assert result.exit_code == 0
    data = json.loads(result.output)["data"]
    assert data["1"] == {"enabled": True, "value": True}


def test_config_auto_restore():
    result = runner.invoke(app, ["--no-pretty", "config", "auto-restore", "--enable"])
    assert result.exit_code == 0
    assert json.loads(result.output)["data"]["enabled"] is True


def test_config_operate_mode():
    result = runner.invoke(app, ["--no-pretty", "config", "operate-mode", "--mode", "interlock"])
    assert result.exit_code == 0
    assert json.loads(result.output)["data"]["mode"] == "interlock"


def test_config_device_address():
    result = runner.invoke(app, ["--no-pretty", "config", "device-address", "--address", "0x1234"])
    assert result.exit_code == 0
    assert json.loads(result.output)["data"]["address"] == 0x1234


def test_factory_reset():
    result = runner.invoke(app, ["--no-pretty", "config", "factory-reset"])
    assert result.exit_code == 0
    assert json.loads(result.output)["data"]["reset"] is True


def test_info():
    result = runner.invoke(app, ["--no-pretty", "info"])
    assert result.exit_code == 0
    data = json.loads(result.output)["data"]
    assert data["hardware_version"] == "V1.3"


def test_status_per_channel():
    result = runner.invoke(app, ["--no-pretty", "status"])
    assert result.exit_code == 0
    data = json.loads(result.output)["data"]
    # Status keeps device metadata and groups the rest by channel.
    assert set(data.keys()) == {"device", "channels"}
    assert data["device"]["hardware_version"] == "V1.3"
    assert set(data["channels"].keys()) == {"1", "2", "3", "4"}
    for ch in ("1", "2", "3", "4"):
        assert set(data["channels"][ch].keys()) == {
            "power",
            "dataline",
            "voltage",
            "current",
            "default_power",
            "default_dataline",
        }


def test_help_command():
    result = runner.invoke(app, ["help"])
    assert result.exit_code == 0
    assert "CLI for SmartUSBHub" in result.output
    assert "smartusbhub <command> --help" in " ".join(result.output.split())


def test_help_command_with_help_flag():
    result = runner.invoke(app, ["help", "--help"])
    assert result.exit_code == 0
    assert "CLI for SmartUSBHub" in result.output


def test_pretty_default_output():
    result = runner.invoke(app, ["power", "on", "--ch", "1"])
    assert result.exit_code == 0
    assert "Status: OK" in result.output
    assert "Channel 1: on" in result.output


def test_no_pretty_compact_json():
    result = runner.invoke(app, ["--no-pretty", "power", "on", "--ch", "1"])
    assert result.exit_code == 0
    data = json.loads(result.output)["data"]
    assert data["1"] is True


def test_invalid_channel():
    result = runner.invoke(app, ["power", "on", "--ch", "9"])
    assert result.exit_code != 0
    assert "Invalid channel" in result.output


def test_remote_power(mock_http_server):
    result = runner.invoke(
        app,
        ["--no-pretty", "--remote", mock_http_server, "power", "on", "--ch", "1"],
    )
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["data"]["1"] is True


def test_remote_voltage(mock_http_server):
    result = runner.invoke(
        app,
        ["--no-pretty", "--remote", mock_http_server, "voltage", "1"],
    )
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)["data"]
    assert data["1"] == 5.1


def test_remote_config_operate_mode(mock_http_server):
    result = runner.invoke(
        app,
        ["--no-pretty", "--remote", mock_http_server, "config", "operate-mode", "--mode", "interlock"],
    )
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["data"]["mode"] == "interlock"


def test_remote_firmware_version(mock_http_server):
    result = runner.invoke(
        app,
        ["--no-pretty", "--remote", mock_http_server, "firmware-version"],
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
        config=uvicorn.Config(
            app, host="127.0.0.1", port=port, log_level="warning", ws="none"
        )
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


# ------------------------------------------------------------------
# Local / remote parity
# ------------------------------------------------------------------
@pytest.fixture(params=["local", "remote"])
def cli_invoke(request):
    """Run a CLI invocation in either local or remote (client) mode."""

    def _invoke(args):
        prefix = ["--no-pretty"]
        if request.param == "remote":
            mock_http_server = request.getfixturevalue("mock_http_server")
            prefix.extend(["--remote", mock_http_server])
        return runner.invoke(app, prefix + args)

    return _invoke


def test_parity_power_on(cli_invoke):
    result = cli_invoke(["power", "on", "--ch", "1", "--ch", "3"])
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)["data"]
    assert data["1"] is True
    assert data["3"] is True


def test_parity_power_off_all(cli_invoke):
    cli_invoke(["power", "on", "--all"])
    result = cli_invoke(["power", "off", "--all"])
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)["data"]
    assert all(v is False for v in data.values())


def test_parity_power_status(cli_invoke):
    cli_invoke(["power", "on", "--ch", "2"])
    result = cli_invoke(["power", "status", "--ch", "2"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["data"]["2"] is True


def test_parity_interlock(cli_invoke):
    cli_invoke(["power", "on", "--ch", "1"])
    result = cli_invoke(["interlock", "1"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["data"]["1"] is False


def test_parity_dataline(cli_invoke):
    result = cli_invoke(["dataline", "on", "--ch", "4"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["data"]["4"] is True


def test_parity_voltage(cli_invoke):
    result = cli_invoke(["voltage", "1"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["data"]["1"] == 5.1


def test_parity_current(cli_invoke):
    result = cli_invoke(["current", "4"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["data"]["4"] == 0.4


def test_parity_config_default_power(cli_invoke):
    result = cli_invoke(["config", "default-power", "--ch", "1", "--enable", "--on"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["data"]["1"] == {"enabled": True, "value": True}


def test_parity_config_auto_restore(cli_invoke):
    result = cli_invoke(["config", "auto-restore", "--enable"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["data"]["enabled"] is True


def test_parity_config_operate_mode(cli_invoke):
    result = cli_invoke(["config", "operate-mode", "--mode", "interlock"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["data"]["mode"] == "interlock"


def test_parity_config_device_address(cli_invoke):
    result = cli_invoke(["config", "device-address", "--address", "0x1234"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["data"]["address"] == 0x1234


def test_parity_factory_reset(cli_invoke):
    result = cli_invoke(["config", "factory-reset"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["data"]["reset"] is True


def test_parity_info(cli_invoke):
    result = cli_invoke(["info"])
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)["data"]
    assert data["hardware_version"] == "V1.3"


def test_parity_status(cli_invoke):
    result = cli_invoke(["status"])
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)["data"]
    assert set(data.keys()) == {"device", "channels"}
    assert data["device"]["hardware_version"] == "V1.3"
    assert set(data["channels"].keys()) == {"1", "2", "3", "4"}


def test_parity_firmware_version(cli_invoke):
    result = cli_invoke(["firmware-version"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["data"]["version"] == "V1.15"


def test_parity_hardware_version(cli_invoke):
    result = cli_invoke(["hardware-version"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["data"]["version"] == "V1.3"


# ------------------------------------------------------------------
# Config-driven client / server mode
# ------------------------------------------------------------------
def test_config_file_enables_client_mode(tmp_path, monkeypatch, mock_http_server):
    from smartusbhub_cli import config as config_module

    config_path = tmp_path / "smartusbhub_cli.json"
    config_path.write_text(json.dumps({"server_host": "127.0.0.1", "server_port": 18765}))

    original_load_config = config_module.load_config

    def fake_load_config(path=None):
        cfg = original_load_config(path)
        cfg.device = "/dev/fakehub"
        return cfg

    monkeypatch.setattr(config_module, "load_config", fake_load_config)

    result = runner.invoke(
        app,
        ["--no-pretty", "--config", str(config_path), "firmware-version"],
    )
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["data"]["version"] == "V1.15"


def test_server_command_uses_config_host_port(tmp_path, monkeypatch):
    from smartusbhub_cli import config as config_module

    config_path = tmp_path / "smartusbhub_cli.json"
    config_path.write_text(
        json.dumps({"server_host": "192.168.1.10", "server_port": 18766})
    )

    original_load_config = config_module.load_config

    def fake_load_config(path=None):
        cfg = original_load_config(path)
        cfg.device = "/dev/fakehub"
        return cfg

    monkeypatch.setattr(config_module, "load_config", fake_load_config)

    captured = {}

    def fake_run_server(host, port, port_name=None):
        captured["host"] = host
        captured["port"] = port
        captured["port_name"] = port_name

    monkeypatch.setattr("smartusbhub_cli.http_server.run_server", fake_run_server)

    result = runner.invoke(app, ["--config", str(config_path), "server"])
    assert result.exit_code == 0, result.output
    assert captured["host"] == "192.168.1.10"
    assert captured["port"] == 18766

    # CLI arguments override config values.
    captured.clear()
    result = runner.invoke(
        app,
        [
            "--config",
            str(config_path),
            "server",
            "--host",
            "0.0.0.0",
            "--port",
            "9000",
        ],
    )
    assert result.exit_code == 0, result.output
    assert captured["host"] == "0.0.0.0"
    assert captured["port"] == 9000


# ------------------------------------------------------------------
# setup subcommand
# ------------------------------------------------------------------
def _read_config_file(path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def test_setup_native(tmp_path):
    config_path = tmp_path / "smartusbhub_cli.json"
    result = runner.invoke(
        app, ["--no-pretty", "--config", str(config_path), "setup", "--native"]
    )
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["data"]["mode"] == "native"

    data = _read_config_file(config_path)
    assert data["device"] == "/dev/ttyACM0"
    assert data.get("server_host") is None


def test_setup_remote(tmp_path):
    config_path = tmp_path / "smartusbhub_cli.json"
    result = runner.invoke(
        app,
        [
            "--no-pretty",
            "--config",
            str(config_path),
            "setup",
            "--remote",
            "--host",
            "0.0.0.0",
        ],
    )
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["data"]["mode"] == "remote"

    data = _read_config_file(config_path)
    # Remote mode keeps device so the same file can run a local server
    # and also drive client-mode subcommands.
    assert data["device"] == "/dev/ttyACM0"
    assert data["server_host"] == "0.0.0.0"
    assert isinstance(data["server_port"], int)
    assert data["server_port"] > 9000


def test_setup_mcp(tmp_path):
    config_path = tmp_path / "smartusbhub_cli.json"
    result = runner.invoke(
        app,
        [
            "--no-pretty",
            "--config",
            str(config_path),
            "setup",
            "--mcp",
            "--host",
            "0.0.0.0",
        ],
    )
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["data"]["mode"] == "mcp"

    data = _read_config_file(config_path)
    assert data["device"] == "/dev/ttyACM0"
    assert data["mcp_host"] == "0.0.0.0"
    assert data["mcp_transport"] == "sse"
    assert isinstance(data["mcp_port"], int)
    assert data["mcp_port"] > 9000


# ------------------------------------------------------------------
# explicit client subcommand
# ------------------------------------------------------------------
def test_client_subcommand(mock_http_server):
    host, port = mock_http_server.replace("http://", "").split(":")
    result = runner.invoke(
        app,
        ["--no-pretty", "client", "--host", host, "--port", port, "firmware-version"],
    )
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["data"]["version"] == "V1.15"


def test_client_subcommand_requires_host_or_config(tmp_path, monkeypatch):
    from smartusbhub_cli import config as config_module

    config_path = tmp_path / "smartusbhub_cli.json"
    config_path.write_text(json.dumps({}))

    original_load_config = config_module.load_config

    def fake_load_config(path=None):
        cfg = original_load_config(path)
        cfg.device = "/dev/fakehub"
        return cfg

    monkeypatch.setattr(config_module, "load_config", fake_load_config)

    result = runner.invoke(
        app,
        ["--config", str(config_path), "--no-pretty", "client", "info"],
    )
    assert result.exit_code != 0
    assert "client mode requires" in " ".join(result.output.split())


# ------------------------------------------------------------------
# server auto-scan
# ------------------------------------------------------------------
def test_server_auto_scans_single_hub(tmp_path, monkeypatch, mock_hub):
    from smartusbhub_cli import config as config_module
    from smartusbhub_cli.protocol import HubProtocol

    config_path = tmp_path / "smartusbhub_cli.json"
    config_path.write_text(json.dumps({}))

    original_load_config = config_module.load_config

    def fake_load_config(path=None):
        cfg = original_load_config(path)
        cfg.device = None
        return cfg

    monkeypatch.setattr(config_module, "load_config", fake_load_config)

    captured = {}

    def fake_run_server(host, port, port_name=None):
        captured["host"] = host
        captured["port"] = port
        captured["port_name"] = port_name

    monkeypatch.setattr("smartusbhub_cli.http_server.run_server", fake_run_server)

    result = runner.invoke(
        app, ["--config", str(config_path), "server", "--port", "9000"]
    )
    assert result.exit_code == 0, result.output
    assert captured["host"] == "127.0.0.1"
    assert captured["port"] == 9000
    assert captured["port_name"] == "/dev/fakehub"


def test_server_warns_when_no_hub(tmp_path, monkeypatch):
    from smartusbhub_cli import config as config_module
    from smartusbhub_cli.protocol import HubProtocol

    config_path = tmp_path / "smartusbhub_cli.json"
    config_path.write_text(json.dumps({}))

    original_load_config = config_module.load_config

    def fake_load_config(path=None):
        cfg = original_load_config(path)
        cfg.device = None
        return cfg

    monkeypatch.setattr(config_module, "load_config", fake_load_config)
    monkeypatch.setattr(HubProtocol, "scan_ports", lambda: [])

    captured = {}

    def fake_run_server(host, port, port_name=None):
        captured["host"] = host
        captured["port"] = port
        captured["port_name"] = port_name

    monkeypatch.setattr("smartusbhub_cli.http_server.run_server", fake_run_server)

    result = runner.invoke(
        app, ["--config", str(config_path), "server", "--port", "9000"]
    )
    assert result.exit_code != 0
    assert "No SmartUSBHub detected" in " ".join(result.output.split())


def test_server_warns_when_multiple_hubs(tmp_path, monkeypatch):
    from smartusbhub_cli import config as config_module
    from smartusbhub_cli.protocol import HubProtocol

    config_path = tmp_path / "smartusbhub_cli.json"
    config_path.write_text(json.dumps({}))

    original_load_config = config_module.load_config

    def fake_load_config(path=None):
        cfg = original_load_config(path)
        cfg.device = None
        return cfg

    monkeypatch.setattr(config_module, "load_config", fake_load_config)
    monkeypatch.setattr(
        HubProtocol, "scan_ports", lambda: ["/dev/hub1", "/dev/hub2"]
    )

    captured = {}

    def fake_run_server(host, port, port_name=None):
        captured["host"] = host
        captured["port"] = port
        captured["port_name"] = port_name

    monkeypatch.setattr("smartusbhub_cli.http_server.run_server", fake_run_server)

    result = runner.invoke(
        app, ["--config", str(config_path), "server", "--port", "9000"]
    )
    assert result.exit_code != 0
    assert "Multiple SmartUSBHubs detected" in " ".join(result.output.split())


def test_remote_commit_hash_mismatch(mock_http_server, monkeypatch):
    """The CLI must exit when its commit hash does not match the server's."""
    from smartusbhub_cli import client as client_module

    monkeypatch.setattr(client_module, "get_commit_hash", lambda: "mismatch")

    result = runner.invoke(
        app,
        ["--no-pretty", "--remote", mock_http_server, "firmware-version"],
    )
    assert result.exit_code != 0
    assert "Commit hash mismatch" in " ".join(result.output.split())
