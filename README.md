# smartusbhub_cli

CLI, HTTP REST server, and MCP server for the SmartUSBHub.

## Features

- **Self-contained**: implements the SmartUSBHub serial protocol natively on top of `pyserial`, with no dependency on the upstream `smartusbhub` package or `colorlog`.
- **Local CLI**: control the hub directly over USB-CDC serial. Pretty output is on by default.
- **HTTP server**: expose the hub as a compact JSON REST API on a Linux host attached to the device.
- **HTTP client mode**: run the same CLI commands against a remote `smartusbhub_cli` HTTP server. Pretty output is on by default.
- **MCP server**: expose the hub as MCP tools so AI agents can control it via `stdio` or SSE. Returns compact JSON.
- Cross-platform ARM64 / x86_64 Linux single-file executable (shiv zipapp).
- Standard Python wheel distribution.
- One-shot execution with `uvx`.

## Installation

### From source

```bash
cd smartusbhub_cli
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

### From wheel

Pre-built wheels are attached to GitHub Releases. Install with pip:

```bash
pip install smartusbhub_cli-*.whl
```

Or use [uv](https://docs.astral.sh/uv/) for a self-contained tool install:

```bash
uv tool install smartusbhub_cli-*.whl
```

Run directly from a wheel without installing (via `uvx`):

```bash
uvx smartusbhub_cli-*.whl
# or, once published to a package index:
uvx smartusbhub-cli
```

### Build artifacts

To build the single-file executable (shiv zipapp), wheel and sdist locally:

```bash
# Host architecture only (default)
./scripts/build.sh

# Also attempt cross-arch build via Docker (requires Docker/QEMU)
./scripts/build.sh --multi-arch

# outputs:
#   dist/smartusbhub-linux-x86_64   # shiv zipapp, requires Python >=3.10
#   dist/smartusbhub-linux-aarch64  # when --multi-arch succeeds
#   dist/smartusbhub_cli-*.whl
#   dist/smartusbhub_cli-*.tar.gz
```

## Quick start

### Local CLI

```bash
# Auto-scan and connect
smartusbhub info

# Specify a serial device
smartusbhub --device /dev/ttyACM0 power on --ch 1

# Pretty output is the default in local/remote CLI mode (lsusb/lspci style)
smartusbhub --device /dev/ttyACM0 power status --all

# Compact JSON for piping to jq or other tools
smartusbhub --device /dev/ttyACM0 --no-pretty power status --ch 1 | jq '.data."1"'
```

> **Global options position:** options such as `--device`, `--remote` and
> `--pretty/--no-pretty` must be placed **before** the subcommand, e.g.
> `smartusbhub --no-pretty info`. `smartusbhub info --no-pretty` is not
> supported by Typer/Click.

### Channel selection

Commands that act on channels accept channel numbers as **positional arguments**,
as repeated `--ch` flags, and/or `--all`:

```bash
smartusbhub power on 1 3
smartusbhub power on --ch 1 --ch 3
smartusbhub power on --all
smartusbhub voltage 1 3
smartusbhub voltage --all
smartusbhub current 4
```

`interlock` takes a single positional channel (`0` = all-off, `1-4` = single channel).

Use `<command> --help` or `<group> <command> --help` for details, e.g.
`smartusbhub power on --help`.

### Verify delay

State-changing commands read back the affected state immediately after writing.
If the hub needs time to settle, add a delay with the global `--verify-delay`
option (seconds):

```bash
smartusbhub --verify-delay 0.2 power on --ch 1
```

### HTTP server

Run on the host directly attached to the SmartUSBHub (binds to `0.0.0.0` by
default so it accepts connections from any interface):

```bash
# Auto-scan by SmartUSBHub USB VID/PID and bind to 0.0.0.0:8000
smartusbhub server --port 8000

# Or specify the serial device explicitly
smartusbhub server --port 8000 --serial-port /dev/ttyACM0

# Bind to a specific interface only
smartusbhub server --host 127.0.0.1 --port 8000
```

If no device is given and exactly one SmartUSBHub is found, it is used
automatically. If zero or multiple hubs are found, the CLI reports the
situation and asks you to specify `--serial-port` (or set `device` in the
config file).

### HTTP client mode

From another machine on the LAN:

```bash
smartusbhub --remote http://192.168.1.10:8000 power on --ch 1
smartusbhub --remote http://192.168.1.10:8000 voltage 1
```

Or use the explicit `client` subcommand:

```bash
smartusbhub client --host 192.168.1.10 --port 8000 power on --ch 1
smartusbhub client --host 192.168.1.10 --port 8000 voltage 1
```

### MCP server

stdio (for local spawning by an MCP host):

```bash
smartusbhub mcp --transport stdio --serial-port /dev/ttyACM0
```

SSE (for LAN access by AI agents):

```bash
smartusbhub mcp --transport sse --host 0.0.0.0 --port 8001 --serial-port /dev/ttyACM0
```

## Configuration

Create `~/.config/smartusbhub_cli.json` as JSON (the default path is searched
automatically when no `--config` argument is given):

```json
{
  "device": "/dev/ttyACM0",
  "baudrate": 115200,
  "timeout": 0.5,
  "server_host": "0.0.0.0",
  "server_port": 8000,
  "mcp_transport": "stdio",
  "mcp_port": 8001,
  "mcp_host": "0.0.0.0",
  "pretty": true
}
```

- If `server_host` is set, normal subcommands (e.g. `power`, `voltage`, `info`) run in HTTP **client mode** and connect to `http://server_host:server_port`. For a remote client, set `server_host` to the server's real IP; `0.0.0.0` works for local clients.
- If `server_host` is omitted, the CLI works in native serial mode.
- The explicit `server` subcommand binds to `server_host:server_port` by default, or to `0.0.0.0:8000` if neither is configured; `--host` / `--port` override the config.
- The explicit `mcp` subcommand binds to `mcp_host:mcp_port` by default, or to `0.0.0.0:8001`; `--host` / `--port` override the config.
- `device` is used by native serial mode and by the `server`/`mcp` subcommands. The server also auto-scans by USB VID/PID when `device` is not set.

Use the `setup` subcommand to generate a template:

```bash
smartusbhub setup --native
smartusbhub setup --remote --host 0.0.0.0
smartusbhub setup --remote --host 192.168.1.10 --port 8000
smartusbhub setup --mcp --host 0.0.0.0
```

`setup` writes to the default config path (or the path given by `--config`).
For `--remote` and `--mcp`, a currently unused random port is chosen unless
`--port` is provided.

Environment variables override the config file:

- `SMARTUSBHUB_DEVICE`
- `SMARTUSBHUB_SERVER_HOST`
- `SMARTUSBHUB_SERVER_PORT`
- `SMARTUSBHUB_MCP_PORT`
- `SMARTUSBHUB_BAUDRATE`
- `SMARTUSBHUB_TIMEOUT`

## Command reference

See `DESIGN.md` for the full command taxonomy and REST API mapping.

## Development

Run tests:

```bash
pytest
```

Build and test the single-file executable:

```bash
./scripts/build.sh
./dist/smartusbhub-linux-x86_64 --help
```

## License

Apache-2.0
