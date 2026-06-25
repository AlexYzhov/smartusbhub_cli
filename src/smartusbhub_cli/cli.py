"""Typer-based CLI for smartusbhub_cli.

Modes:
- Local serial: ``smartusbhub power on --ch 1``
- Remote HTTP client: ``smartusbhub --remote http://IP:PORT power on --ch 1``
- HTTP server: ``smartusbhub server --host 0.0.0.0 --port 8000``
- MCP server: ``smartusbhub mcp --transport stdio``
"""

from __future__ import annotations

import functools
import random
import socket
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, TypeVar, Union
from urllib.parse import urlparse

import typer

from smartusbhub_cli import config as config_module
from smartusbhub_cli.client import HTTPClient, HTTPClientError
from smartusbhub_cli.config import (
    DEFAULT_BIND_HOST,
    DEFAULT_CONFIG_PATH,
    DEFAULT_DEVICE,
    DEFAULT_HOST,
    DEFAULT_HTTP_PORT,
    DEFAULT_MCP_PORT,
    Config,
)
from smartusbhub_cli.protocol import HubError, HubNotFoundError, HubProtocol
from smartusbhub_cli.utils import (
    ALL_CHANNELS_HELP,
    CHANNEL_OPTION_HELP,
    OutputFormatter,
    format_channel_error,
    resolve_channels,
    validate_interlock_channel,
)

app = typer.Typer(
    help=(
        "CLI for SmartUSBHub.\n\n"
        "Global options such as --device, --remote and --pretty/--no-pretty "
        "must be placed before the subcommand "
        "(e.g. smartusbhub --no-pretty info).\n\n"
        "Channel commands accept positional channel numbers, --ch N (repeatable) "
        "and/or --all:\n"
        "  smartusbhub power on 1 3\n"
        "  smartusbhub power on --ch 1 --ch 3\n"
        "  smartusbhub power on --all\n"
        "  smartusbhub voltage 1 3\n\n"
        "Use `smartusbhub <command> --help` or "
        "`smartusbhub <group> <command> --help` for details."
    )
)

# Mirror of the main CLI for explicit client-mode invocation.
client_app = typer.Typer(
    help="Run subcommands against a remote HTTP server.",
    invoke_without_command=True,
)

ClientLike = Union[HubProtocol, HTTPClient]
F = TypeVar("F", bound=Callable[..., Any])


def _parse_int(value: str) -> int:
    """Parse an integer, supporting decimal and ``0x`` hex prefixes."""
    return int(value, 0)


def _resolve_device(
    cfg: Config, serial_port: Optional[str] = None
) -> str:
    """Return the serial device to use, falling back to USB VID/PID scan."""
    device = serial_port or cfg.device
    if device:
        return device

    ports = HubProtocol.scan_ports()
    if len(ports) == 1:
        return ports[0]
    if len(ports) == 0:
        raise HubNotFoundError(
            "No SmartUSBHub detected (VID 0x1A86, PID 0xFE0C). "
            "Connect the hub or specify --device / set device in config."
        )
    raise HubNotFoundError(
        f"Multiple SmartUSBHubs detected: {', '.join(ports)}. "
        "Use --device or set device in config to choose one."
    )


class _LazyHub:
    """Lazy wrapper that instantiates ``HubProtocol`` on first use."""

    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg
        self._hub: Optional[HubProtocol] = None

    def __getattr__(self, name: str) -> Any:
        if self._hub is None:
            device = _resolve_device(self.cfg)
            self._hub = HubProtocol(device, self.cfg.baudrate, self.cfg.timeout)
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


def _merge_channels(
    positional: List[int],
    flags: List[int],
    all_channels: bool,
) -> List[int]:
    """Merge positional channel arguments, --ch flags and --all into a sorted list.

    Raises ``typer.BadParameter`` if any channel is outside 1-4.
    """
    if all_channels:
        return [1, 2, 3, 4]
    combined = list(dict.fromkeys(positional + flags))
    if not combined:
        return [1, 2, 3, 4]
    for ch in combined:
        if ch not in (1, 2, 3, 4):
            raise typer.BadParameter(format_channel_error(ch))
    return sorted(combined)


T = TypeVar("T")


def _verify(
    ctx: typer.Context,
    getter: Callable[[], T],
    predicate: Callable[[T], bool],
    failure_message: str = "Setting verification failed",
) -> T:
    """Read back the state after the configured verify delay and check it.

    On success the read-back state is printed to stdout and returned.
    On failure the state and an error message are printed to stderr and the
    CLI exits with code 1.
    """
    delay = float(ctx.ensure_object(dict).get("verify_delay", 0.0))
    if delay > 0:
        time.sleep(delay)
    actual = getter()
    formatter = _get_formatter(ctx)
    if predicate(actual):
        typer.echo(formatter.ok(actual))
        return actual
    typer.echo(formatter.fail(failure_message), err=True)
    typer.echo(formatter.ok(actual), err=True)
    raise typer.Exit(code=1)


@app.callback()
def main(
    ctx: typer.Context,
    device: Optional[str] = typer.Option(
        None, "--device", "-d", help="Serial device (e.g. /dev/ttyUSB0 or COM3)."
    ),
    remote: Optional[str] = typer.Option(
        None, "--remote", "-r", help="Remote HTTP server URL (enables client mode)."
    ),
    pretty: Optional[bool] = typer.Option(
        None,
        "--pretty/--no-pretty",
        help="Pretty-print output in lsusb/lspci style. Defaults to ON for local/remote CLI.",
    ),
    verify_delay: float = typer.Option(
        0.0,
        "--verify-delay",
        help="Seconds to wait before reading back state after a setting command.",
    ),
    config_file: Optional[str] = typer.Option(
        None, "--config", help="Path to configuration file."
    ),
) -> None:
    """Global CLI options.

    Note: global options such as --device, --remote and --pretty/--no-pretty
    must be placed before the subcommand (e.g. `smartusbhub --no-pretty info`).
    Placing them after the subcommand, like `smartusbhub info --no-pretty`, is
    not supported by Typer/Click and will raise an error.
    """
    cfg_path = Path(config_file) if config_file else None
    cfg = config_module.load_config(cfg_path)

    if remote:
        # Explicit --remote forces client mode.
        parsed = urlparse(remote)
        cfg.server_host = parsed.hostname or DEFAULT_HOST
        cfg.server_port = parsed.port or DEFAULT_HTTP_PORT
    elif device:
        # Explicit --device forces native serial mode, ignoring any config that
        # would put us into client mode.
        cfg.device = device
        cfg.server_host = None
        cfg.server_port = None

    ctx.ensure_object(dict)
    ctx.obj["config"] = cfg
    ctx.obj["config_path"] = cfg_path
    ctx.obj["formatter"] = OutputFormatter(
        pretty=pretty if pretty is not None else cfg.pretty
    )
    ctx.obj["verify_delay"] = verify_delay

    if cfg.is_remote():
        client: ClientLike = HTTPClient(cfg.remote_url)
    else:
        client = _LazyHub(cfg)
    ctx.obj["client"] = client

    @ctx.call_on_close
    def _close_client() -> None:
        if isinstance(client, HTTPClient):
            client.close()
        else:
            client.close()


@client_app.callback()
@_handle_errors
def client_callback(
    ctx: typer.Context,
    host: Optional[str] = typer.Option(None, "--host", help="Remote server host."),
    port: Optional[int] = typer.Option(None, "--port", help="Remote server port."),
) -> None:
    """Explicitly run the following subcommands in HTTP client mode."""
    if ctx.invoked_subcommand is None:
        typer.echo(ctx.get_help())
        raise typer.Exit()

    cfg = ctx.obj["config"]
    if host:
        remote_url = f"http://{host}:{port or DEFAULT_HTTP_PORT}"
    elif cfg.is_remote():
        remote_url = cfg.remote_url
    else:
        raise typer.BadParameter(
            "client mode requires --host/--port or server_host/server_port in config"
        )

    client = HTTPClient(remote_url)
    ctx.obj["client"] = client

    @ctx.call_on_close
    def _close_client() -> None:
        client.close()


# ------------------------------------------------------------------
# power
# ------------------------------------------------------------------
power_app = typer.Typer(help="Control channel power.")
app.add_typer(power_app, name="power")


@power_app.command("on")
@_handle_errors
def power_on(
    ctx: typer.Context,
    channels: List[int] = typer.Argument([], help="Channel number(s) as positional arguments."),
    ch_flags: List[int] = typer.Option([], "--ch", help=CHANNEL_OPTION_HELP),
    all_channels: bool = typer.Option(False, "--all", help=ALL_CHANNELS_HELP),
) -> None:
    """Turn power ON for the selected channels.

    Examples:
        smartusbhub power on 1
        smartusbhub power on 1 3
        smartusbhub power on --ch 1 --ch 3
        smartusbhub power on --all
    """
    chs = _merge_channels(channels, ch_flags, all_channels)
    client = _get_client(ctx)
    client.set_power(chs, True)
    _verify(
        ctx,
        lambda: client.get_power(chs),
        lambda d: all(d[ch] for ch in chs),
        failure_message="Power ON verification failed",
    )


@power_app.command("off")
@_handle_errors
def power_off(
    ctx: typer.Context,
    channels: List[int] = typer.Argument([], help="Channel number(s) as positional arguments."),
    ch_flags: List[int] = typer.Option([], "--ch", help=CHANNEL_OPTION_HELP),
    all_channels: bool = typer.Option(False, "--all", help=ALL_CHANNELS_HELP),
) -> None:
    """Turn power OFF for the selected channels.

    Examples:
        smartusbhub power off 1
        smartusbhub power off 1 3
        smartusbhub power off --ch 1 --ch 3
        smartusbhub power off --all
    """
    chs = _merge_channels(channels, ch_flags, all_channels)
    client = _get_client(ctx)
    client.set_power(chs, False)
    _verify(
        ctx,
        lambda: client.get_power(chs),
        lambda d: all(not d[ch] for ch in chs),
        failure_message="Power OFF verification failed",
    )


@power_app.command("status")
@_handle_errors
def power_status(
    ctx: typer.Context,
    channels: List[int] = typer.Argument([], help="Channel number(s) as positional arguments."),
    ch_flags: List[int] = typer.Option([], "--ch", help=CHANNEL_OPTION_HELP),
    all_channels: bool = typer.Option(False, "--all", help=ALL_CHANNELS_HELP),
) -> None:
    """Get power status.

    Examples:
        smartusbhub power status 1
        smartusbhub power status 1 3
        smartusbhub power status --ch 1 --ch 3
        smartusbhub power status --all
    """
    chs = _merge_channels(channels, ch_flags, all_channels)
    data = _get_client(ctx).get_power(chs)
    _echo(ctx, data)


# ------------------------------------------------------------------
# interlock
# ------------------------------------------------------------------
@app.command()
@_handle_errors
def interlock(
    ctx: typer.Context,
    channel: int = typer.Argument(
        ...,
        help="Channel to interlock. Use 0 for all-off, or 1-4 for a single channel.",
    ),
) -> None:
    """Set interlock mode on a channel.

    Examples:
        smartusbhub interlock 0
        smartusbhub interlock 1
    """
    ch = validate_interlock_channel(channel)
    client = _get_client(ctx)
    client.set_interlock(ch)
    if ch == 0:
        _verify(
            ctx,
            lambda: client.get_power([1, 2, 3, 4]),
            lambda d: all(not v for v in d.values()),
            failure_message="Interlock all-off verification failed",
        )
    else:
        _verify(
            ctx,
            lambda: client.get_power([ch]),
            lambda d: not d[ch],
            failure_message=f"Interlock channel {ch} verification failed",
        )


# ------------------------------------------------------------------
# dataline
# ------------------------------------------------------------------
dataline_app = typer.Typer(help="Control USB data lines.")
app.add_typer(dataline_app, name="dataline")


@dataline_app.command("on")
@_handle_errors
def dataline_on(
    ctx: typer.Context,
    channels: List[int] = typer.Argument([], help="Channel number(s) as positional arguments."),
    ch_flags: List[int] = typer.Option([], "--ch", help=CHANNEL_OPTION_HELP),
    all_channels: bool = typer.Option(False, "--all", help=ALL_CHANNELS_HELP),
) -> None:
    """Connect data lines for selected channels.

    Examples:
        smartusbhub dataline on 1
        smartusbhub dataline on 1 3
        smartusbhub dataline on --ch 1 --ch 3
        smartusbhub dataline on --all
    """
    chs = _merge_channels(channels, ch_flags, all_channels)
    client = _get_client(ctx)
    client.set_dataline(chs, True)
    _verify(
        ctx,
        lambda: client.get_dataline(chs),
        lambda d: all(d[ch] for ch in chs),
        failure_message="Dataline ON verification failed",
    )


@dataline_app.command("off")
@_handle_errors
def dataline_off(
    ctx: typer.Context,
    channels: List[int] = typer.Argument([], help="Channel number(s) as positional arguments."),
    ch_flags: List[int] = typer.Option([], "--ch", help=CHANNEL_OPTION_HELP),
    all_channels: bool = typer.Option(False, "--all", help=ALL_CHANNELS_HELP),
) -> None:
    """Disconnect data lines for selected channels.

    Examples:
        smartusbhub dataline off 1
        smartusbhub dataline off 1 3
        smartusbhub dataline off --ch 1 --ch 3
        smartusbhub dataline off --all
    """
    chs = _merge_channels(channels, ch_flags, all_channels)
    client = _get_client(ctx)
    client.set_dataline(chs, False)
    _verify(
        ctx,
        lambda: client.get_dataline(chs),
        lambda d: all(not d[ch] for ch in chs),
        failure_message="Dataline OFF verification failed",
    )


@dataline_app.command("status")
@_handle_errors
def dataline_status(
    ctx: typer.Context,
    channels: List[int] = typer.Argument([], help="Channel number(s) as positional arguments."),
    ch_flags: List[int] = typer.Option([], "--ch", help=CHANNEL_OPTION_HELP),
    all_channels: bool = typer.Option(False, "--all", help=ALL_CHANNELS_HELP),
) -> None:
    """Get data line status.

    Examples:
        smartusbhub dataline status 1
        smartusbhub dataline status 1 3
        smartusbhub dataline status --ch 1 --ch 3
        smartusbhub dataline status --all
    """
    chs = _merge_channels(channels, ch_flags, all_channels)
    data = _get_client(ctx).get_dataline(chs)
    _echo(ctx, data)


# ------------------------------------------------------------------
# measurements
# ------------------------------------------------------------------
@app.command()
@_handle_errors
def voltage(
    ctx: typer.Context,
    channels: List[int] = typer.Argument([], help="Channel number(s) as positional arguments."),
    ch_flags: List[int] = typer.Option([], "--ch", help=CHANNEL_OPTION_HELP),
    all_channels: bool = typer.Option(False, "--all", help=ALL_CHANNELS_HELP),
) -> None:
    """Read channel voltage.

    Examples:
        smartusbhub voltage 1
        smartusbhub voltage 1 3
        smartusbhub voltage --all
    """
    chs = _merge_channels(channels, ch_flags, all_channels)
    client = _get_client(ctx)
    data = {ch: client.get_voltage(ch) for ch in chs}
    _echo(ctx, data)


@app.command()
@_handle_errors
def current(
    ctx: typer.Context,
    channels: List[int] = typer.Argument([], help="Channel number(s) as positional arguments."),
    ch_flags: List[int] = typer.Option([], "--ch", help=CHANNEL_OPTION_HELP),
    all_channels: bool = typer.Option(False, "--all", help=ALL_CHANNELS_HELP),
) -> None:
    """Read channel current.

    Examples:
        smartusbhub current 1
        smartusbhub current 1 3
        smartusbhub current --all
    """
    chs = _merge_channels(channels, ch_flags, all_channels)
    client = _get_client(ctx)
    data = {ch: client.get_current(ch) for ch in chs}
    _echo(ctx, data)


# ------------------------------------------------------------------
# config
# ------------------------------------------------------------------
config_app = typer.Typer(help="Device configuration.")
app.add_typer(config_app, name="config")


@config_app.command("default-power")
@_handle_errors
def config_default_power(
    ctx: typer.Context,
    channels: List[int] = typer.Argument([], help="Channel number(s) as positional arguments."),
    ch_flags: List[int] = typer.Option([], "--ch", help=CHANNEL_OPTION_HELP),
    all_channels: bool = typer.Option(False, "--all", help=ALL_CHANNELS_HELP),
    enable: bool = typer.Option(True, "--enable/--disable", help="Enable default state."),
    state: Optional[bool] = typer.Option(
        None, "--on/--off", help="Default power state when enabled."
    ),
    get: bool = typer.Option(False, "--get", help="Get instead of set."),
) -> None:
    """Set/get default power status.

    Examples:
        smartusbhub config default-power 1 --enable --on
        smartusbhub config default-power --all --disable
        smartusbhub config default-power --get --all
    """
    chs = _merge_channels(channels, ch_flags, all_channels)
    client = _get_client(ctx)
    if get:
        data = client.get_default_power(chs)
        _echo(ctx, data)
    else:
        client.set_default_power(chs, enable, state)

        def _expected(d: Dict[int, Dict[str, bool]]) -> bool:
            return all(
                d[ch]["enabled"] == enable
                and (state is None or d[ch]["value"] == state)
                for ch in chs
            )

        _verify(
            ctx,
            lambda: client.get_default_power(chs),
            _expected,
            failure_message="Default power verification failed",
        )


@config_app.command("default-dataline")
@_handle_errors
def config_default_dataline(
    ctx: typer.Context,
    channels: List[int] = typer.Argument([], help="Channel number(s) as positional arguments."),
    ch_flags: List[int] = typer.Option([], "--ch", help=CHANNEL_OPTION_HELP),
    all_channels: bool = typer.Option(False, "--all", help=ALL_CHANNELS_HELP),
    enable: bool = typer.Option(True, "--enable/--disable", help="Enable default state."),
    state: Optional[bool] = typer.Option(
        None, "--on/--off", help="Default dataline state when enabled."
    ),
    get: bool = typer.Option(False, "--get", help="Get instead of set."),
) -> None:
    """Set/get default dataline status.

    Examples:
        smartusbhub config default-dataline 1 --enable --on
        smartusbhub config default-dataline --all --disable
        smartusbhub config default-dataline --get --all
    """
    chs = _merge_channels(channels, ch_flags, all_channels)
    client = _get_client(ctx)
    if get:
        data = client.get_default_dataline(chs)
        _echo(ctx, data)
    else:
        client.set_default_dataline(chs, enable, state)

        def _expected(d: Dict[int, Dict[str, bool]]) -> bool:
            return all(
                d[ch]["enabled"] == enable
                and (state is None or d[ch]["value"] == state)
                for ch in chs
            )

        _verify(
            ctx,
            lambda: client.get_default_dataline(chs),
            _expected,
            failure_message="Default dataline verification failed",
        )


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
        _echo(ctx, data)
    else:
        client.set_auto_restore(enable)
        delay = float(ctx.ensure_object(dict).get("verify_delay", 0.0))
        if delay > 0:
            time.sleep(delay)
        actual = client.get_auto_restore()
        if actual != enable:
            formatter = _get_formatter(ctx)
            typer.echo(formatter.fail("Auto-restore verification failed"), err=True)
            typer.echo(formatter.ok({"enabled": actual}), err=True)
            raise typer.Exit(code=1)
        _echo(ctx, {"enabled": actual})


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
        _echo(ctx, data)
    else:
        client.set_button_control(enable)
        delay = float(ctx.ensure_object(dict).get("verify_delay", 0.0))
        if delay > 0:
            time.sleep(delay)
        actual = client.get_button_control()
        if actual != enable:
            formatter = _get_formatter(ctx)
            typer.echo(formatter.fail("Button-control verification failed"), err=True)
            typer.echo(formatter.ok({"enabled": actual}), err=True)
            raise typer.Exit(code=1)
        _echo(ctx, {"enabled": actual})


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
        _echo(ctx, data)
    else:
        client.set_operate_mode(mode)
        delay = float(ctx.ensure_object(dict).get("verify_delay", 0.0))
        if delay > 0:
            time.sleep(delay)
        actual = client.get_operate_mode()
        if actual != mode:
            formatter = _get_formatter(ctx)
            typer.echo(formatter.fail("Operate-mode verification failed"), err=True)
            typer.echo(formatter.ok({"mode": actual}), err=True)
            raise typer.Exit(code=1)
        _echo(ctx, {"mode": actual})


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
        _echo(ctx, data)
    else:
        client.set_device_address(address)
        delay = float(ctx.ensure_object(dict).get("verify_delay", 0.0))
        if delay > 0:
            time.sleep(delay)
        actual = client.get_device_address()
        if actual != address:
            formatter = _get_formatter(ctx)
            typer.echo(formatter.fail("Device-address verification failed"), err=True)
            typer.echo(formatter.ok({"address": actual}), err=True)
            raise typer.Exit(code=1)
        _echo(ctx, {"address": actual})


@config_app.command("factory-reset")
@_handle_errors
def config_factory_reset(ctx: typer.Context) -> None:
    """Perform factory reset."""
    client = _get_client(ctx)
    client.factory_reset()
    delay = float(ctx.ensure_object(dict).get("verify_delay", 0.0))
    if delay > 0:
        time.sleep(delay)
    info = client.get_device_info()
    if hasattr(info, "to_dict"):
        info_dict = info.to_dict()
    else:
        info_dict = info
    power_ok = all(not v for v in info_dict.get("channel_power", {}).values())
    dataline_ok = all(not v for v in info_dict.get("channel_dataline", {}).values())
    if not (power_ok and dataline_ok):
        formatter = _get_formatter(ctx)
        typer.echo(formatter.fail("Factory-reset verification failed"), err=True)
        typer.echo(formatter.ok(info_dict), err=True)
        raise typer.Exit(code=1)
    _echo(ctx, {"reset": True})


# ------------------------------------------------------------------
# info / version
# ------------------------------------------------------------------
def _info_impl(ctx: typer.Context) -> None:
    """Get full device information."""
    data = _get_client(ctx).get_device_info()
    if hasattr(data, "to_dict"):
        data = data.to_dict()
    _echo(ctx, data)


def _int_channel_dict(data: Dict[str, Any], key: str) -> Dict[int, Any]:
    """Return a channel-keyed dict with integer keys.

    Handles both local ``HubState`` (already int keys) and remote JSON
    responses where the keys are strings.
    """
    value = data.get(key, {})
    return {
        int(k) if isinstance(k, str) and k.isdigit() else k: v
        for k, v in value.items()
    }


def _status_impl(ctx: typer.Context) -> None:
    """Get per-channel status.

    Reorganises the device-info snapshot so each channel contains its own
    power, dataline, voltage, current and default settings, while keeping
    the top-level device metadata visible.
    """
    data = _get_client(ctx).get_device_info()
    if hasattr(data, "to_dict"):
        data = data.to_dict()

    channel_power = _int_channel_dict(data, "channel_power")
    channel_dataline = _int_channel_dict(data, "channel_dataline")
    channel_voltage = _int_channel_dict(data, "channel_voltage")
    channel_current = _int_channel_dict(data, "channel_current")
    default_power = _int_channel_dict(data, "default_power")
    default_dataline = _int_channel_dict(data, "default_dataline")

    channels: Dict[int, Dict[str, Any]] = {}
    for ch in range(1, 5):
        channels[ch] = {
            "power": channel_power.get(ch),
            "dataline": channel_dataline.get(ch),
            "voltage": channel_voltage.get(ch),
            "current": channel_current.get(ch),
            "default_power": default_power.get(ch),
            "default_dataline": default_dataline.get(ch),
        }

    status = {
        "device": {
            "id": data.get("id"),
            "address": data.get("address"),
            "hardware_version": data.get("hardware_version"),
            "firmware_version": data.get("firmware_version"),
            "operate_mode": data.get("operate_mode"),
            "auto_restore": data.get("auto_restore"),
            "button_control": data.get("button_control"),
        },
        "channels": channels,
    }
    _echo(ctx, status)


@app.command()
@_handle_errors
def info(ctx: typer.Context) -> None:
    """Get full device information."""
    _info_impl(ctx)


@app.command(name="status")
@_handle_errors
def status(ctx: typer.Context) -> None:
    """Get per-channel status."""
    _status_impl(ctx)


@app.command(name="help", add_help_option=False)
def help_cmd(
    ctx: typer.Context,
    help_flag: bool = typer.Option(
        False, "--help", "-h", help="Show the top-level help message and exit."
    ),
) -> None:
    """Show the top-level help message and exit."""
    # --help is accepted but ignored; this command always prints top-level help.
    _ = help_flag
    parent = ctx.parent
    if parent is None:
        parent = ctx
    typer.echo(parent.get_help())
    raise typer.Exit()


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
@_handle_errors
def server(
    ctx: typer.Context,
    host: Optional[str] = typer.Option(None, "--host", help="Bind host."),
    port: Optional[int] = typer.Option(None, "--port", help="Bind port."),
    serial_port: Optional[str] = typer.Option(None, "--serial-port", help="Serial port."),
) -> None:
    """Start the HTTP REST server.

    Defaults are read from the configuration file (server_host / server_port)
    and can be overridden with --host / --port.
    """
    from smartusbhub_cli.http_server import _server_state, run_server

    cfg = ctx.obj["config"]
    host = host or cfg.server_host or DEFAULT_BIND_HOST
    port = port or cfg.server_port or DEFAULT_HTTP_PORT
    device = _resolve_device(cfg, serial_port)

    # Pre-create the protocol from the same config so the lifespan doesn't
    # reload a different (possibly default) config file.
    try:
        _server_state.protocol = HubProtocol(device, cfg.baudrate, cfg.timeout)
    except HubError:
        _server_state.protocol = None

    run_server(host=host, port=port, port_name=device)


# ------------------------------------------------------------------
# mcp
# ------------------------------------------------------------------
@app.command(name="mcp")
def mcp_cmd(
    transport: str = typer.Option("stdio", "--transport", help="stdio or sse."),
    host: str = typer.Option(DEFAULT_BIND_HOST, "--host", help="SSE bind host."),
    port: int = typer.Option(DEFAULT_MCP_PORT, "--port", help="SSE bind port."),
    serial_port: Optional[str] = typer.Option(None, "--serial-port", help="Serial port."),
) -> None:
    """Start the MCP server."""
    from smartusbhub_cli.mcp_server import run_mcp

    run_mcp(transport=transport, host=host, port=port, serial_port=serial_port)


# ------------------------------------------------------------------
# setup
# ------------------------------------------------------------------
def _find_free_port(
    host: str = DEFAULT_BIND_HOST, min_port: int = 9001, max_port: int = 65535
) -> int:
    """Return an unused TCP port on ``host`` in the range (min_port, max_port]."""
    # Resolve the address family for the requested host.
    addr_info = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    if not addr_info:
        raise ValueError(f"Could not resolve host {host!r}")
    family, _, _, _, sockaddr = addr_info[0]
    bind_addr = sockaddr[0]

    # Start from a random offset to reduce collisions when multiple setups run
    # concurrently, then scan sequentially for the first free port.
    start = random.randint(min_port, max_port)
    for port in range(start, max_port + 1):
        with socket.socket(family, socket.SOCK_STREAM) as sock:
            try:
                sock.bind((bind_addr, port))
                return port
            except OSError:
                pass
    # Wrap around and scan from the bottom up to the starting point.
    for port in range(min_port, start):
        with socket.socket(family, socket.SOCK_STREAM) as sock:
            try:
                sock.bind((bind_addr, port))
                return port
            except OSError:
                pass
    raise RuntimeError(
        f"No free TCP port found in range {min_port}-{max_port} on {host}"
    )


@app.command()
@_handle_errors
def setup(
    ctx: typer.Context,
    native: bool = typer.Option(False, "--native", help="Native serial mode."),
    remote: bool = typer.Option(False, "--remote", help="HTTP server/client mode."),
    mcp: bool = typer.Option(False, "--mcp", help="MCP server mode."),
    host: Optional[str] = typer.Option(None, "--host", help="Host/IP address."),
    port: Optional[int] = typer.Option(None, "--port", help="Port number."),
    device: Optional[str] = typer.Option(None, "--device", help="Serial device path."),
) -> None:
    """Create a configuration file template at the default location.

    Examples:
        smartusbhub setup --native
        smartusbhub setup --remote --host 0.0.0.0
        smartusbhub setup --remote --host 192.168.1.10 --port 8000
        smartusbhub setup --mcp --host 0.0.0.0
    """
    modes = [("native", native), ("remote", remote), ("mcp", mcp)]
    selected = [name for name, flag in modes if flag]
    if len(selected) > 1:
        raise typer.BadParameter(
            "Only one of --native/--remote/--mcp can be used"
        )
    mode = selected[0] if selected else "native"

    cfg = Config()
    target = ctx.obj.get("config_path") or DEFAULT_CONFIG_PATH
    bind_host = host or DEFAULT_BIND_HOST

    cfg.device = device or DEFAULT_DEVICE

    if mode == "remote":
        cfg.server_host = bind_host
        cfg.server_port = port or _find_free_port(bind_host)
    elif mode == "mcp":
        cfg.mcp_host = bind_host
        cfg.mcp_port = port or _find_free_port(bind_host)
        cfg.mcp_transport = "sse"

    config_module.save_config(cfg, target)
    _echo(ctx, {"config": str(target), "mode": mode})


# ------------------------------------------------------------------
# Register the explicit client-mode group (must be done after all commands
# are defined so the same function objects can be reused).
# ------------------------------------------------------------------
app.add_typer(client_app, name="client")
client_app.add_typer(power_app, name="power")
client_app.add_typer(dataline_app, name="dataline")
client_app.add_typer(config_app, name="config")
client_app.command(name="interlock")(interlock)
client_app.command(name="voltage")(voltage)
client_app.command(name="current")(current)
client_app.command(name="info")(info)
client_app.command(name="status")(status)
client_app.command(name="firmware-version")(firmware_version)
client_app.command(name="hardware-version")(hardware_version)


def main() -> None:
    """Console entry point used by the ``smartusbhub`` script and PyInstaller."""
    app()


if __name__ == "__main__":
    main()
