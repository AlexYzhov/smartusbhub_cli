"""MCP (Model Control Protocol) server for SmartUSBHub.

Exposes hub control as MCP tools so AI agents on the LAN can invoke commands
via IP:PORT (when transport is SSE) or stdio (for local spawning).
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, Callable, Dict, List, Optional

from mcp.server import FastMCP

from smartusbhub_cli.config import DEFAULT_MCP_PORT, load_config
from smartusbhub_cli.protocol import HubError, HubProtocol, HubState
from smartusbhub_cli.utils import resolve_channels


class MCPServer:
    """MCP server wrapping SmartUSBHub operations."""

    def __init__(self, port_name: Optional[str] = None) -> None:
        self.port_name = port_name
        self.protocol: Optional[HubProtocol] = None
        self.mcp = FastMCP("smartusbhub")

    def _get_protocol(self) -> HubProtocol:
        if self.protocol is None:
            cfg = load_config()
            device = self.port_name or cfg.device
            if not device:
                raise HubError("No serial device configured for MCP server")
            self.protocol = HubProtocol(device, cfg.baudrate, cfg.timeout)
        return self.protocol

    def _tool_result(self, data: Any) -> str:
        """Serialize a successful tool result."""
        return json.dumps({"success": True, "data": data})

    def _tool_error(self, message: str) -> str:
        """Serialize a tool error."""
        return json.dumps({"success": False, "error": message})

    def _call(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> str:
        """Invoke a protocol method and return JSON text, catching hub errors."""
        try:
            return self._tool_result(fn(self._get_protocol(), *args, **kwargs))
        except HubError as exc:
            return self._tool_error(str(exc))
        except ValueError as exc:
            return self._tool_error(str(exc))

    def register_tools(self) -> None:
        """Register all hub tools with the MCP server."""

        # ------------------------------------------------------------------
        # Power
        # ------------------------------------------------------------------
        @self.mcp.tool()
        def power_on(channels: List[int]) -> str:
            """Turn power on for channels."""
            chs = resolve_channels(channels)
            return self._call(HubProtocol.set_power, chs, True)

        @self.mcp.tool()
        def power_off(channels: List[int]) -> str:
            """Turn power off for channels."""
            chs = resolve_channels(channels)
            return self._call(HubProtocol.set_power, chs, False)

        @self.mcp.tool()
        def power_status(channels: List[int]) -> str:
            """Read channel power states."""
            chs = resolve_channels(channels)
            return self._call(HubProtocol.get_power, chs)

        @self.mcp.tool()
        def interlock(channel: int) -> str:
            """Set interlock on a channel."""
            return self._call(HubProtocol.set_interlock, channel)

        # ------------------------------------------------------------------
        # Dataline
        # ------------------------------------------------------------------
        @self.mcp.tool()
        def dataline_on(channels: List[int]) -> str:
            """Connect data lines."""
            chs = resolve_channels(channels)
            return self._call(HubProtocol.set_dataline, chs, True)

        @self.mcp.tool()
        def dataline_off(channels: List[int]) -> str:
            """Disconnect data lines."""
            chs = resolve_channels(channels)
            return self._call(HubProtocol.set_dataline, chs, False)

        @self.mcp.tool()
        def dataline_status(channels: List[int]) -> str:
            """Read data-line states."""
            chs = resolve_channels(channels)
            return self._call(HubProtocol.get_dataline, chs)

        # ------------------------------------------------------------------
        # Measurements
        # ------------------------------------------------------------------
        @self.mcp.tool()
        def voltage(channel: int) -> str:
            """Read channel voltage."""
            return self._call(
                lambda proto, ch: {"channel": ch, "voltage": proto.get_voltage(ch)},
                channel,
            )

        @self.mcp.tool()
        def current(channel: int) -> str:
            """Read channel current."""
            return self._call(
                lambda proto, ch: {"channel": ch, "current": proto.get_current(ch)},
                channel,
            )

        # ------------------------------------------------------------------
        # Config
        # ------------------------------------------------------------------
        @self.mcp.tool()
        def set_default_power(
            channels: List[int], enable: bool, state: bool = False
        ) -> str:
            """Configure default power."""
            chs = resolve_channels(channels)
            return self._call(HubProtocol.set_default_power, chs, enable, state)

        @self.mcp.tool()
        def get_default_power(channels: List[int]) -> str:
            """Read default power config."""
            chs = resolve_channels(channels)
            return self._call(HubProtocol.get_default_power, chs)

        @self.mcp.tool()
        def set_default_dataline(
            channels: List[int], enable: bool, state: bool = False
        ) -> str:
            """Configure default dataline."""
            chs = resolve_channels(channels)
            return self._call(HubProtocol.set_default_dataline, chs, enable, state)

        @self.mcp.tool()
        def get_default_dataline(channels: List[int]) -> str:
            """Read default dataline config."""
            chs = resolve_channels(channels)
            return self._call(HubProtocol.get_default_dataline, chs)

        @self.mcp.tool()
        def set_auto_restore(enable: bool) -> str:
            """Enable/disable auto restore."""
            return self._call(
                lambda proto, en: {"enabled": proto.set_auto_restore(en)}, enable
            )

        @self.mcp.tool()
        def get_auto_restore() -> str:
            """Read auto restore state."""
            return self._call(
                lambda proto: {"enabled": proto.get_auto_restore()}
            )

        @self.mcp.tool()
        def set_button_control(enable: bool) -> str:
            """Enable/disable button control."""
            return self._call(
                lambda proto, en: {"enabled": proto.set_button_control(en)}, enable
            )

        @self.mcp.tool()
        def get_button_control() -> str:
            """Read button control state."""
            return self._call(
                lambda proto: {"enabled": proto.get_button_control()}
            )

        @self.mcp.tool()
        def set_operate_mode(mode: str) -> str:
            """Set normal/interlock mode."""
            return self._call(
                lambda proto, m: {"mode": proto.set_operate_mode(m)}, mode
            )

        @self.mcp.tool()
        def get_operate_mode() -> str:
            """Read operate mode."""
            return self._call(
                lambda proto: {"mode": proto.get_operate_mode()}
            )

        @self.mcp.tool()
        def set_device_address(address: int) -> str:
            """Set 16-bit device address."""
            return self._call(
                lambda proto, addr: {"address": proto.set_device_address(addr)},
                address,
            )

        @self.mcp.tool()
        def get_device_address() -> str:
            """Read device address."""
            return self._call(
                lambda proto: {"address": proto.get_device_address()}
            )

        @self.mcp.tool()
        def factory_reset() -> str:
            """Factory reset."""
            return self._call(
                lambda proto: {"reset": proto.factory_reset()}
            )

        @self.mcp.tool()
        def firmware_version() -> str:
            """Read firmware version."""
            return self._call(
                lambda proto: {"version": proto.get_firmware_version()}
            )

        @self.mcp.tool()
        def hardware_version() -> str:
            """Read hardware version."""
            return self._call(
                lambda proto: {"version": proto.get_hardware_version()}
            )

        @self.mcp.tool()
        def device_info() -> str:
            """Full device snapshot."""
            def _info(proto: HubProtocol) -> Dict[str, Any]:
                info = proto.get_device_info()
                return info.to_dict() if isinstance(info, HubState) else info

            return self._call(_info)

    def run_stdio(self) -> None:
        """Run the MCP server over stdio transport."""
        asyncio.run(self.mcp.run_stdio_async())

    def run_sse(self, host: str, port: int) -> None:
        """Run the MCP server over SSE transport."""
        asyncio.run(self.mcp.run_sse_async(host=host, port=port))


def run_mcp(
    transport: str = "stdio",
    host: str = "127.0.0.1",
    port: int = DEFAULT_MCP_PORT,
    serial_port: Optional[str] = None,
) -> None:
    """Convenience entry point used by the CLI."""
    server = MCPServer(port_name=serial_port)
    server.register_tools()
    if transport == "stdio":
        server.run_stdio()
    elif transport == "sse":
        server.run_sse(host=host, port=port)
    else:
        raise ValueError(f"Unsupported MCP transport: {transport}")
