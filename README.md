# smartusbhub_cli

CLI, HTTP REST server, and MCP server for the SmartUSBHub.

## Features

- **Self-contained**: implements the SmartUSBHub serial protocol natively on top of `pyserial`, with no dependency on the upstream `smartusbhub` package or `colorlog`.
- **Local CLI**: control the hub directly over USB-CDC serial. Pretty output is on by default.
- **HTTP server**: expose the hub as a compact JSON REST API on a Linux host attached to the device.
- **HTTP client mode**: run the same CLI commands against a remote `smartusbhub_cli` HTTP server. Pretty output is on by default.
- **MCP server**: expose the hub as MCP tools so AI agents can control it via `stdio` or SSE. Returns compact JSON.
- Cross-platform ARM64 / x86_64 Linux binaries via PyInstaller.

## Installation

### From source

```bash
cd smartusbhub_cli
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

### Single binary

Pre-built binaries are attached to GitHub Releases. To build locally:

```bash
# Host architecture only (default)
./scripts/build.sh

# Also attempt cross-arch build via Docker (requires Docker/QEMU)
./scripts/build.sh --multi-arch

# Source the build environment to get SMARTUSBHUB_BIN pointing to the
# host-arch binary (builds it first if necessary)
source ./scripts/build.sh

# outputs:
#   dist/smartusbhub-linux-x86_64
#   dist/smartusbhub-linux-aarch64   # when --multi-arch succeeds
#   dist/smartusbhub.pyz
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

Run on the host directly attached to the SmartUSBHub (binds to localhost by
default):

```bash
# Auto-scan by SmartUSBHub USB VID/PID and bind to localhost:8000
smartusbhub server --port 8000

# Or specify the serial device explicitly
smartusbhub server --port 8000 --serial-port /dev/ttyACM0
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
  "server_host": "127.0.0.1",
  "server_port": 8000,
  "mcp_transport": "stdio",
  "mcp_port": 8001,
  "mcp_host": "127.0.0.1",
  "pretty": true
}
```

- If `server_host` is set, normal subcommands (e.g. `power`, `voltage`, `info`) run in HTTP **client mode** and connect to `http://server_host:server_port`.
- If `server_host` is omitted, the CLI works in native serial mode.
- The explicit `server` subcommand binds to `server_host:server_port` by default, or to `127.0.0.1:8000` if neither is configured; `--host` / `--port` override the config. The same `server_host`/`server_port` can therefore drive both the server and the client from one config file.
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

Build and test the binary:

```bash
./scripts/build.sh
./dist/smartusbhub-linux-x86_64 --help
```

## License

Apache-2.0
