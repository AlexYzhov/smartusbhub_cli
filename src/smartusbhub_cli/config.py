"""Configuration loading and defaults for smartusbhub_cli."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Optional


DEFAULT_BAUDRATE = 115200
DEFAULT_TIMEOUT = 0.5
DEFAULT_HOST = "127.0.0.1"          # Default for client-mode connections
DEFAULT_BIND_HOST = "0.0.0.0"       # Default for server/MCP bind address
DEFAULT_HTTP_PORT = 8000
DEFAULT_MCP_PORT = 8001
DEFAULT_DEVICE = "/dev/ttyACM0"
DEFAULT_CONFIG_PATH = Path.home() / ".config" / "smartusbhub_cli.json"


@dataclass
class Config:
    """Runtime configuration for smartusbhub_cli."""

    # Serial settings
    device: Optional[str] = None
    baudrate: int = DEFAULT_BAUDRATE
    timeout: float = DEFAULT_TIMEOUT

    # Config-driven client mode: if server_host is set, normal subcommands will
    # connect to http://server_host:server_port instead of opening the local
    # serial port.  These values also serve as the default bind address for the
    # explicit ``server`` subcommand.  When server_host is omitted the server
    # subcommand binds to localhost (127.0.0.1).
    server_host: Optional[str] = None
    server_port: Optional[int] = None

    # MCP settings
    mcp_transport: str = "stdio"  # or "sse"
    mcp_port: int = DEFAULT_MCP_PORT
    mcp_host: str = DEFAULT_BIND_HOST

    # Output formatting
    pretty: bool = True

    @property
    def remote_url(self) -> Optional[str]:
        """Return the implied HTTP client URL when server_host is set."""
        if not self.server_host:
            return None
        return f"http://{self.server_host}:{self.server_port or DEFAULT_HTTP_PORT}"

    def is_remote(self) -> bool:
        """Return True if CLI should operate as an HTTP client."""
        return self.server_host is not None and self.server_host.strip() != ""

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the configuration to a plain dictionary."""
        return asdict(self)


def load_config(path: Optional[Path] = None) -> Config:
    """Load configuration from file and environment variables.

    Precedence (highest to lowest):
    1. Explicit ``path`` argument
    2. Environment variables
    3. Configuration file at ``path`` or the default location
    4. Built-in defaults
    """
    cfg = Config()
    target = path or DEFAULT_CONFIG_PATH

    # Load config file if it exists.
    if target.exists():
        try:
            with target.open("r", encoding="utf-8") as f:
                file_data = json.load(f)
        except (json.JSONDecodeError, OSError) as exc:
            raise RuntimeError(f"Failed to load config from {target}: {exc}") from exc

        if not isinstance(file_data, dict):
            raise RuntimeError(f"Config file {target} must contain a JSON object")

        # Map known keys to the dataclass.
        for key in cfg.to_dict().keys():
            if key in file_data:
                setattr(cfg, key, file_data[key])

    # Environment variables override the config file.
    if os.getenv("SMARTUSBHUB_DEVICE"):
        cfg.device = os.getenv("SMARTUSBHUB_DEVICE")
    if os.getenv("SMARTUSBHUB_SERVER_HOST"):
        cfg.server_host = os.getenv("SMARTUSBHUB_SERVER_HOST")
    if os.getenv("SMARTUSBHUB_SERVER_PORT"):
        try:
            cfg.server_port = int(os.getenv("SMARTUSBHUB_SERVER_PORT"))
        except ValueError as exc:
            raise RuntimeError("SMARTUSBHUB_SERVER_PORT must be an integer") from exc
    if os.getenv("SMARTUSBHUB_MCP_PORT"):
        try:
            cfg.mcp_port = int(os.getenv("SMARTUSBHUB_MCP_PORT"))
        except ValueError as exc:
            raise RuntimeError("SMARTUSBHUB_MCP_PORT must be an integer") from exc
    if os.getenv("SMARTUSBHUB_BAUDRATE"):
        try:
            cfg.baudrate = int(os.getenv("SMARTUSBHUB_BAUDRATE"))
        except ValueError as exc:
            raise RuntimeError("SMARTUSBHUB_BAUDRATE must be an integer") from exc
    if os.getenv("SMARTUSBHUB_TIMEOUT"):
        try:
            cfg.timeout = float(os.getenv("SMARTUSBHUB_TIMEOUT"))
        except ValueError as exc:
            raise RuntimeError("SMARTUSBHUB_TIMEOUT must be a number") from exc

    return cfg


def save_config(cfg: Config, path: Optional[Path] = None) -> None:
    """Persist configuration to disk."""
    target = path or DEFAULT_CONFIG_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as f:
        json.dump(cfg.to_dict(), f, indent=2)
