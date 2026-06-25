"""Tests for ``smartusbhub_cli.mcp_server``."""

from __future__ import annotations

import pytest

from smartusbhub_cli.mcp_server import MCPServer


@pytest.fixture
def mcp_server(mock_hub, monkeypatch):
    """Return a configured MCPServer with a mocked hub."""
    from smartusbhub_cli import config as config_module

    original_load_config = config_module.load_config

    def fake_load_config(path=None):
        cfg = original_load_config(path)
        cfg.port = "/dev/fakehub"
        return cfg

    monkeypatch.setattr(config_module, "load_config", fake_load_config)

    server = MCPServer(port_name="/dev/fakehub")
    server.register_tools()
    return server


def _tool_text(result):
    """Unpack the (content, meta) tuple returned by FastMCP.call_tool."""
    content, _meta = result
    return content[0].text


async def test_mcp_tool_power_on(mcp_server):
    result = await mcp_server.mcp.call_tool("power_on", {"channels": [1, 3]})
    import json

    data = json.loads(_tool_text(result))["data"]
    assert data["1"] is True
    assert data["3"] is True


async def test_mcp_tool_power_status(mcp_server):
    await mcp_server.mcp.call_tool("power_on", {"channels": [2]})
    result = await mcp_server.mcp.call_tool("power_status", {"channels": [2]})
    import json

    data = json.loads(_tool_text(result))["data"]
    assert data["2"] is True


async def test_mcp_tool_voltage(mcp_server):
    result = await mcp_server.mcp.call_tool("voltage", {"channel": 1})
    import json

    data = json.loads(_tool_text(result))["data"]
    assert data["voltage"] == 5.1


async def test_mcp_tool_operate_mode(mcp_server):
    result = await mcp_server.mcp.call_tool(
        "set_operate_mode", {"mode": "interlock"}
    )
    import json

    data = json.loads(_tool_text(result))["data"]
    assert data["mode"] == "interlock"


async def test_mcp_tool_device_info(mcp_server):
    result = await mcp_server.mcp.call_tool("device_info", {})
    import json

    data = json.loads(_tool_text(result))["data"]
    assert data["hardware_version"] == "V1.3"


async def test_mcp_tool_factory_reset(mcp_server):
    result = await mcp_server.mcp.call_tool("factory_reset", {})
    import json

    data = json.loads(_tool_text(result))["data"]
    assert data["reset"] is True
