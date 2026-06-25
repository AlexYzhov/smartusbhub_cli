# SmartUSBHub CLI — Design Document

## 1. Overview

This document describes the architecture for `smartusbhub_cli/`, a new subproject under `/home/alexyzhov/ws/smarthub`. It provides a command-line interface, an HTTP REST server, an HTTP client mode, and an MCP (Model Context Protocol) server for the existing SmartUSBHub hardware.

The upstream Python library lives in `smartusbhub/smartusbhub.py`. It uses a USB-CDC serial port (VID=0x1A86, PID=0xfe0c, 115200 baud) and a 6/7-byte framed binary protocol. This CLI wraps that library so AI agents and operators can control the hub from the LAN without needing a local serial port.

## 2. Goals

- Provide a single `smartusbhub` executable that works in four modes:
  1. **Local CLI** — talk directly to the serial device.
  2. **HTTP server** — expose the hub as a REST API.
  3. **HTTP client** — run the same CLI commands against a remote server.
  4. **MCP server** — expose the hub as MCP tools over `stdio` or SSE.
- JSON output by default; human-readable output with `--human`.
- Configurable via a config file and environment variables.
- Packaged as a single binary for ARM64 and x86_64 Linux via PyInstaller.
- `zipapp` fallback for environments where PyInstaller is not available.

## 3. Module Layout

```
smartusbhub_cli/
├── DESIGN.md                         # This document
├── README.md                         # User-facing quick-start
├── pyproject.toml                    # PEP 621 project metadata
├── smartusbhub_cli.spec              # PyInstaller single-file spec
├── .github/
│   └── workflows/
│       └── build.yml                 # CI: test + PyInstaller for aarch64/x86_64 Linux
├── scripts/
│   └── build.sh                      # Local build helper (PyInstaller / zipapp)
├── src/
│   └── smartusbhub_cli/
│       ├── __init__.py               # Package version
│       ├── __main__.py               # `python -m smartusbhub_cli`
│       ├── py.typed                  # PEP 561 marker
│       ├── config.py                 # Config file / env loading
│       ├── utils.py                  # Output formatting, channel bitmask helpers
│       ├── protocol.py               # Thin facade over smartusbhub.SmartUSBHub
│       ├── client.py                 # HTTP client for remote CLI mode
│       ├── http_server.py            # FastAPI REST server
│       ├── mcp_server.py             # MCP server (stdio + SSE)
│       └── cli.py                    # Typer CLI entry point
└── tests/
    ├── __init__.py
    └── test_placeholder.py           # Skeleton tests
```

## 4. Command Taxonomy

Global options (applicable to every local/remote CLI command):

```
--port, -p      Serial port (e.g. /dev/ttyUSB0 or COM3). Overrides config/env.
--remote, -r    Remote URL (e.g. http://192.168.1.10:8000). Enables client mode.
--human, -h     Emit human-readable output instead of JSON.
--config        Path to config file (default: ~/.config/smartusbhub_cli/config.json).
```

### 4.1 Power

```
smartusbhub power on  --ch 1 [--ch 3] [--all]
smartusbhub power off --ch 1 [--ch 3] [--all]
smartusbhub power status [--ch 1] [--all]
```

### 4.2 Interlock

```
smartusbhub interlock 1
```

### 4.3 Dataline

```
smartusbhub dataline on  --ch 1 [--ch 3] [--all]
smartusbhub dataline off --ch 1 [--ch 3] [--all]
smartusbhub dataline status [--ch 1] [--all]
```

### 4.4 Measurements

```
smartusbhub voltage 1
smartusbhub current 1
```

### 4.5 Configuration

```
smartusbhub config default-power     [--ch 1] [--all] --enable  --on
smartusbhub config default-power     [--ch 1] [--all] --disable
smartusbhub config default-power     --get [--ch 1] [--all]

smartusbhub config default-dataline  [--ch 1] [--all] --enable  --on
smartusbhub config default-dataline  [--ch 1] [--all] --disable
smartusbhub config default-dataline  --get [--ch 1] [--all]

smartusbhub config auto-restore      --enable | --disable | --get
smartusbhub config button-control    --enable | --disable | --get
smartusbhub config operate-mode      --mode normal | --mode interlock | --get
smartusbhub config device-address    --address 0x0001 | --get
smartusbhub config factory-reset
```

### 4.6 Info / Version

```
smartusbhub info
smartusbhub firmware-version
smartusbhub hardware-version
```

### 4.7 Server Commands

```
smartusbhub server --host 0.0.0.0 --port 8000 [--serial-port /dev/ttyUSB0]
smartusbhub mcp --transport stdio [--serial-port /dev/ttyUSB0]
smartusbhub mcp --transport sse --host 0.0.0.0 --port 8001 [--serial-port /dev/ttyUSB0]
```

## 5. REST API Mapping

All endpoints return a JSON envelope:

```json
{
  "success": true,
  "data": { ... },
  "error": null
}
```

| Resource | Method | Path | Body / Query | Maps to |
|---|---|---|---|---|
| Power | POST | `/power` | `{channels: [1,3], state: true}` | `set_channel_power` |
| Power | GET | `/power?channels=1,2,3,4` | query | `get_channel_power_status` |
| Interlock | POST | `/interlock/{channel}` | path | `set_channel_power_interlock` |
| Dataline | POST | `/dataline` | `{channels: [1,3], state: true}` | `set_channel_dataline` |
| Dataline | GET | `/dataline?channels=1,2,3,4` | query | `get_channel_dataline_status` |
| Voltage | GET | `/voltage/{channel}` | path | `get_channel_voltage` |
| Current | GET | `/current/{channel}` | path | `get_channel_current` |
| Default Power | POST | `/config/default-power` | `{channels:[1], enable:true, state:true}` | `set_default_power_status` |
| Default Power | GET | `/config/default-power?channels=1,2,3,4` | query | `get_default_power_status` |
| Default Dataline | POST | `/config/default-dataline` | `{channels:[1], enable:true, state:true}` | `set_default_dataline_status` |
| Default Dataline | GET | `/config/default-dataline?channels=1,2,3,4` | query | `get_default_dataline_status` |
| Auto Restore | POST | `/config/auto-restore` | `{enable: true}` | `set_auto_restore` |
| Auto Restore | GET | `/config/auto-restore` | — | `get_auto_restore_status` |
| Button Control | POST | `/config/button-control` | `{enable: true}` | `set_button_control` |
| Button Control | GET | `/config/button-control` | — | `get_button_control_status` |
| Operate Mode | POST | `/config/operate-mode` | `{mode: "normal"}` | `set_operate_mode` |
| Operate Mode | GET | `/config/operate-mode` | — | `get_operate_mode` |
| Device Address | POST | `/config/device-address` | `{address: 1}` | `set_device_address` |
| Device Address | GET | `/config/device-address` | — | `get_device_address` |
| Factory Reset | POST | `/factory-reset` | — | `factory_reset` |
| Firmware Version | GET | `/version/firmware` | — | `get_firmware_version` |
| Hardware Version | GET | `/version/hardware` | — | `get_hardware_version` |
| Device Info | GET | `/device-info` | — | `get_device_info` |
| Health | GET | `/health` | — | — |

## 6. MCP Tools List

The MCP server registers one tool per operation. Names follow the CLI command names. Arguments and return values are JSON-serializable.

| Tool | Arguments | Description |
|---|---|---|
| `power_on` | `channels: list[int]` | Turn power on for channels |
| `power_off` | `channels: list[int]` | Turn power off for channels |
| `power_status` | `channels: list[int]` | Read channel power states |
| `interlock` | `channel: int` | Set interlock on a channel |
| `dataline_on` | `channels: list[int]` | Connect data lines |
| `dataline_off` | `channels: list[int]` | Disconnect data lines |
| `dataline_status` | `channels: list[int]` | Read data-line states |
| `voltage` | `channel: int` | Read channel voltage |
| `current` | `channel: int` | Read channel current |
| `set_default_power` | `channels, enable, state` | Configure default power |
| `get_default_power` | `channels` | Read default power config |
| `set_default_dataline` | `channels, enable, state` | Configure default dataline |
| `get_default_dataline` | `channels` | Read default dataline config |
| `set_auto_restore` | `enable: bool` | Enable/disable auto restore |
| `get_auto_restore` | — | Read auto restore state |
| `set_button_control` | `enable: bool` | Enable/disable button control |
| `get_button_control` | — | Read button control state |
| `set_operate_mode` | `mode: str` | Set normal/interlock mode |
| `get_operate_mode` | — | Read operate mode |
| `set_device_address` | `address: int` | Set 16-bit device address |
| `get_device_address` | — | Read device address |
| `factory_reset` | — | Factory reset |
| `firmware_version` | — | Read firmware version |
| `hardware_version` | — | Read hardware version |
| `device_info` | — | Full device snapshot |

## 7. Configuration

Default config path: `~/.config/smartusbhub_cli/config.json`.

Supported settings:

```json
{
  "port": "/dev/ttyUSB0",
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

CLI options override environment variables.

## 8. Packaging Plan

### 8.1 PyInstaller single binary

- Spec file: `smartusbhub_cli.spec`.
- Entry point: `src/smartusbhub_cli/__main__.py`.
- Hidden imports include `pydantic`, `fastapi`, `uvicorn`, `mcp`, `typer`, `click`, `serial`.
- Build command: `pyinstaller smartusbhub_cli.spec`.
- Output: `dist/smartusbhub` (single-file console executable).

### 8.2 zipapp fallback

- `python -m zipapp src -m smartusbhub_cli.__main__:app -o dist/smartusbhub.pyz`.
- Requires Python and dependencies to be pre-installed.

### 8.3 GitHub Actions matrix

See `.github/workflows/build.yml`:

1. **test** job — run pytest on Python 3.8, 3.11, and 3.12.
2. **build** job — matrix:
   - `x86_64` runner: `ubuntu-latest`
   - `aarch64` runner: `ubuntu-22.04-arm`
   - Both install deps, run `pyinstaller`, and upload `smartusbhub-linux-<arch>`.
3. **release** job — triggered only on tags `v*`; attaches both binaries to the GitHub release.

## 9. Implementation Notes for Developers

- `protocol.py` should be a thin facade over `smartusbhub.SmartUSBHub` from the existing library. It should translate bitmask-style channel groups into the CLI's list-of-integers convention.
- `http_server.py` and `client.py` must share Pydantic request/response models where practical.
- `cli.py` should instantiate either `HubProtocol` or `HTTPClient` once in the Typer callback and pass the object through `typer.Context`.
- All user-facing output goes through `utils.format_output()` so JSON/human modes are consistent.
- The MCP server should reuse `HubProtocol`; the SSE transport is intended for LAN access, and stdio is intended for local spawning by MCP hosts.
- No authentication is required for the first iteration; if this changes, add it in `http_server.py` and `mcp_server.py` without changing the CLI command taxonomy.

## 10. Protocol Reference (Summary)

The existing SmartUSBHub protocol uses frames starting with `0x55 0x5A`, followed by command, channel bitmask, payload, and checksum. Relevant command bytes:

| Command | Byte | R/W |
|---|---|---|
| Get channel power status | `0x00` | Read |
| Set channel power | `0x01` | Write |
| Set interlock | `0x02` | Write |
| Get channel voltage | `0x03` | Read |
| Get channel current | `0x04` | Read |
| Set channel dataline | `0x05` | Write |
| Set operate mode | `0x06` | Write |
| Get operate mode | `0x07` | Read |
| Get channel dataline status | `0x08` | Read |
| Set button control | `0x09` | Write |
| Get button control status | `0x0A` | Read |
| Set default power status | `0x0B` | Write |
| Get default power status | `0x0C` | Read |
| Set default dataline status | `0x0D` | Write |
| Get default dataline status | `0x0E` | Read |
| Set auto restore | `0x0F` | Write |
| Get auto restore status | `0x10` | Read |
| Set device address | `0x11` | Write |
| Get device address | `0x12` | Read |
| Factory reset | `0xFC` | Write |
| Get firmware version | `0xFD` | Read |
| Get hardware version | `0xFE` | Read |

See `smartusbhub/smartusbhub.py` lines 9-222 for full protocol examples.
