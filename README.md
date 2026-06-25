# smartusbhub_cli

CLI, HTTP REST server, and MCP server for the SmartUSBHub.

## Features

- **Local CLI**: control the hub directly over USB-CDC serial.
- **HTTP server**: expose the hub as a REST API on a Linux host attached to the device.
- **HTTP client mode**: run the same CLI commands against a remote `smartusbhub_cli` HTTP server.
- **MCP server**: expose the hub as MCP tools so AI agents can control it via `stdio` or SSE.
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
./scripts/build.sh
# outputs:
#   dist/smartusbhub-linux-<arch>
#   dist/smartusbhub.pyz
```

## Quick start

### Local CLI

```bash
# Auto-scan and connect
smartusbhub info

# Specify a serial port
smartusbhub --port /dev/ttyACM0 power on --ch 1

# Human-readable output
smartusbhub --human power status --all
```

### HTTP server

Run on the host directly attached to the SmartUSBHub:

```bash
smartusbhub server --host 0.0.0.0 --port 8000 --serial-port /dev/ttyACM0
```

### HTTP client mode

From another machine on the LAN:

```bash
smartusbhub --remote http://192.168.1.10:8000 power on --ch 1
smartusbhub --remote http://192.168.1.10:8000 voltage 1
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

Create `~/.config/smartusbhub_cli/config.json`:

```json
{
  "port": "/dev/ttyACM0",
  "baudrate": 115200,
  "timeout": 0.5,
  "host": "127.0.0.1",
  "http_port": 8000,
  "remote_url": null,
  "mcp_transport": "stdio",
  "mcp_port": 8001,
  "mcp_host": "127.0.0.1",
  "human_readable": false
}
```

Environment variables override the config file:

- `SMARTUSBHUB_PORT`
- `SMARTUSBHUB_REMOTE`
- `SMARTUSBHUB_HOST`
- `SMARTUSBHUB_HTTP_PORT`
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
