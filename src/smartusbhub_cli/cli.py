"""Typer-based CLI for smartusbhub_cli.

Modes:
- Local serial: ``smartusbhub power on --ch 1``
- Remote HTTP client: ``smartusbhub --remote http://IP:PORT power on --ch 1``
- HTTP server: ``smartusbhub server --host 0.0.0.0 --port 8000``
- MCP server: ``smartusbhub mcp --transport stdio``
"""

from __future__ import annotations

import functools
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, TypeVar, Union

import typer

from smartusbhub_cli.client import HTTPClient, HTTPClientError
from smartusbhub_cli.config import Config, load_config
from smartusbhub_cli.protocol import HubError, HubNotFoundError, HubProtocol
from smartusbhub_cli.utils import OutputFormatter, resolve_channels

app = typer.Typer(help="CLI for SmartUSBHub")

ClientLike = Union[HubProtocol, HTTPClient]
F = TypeVar("F", bound=Callable[..., Any])


def _parse_int(value: str) -> int:
    """Parse an integer, supporting decimal and ``0x`` hex prefixes."""
    return int(value, 0)


class _LazyHub:
    """Lazy wrapper that instantiates ``HubProtocol`` on first use."""

    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg
        self._hub: Optional[HubProtocol] = None

    def __getattr__(self, name: str) -> Any:
        if self._hub is None:
            port = self.cfg.port
            if not port:
                ports = HubProtocol.scan_ports()
                if ports:
                    port = ports[0]
                else:
                    raise HubNotFoundError(
                        "No serial port specified and no SmartUSBHub detected"
                    )
            self._hub = HubProtocol(port, self.cfg.baudrate, self.cfg.timeout)
        return getattr(self._hub, name)

    def close(self) -> None:
        if self._hub is not None:
            self._hub.close()


def _handle_errors(func: F) -> F:
    """Catch hub/client errors and emit them through the formatter."""

    @functools.wraps(func)
    def wrapper(ctx: typer.Context, *args: Any, **kwargs: Any) -> Any:
        try:
            return func(ctx, *args, **kwargs)
        except (HubError, HTTPClientError, ValueError) as exc:
            formatter = ctx.ensure_object(dict).get("formatter")
            if formatter is not None:
                typer.echo(formatter.fail(str(exc)), err=True)
            else:
                typer.echo(str(exc), err=True)
            raise typer.Exit(code=1) from exc

    return wrapper  # type: ignore[return-value]


def _get_formatter(ctx: typer.Context) -> OutputFormatter:
    return ctx.ensure_object(dict)["formatter"]


def _get_client(ctx: typer.Context) -> ClientLike:
    return ctx.ensure_object(dict)["client"]


def _echo(ctx: typer.Context, data: Any) -> None:
    typer.echo(_get_formatter(ctx).ok(data))


def _resolve(
    channels: List[int], all_channels: bool, default: Optional[List[int]] = None
) -> List[int]:
    try:
        return resolve_channels(channels, all_channels, default)
    except ValueError as exc:
        raise typer.BadParameter(str(exc))


@app.callback()
def main(
    ctx: typer.Context,
    port: Optional[str] = typer.Option(
        None, "--port", "-p", help="Serial port (e.g. /dev/ttyUSB0 or COM3)."
    ),
    remote: Optional[str] = typer.Option(
        None, "--remote", "-r", help="Remote HTTP server URL (enables client mode)."
    ),
    human: bool = typer.Option(False, "--human", "-h", help="Human-readable output."),
    config_file: Optional[str] = typer.Option(
        None, "--config", help="Path to configuration file."
    ),
) -> None:
    """Global CLI options."""
    cfg = load_config(Path(config_file) if config_file else None)
    if port:
        cfg.port = port
    if remote:
        cfg.remote_url = remote
    cfg.human_readable = human

    ctx.ensure_object(dict)
    ctx.obj["config"] = cfg
    ctx.obj["formatter"] = OutputFormatter(human_readable=human)

    if cfg.is_remote():
        ctx.obj["client"] = HTTPClient(cfg.remote_url)
    else:
        ctx.obj["client"] = _LazyHub(cfg)


# ------------------------------------------------------------------
# power
# ------------------------------------------------------------------
power_app = typer.Typer(help="Control channel power.")
app.add_typer(power_app, name="power")


@power_app.command("on")
@_handle_errors
def power_on(
    ctx: typer.Context,
    channels: List[int] = typer.Option([], "--ch", help="Channel number(s)."),
    all_channels: bool = typer.Option(False, "--all", help="Apply to all channels."),
) -> None:
    """Turn power ON for the selected channels."""
    chs = _resolve(channels, all_channels)
    data = _get_client(ctx).set_power(chs, True)
    _echo(ctx, data)


@power_app.command("off")
@_handle_errors
def power_off(
    ctx: typer.Context,
    channels: List[int] = typer.Option([], "--ch", help="Channel number(s)."),
    all_channels: bool = typer.Option(False, "--all", help="Apply to all channels."),
) -> None:
    """Turn power OFF for the selected channels."""
    chs = _resolve(channels, all_channels)
    data = _get_client(ctx).set_power(chs, False)
    _echo(ctx, data)


@power_app.command("status")
@_handle_errors
def power_status(
    ctx: typer.Context,
    channels: List[int] = typer.Option([], "--ch", help="Channel number(s)."),
    all_channels: bool = typer.Option(False, "--all", help="All channels."),
) -> None:
    """Get power status."""
    chs = _resolve(channels, all_channels)
    data = _get_client(ctx).get_power(chs)
    _echo(ctx, data)


# ------------------------------------------------------------------
# interlock
# ------------------------------------------------------------------
@app.command()
@_handle_errors
def interlock(
    ctx: typer.Context,
    channel: int = typer.Argument(..., help="Channel to interlock (0 for all-off)."),
) -> None:
    """Set interlock mode on a channel."""
    data = _get_client(ctx).set_interlock(channel)
    _echo(ctx, {"channel": channel, "interlock": data})


# ------------------------------------------------------------------
# dataline
# ------------------------------------------------------------------
dataline_app = typer.Typer(help="Control USB data lines.")
app.add_typer(dataline_app, name="dataline")


@dataline_app.command("on")
@_handle_errors
def dataline_on(
    ctx: typer.Context,
    channels: List[int] = typer.Option([], "--ch", help="Channel number(s)."),
    all_channels: bool = typer.Option(False, "--all", help="Apply to all channels."),
) -> None:
    """Connect data lines for selected channels."""
    chs = _resolve(channels, all_channels)
    data = _get_client(ctx).set_dataline(chs, True)
    _echo(ctx, data)


@dataline_app.command("off")
@_handle_errors
def dataline_off(
    ctx: typer.Context,
    channels: List[int] = typer.Option([], "--ch", help="Channel number(s)."),
    all_channels: bool = typer.Option(False, "--all", help="Apply to all channels."),
) -> None:
    """Disconnect data lines for selected channels."""
    chs = _resolve(channels, all_channels)
    data = _get_client(ctx).set_dataline(chs, False)
    _echo(ctx, data)


@dataline_app.command("status")
@_handle_errors
def dataline_status(
    ctx: typer.Context,
    channels: List[int] = typer.Option([], "--ch", help="Channel number(s)."),
    all_channels: bool = typer.Option(False, "--all", help="All channels."),
) -> None:
    """Get data line status."""
    chs = _resolve(channels, all_channels)
    data = _get_client(ctx).get_dataline(chs)
    _echo(ctx, data)


# ------------------------------------------------------------------
# measurements
# ------------------------------------------------------------------
@app.command()
@_handle_errors
def voltage(
    ctx: typer.Context,
    channel: int = typer.Argument(..., help="Channel 1-4."),
) -> None:
    """Read channel voltage."""
    value = _get_client(ctx).get_voltage(channel)
    _echo(ctx, {"channel": channel, "voltage": value})


@app.command()
@_handle_errors
def current(
    ctx: typer.Context,
    channel: int = typer.Argument(..., help="Channel 1-4."),
) -> None:
    """Read channel current."""
    value = _get_client(ctx).get_current(channel)
    _echo(ctx, {"channel": channel, "current": value})


# ------------------------------------------------------------------
# config
# ------------------------------------------------------------------
config_app = typer.Typer(help="Device configuration.")
app.add_typer(config_app, name="config")


@config_app.command("default-power")
@_handle_errors
def config_default_power(
    ctx: typer.Context,
    channels: List[int] = typer.Option([], "--ch", help="Channel number(s)."),
    all_channels: bool = typer.Option(False, "--all", help="All channels."),
    enable: bool = typer.Option(True, "--enable/--disable", help="Enable default state."),
    state: Optional[bool] = typer.Option(
        None, "--on/--off", help="Default power state when enabled."
    ),
    get: bool = typer.Option(False, "--get", help="Get instead of set."),
) -> None:
    """Set/get default power status."""
    chs = _resolve(channels, all_channels)
    client = _get_client(ctx)
    if get:
        data = client.get_default_power(chs)
    else:
        data = client.set_default_power(chs, enable, state)
    _echo(ctx, data)


@config_app.command("default-dataline")
@_handle_errors
def config_default_dataline(
    ctx: typer.Context,
    channels: List[int] = typer.Option([], "--ch", help="Channel number(s)."),
    all_channels: bool = typer.Option(False, "--all", help="All channels."),
    enable: bool = typer.Option(True, "--enable/--disable", help="Enable default state."),
    state: Optional[bool] = typer.Option(
        None, "--on/--off", help="Default dataline state when enabled."
    ),
    get: bool = typer.Option(False, "--get", help="Get instead of set."),
) -> None:
    """Set/get default dataline status."""
    chs = _resolve(channels, all_channels)
    client = _get_client(ctx)
    if get:
        data = client.get_default_dataline(chs)
    else:
        data = client.set_default_dataline(chs, enable, state)
    _echo(ctx, data)


@config_app.command("auto-restore")
@_handle_errors
def config_auto_restore(
    ctx: typer.Context,
    enable: Optional[bool] = typer.Option(
        None, "--enable/--disable", help="Enable or disable auto restore."
    ),
) -> None:
    """Set/get auto restore."""
    client = _get_client(ctx)
    if enable is None:
        data = {"enabled": client.get_auto_restore()}
    else:
        data = {"enabled": client.set_auto_restore(enable)}
    _echo(ctx, data)


@config_app.command("button-control")
@_handle_errors
def config_button_control(
    ctx: typer.Context,
    enable: Optional[bool] = typer.Option(
        None, "--enable/--disable", help="Enable or disable button control."
    ),
) -> None:
    """Set/get button control."""
    client = _get_client(ctx)
    if enable is None:
        data = {"enabled": client.get_button_control()}
    else:
        data = {"enabled": client.set_button_control(enable)}
    _echo(ctx, data)


@config_app.command("operate-mode")
@_handle_errors
def config_operate_mode(
    ctx: typer.Context,
    mode: Optional[str] = typer.Option(
        None, "--mode", help="normal or interlock."
    ),
) -> None:
    """Set/get operate mode."""
    client = _get_client(ctx)
    if mode is None:
        data = {"mode": client.get_operate_mode()}
    else:
        data = {"mode": client.set_operate_mode(mode)}
    _echo(ctx, data)


@config_app.command("device-address")
@_handle_errors
def config_device_address(
    ctx: typer.Context,
    address: Optional[int] = typer.Option(
        None, "--address", help="16-bit device address.", parser=_parse_int
    ),
) -> None:
    """Set/get device address."""
    client = _get_client(ctx)
    if address is None:
        data = {"address": client.get_device_address()}
    else:
        data = {"address": client.set_device_address(address)}
    _echo(ctx, data)


@config_app.command("factory-reset")
@_handle_errors
def config_factory_reset(ctx: typer.Context) -> None:
    """Perform factory reset."""
    data = _get_client(ctx).factory_reset()
    _echo(ctx, {"reset": data})


# ------------------------------------------------------------------
# info / version
# ------------------------------------------------------------------
@app.command()
@_handle_errors
def info(ctx: typer.Context) -> None:
    """Get full device information."""
    data = _get_client(ctx).get_device_info()
    if hasattr(data, "to_dict"):
        data = data.to_dict()
    _echo(ctx, data)


@app.command()
@_handle_errors
def firmware_version(ctx: typer.Context) -> None:
    """Get firmware version."""
    value = _get_client(ctx).get_firmware_version()
    _echo(ctx, {"version": value})


@app.command()
@_handle_errors
def hardware_version(ctx: typer.Context) -> None:
    """Get hardware version."""
    value = _get_client(ctx).get_hardware_version()
    _echo(ctx, {"version": value})


# ------------------------------------------------------------------
# server
# ------------------------------------------------------------------
@app.command()
def server(
    host: str = typer.Option("127.0.0.1", "--host", help="Bind host."),
    port: int = typer.Option(8000, "--port", help="Bind port."),
    serial_port: Optional[str] = typer.Option(None, "--serial-port", help="Serial port."),
) -> None:
    """Start the HTTP REST server."""
    from smartusbhub_cli.http_server import run_server

    run_server(host=host, port=port, port_name=serial_port)


# ------------------------------------------------------------------
# mcp
# ------------------------------------------------------------------
@app.command(name="mcp")
def mcp_cmd(
    transport: str = typer.Option("stdio", "--transport", help="stdio or sse."),
    host: str = typer.Option("127.0.0.1", "--host", help="SSE bind host."),
    port: int = typer.Option(8001, "--port", help="SSE bind port."),
    serial_port: Optional[str] = typer.Option(None, "--serial-port", help="Serial port."),
) -> None:
    """Start the MCP server."""
    from smartusbhub_cli.mcp_server import run_mcp

    run_mcp(transport=transport, host=host, port=port, serial_port=serial_port)


if __name__ == "__main__":
    app()
