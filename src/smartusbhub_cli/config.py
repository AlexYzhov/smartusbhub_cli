"""Configuration loading and defaults for smartusbhub_cli."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional


DEFAULT_BAUDRATE = 115200
DEFAULT_TIMEOUT = 0.5
DEFAULT_HOST = "127.0.0.1"
DEFAULT_HTTP_PORT = 8000
DEFAULT_MCP_PORT = 8001
DEFAULT_CONFIG_PATH = Path.home() / ".config" / "smartusbhub_cli" / "config.json"


@dataclass
class Config:
    """Runtime configuration for smartusbhub_cli."""

    # Serial settings
    port: Optional[str] = None
    baudrate: int = DEFAULT_BAUDRATE
    timeout: float = DEFAULT_TIMEOUT

    # HTTP server / client settings
    host: str = DEFAULT_HOST
    http_port: int = DEFAULT_HTTP_PORT
    remote_url: Optional[str] = None

    # MCP settings
    mcp_transport: str = "stdio"  # or "sse"
    mcp_port: int = DEFAULT_MCP_PORT
    mcp_host: str = DEFAULT_HOST

    # Output formatting
    human_readable: bool = False

    # Extra config bag for future extensions
    extra: Dict[str, Any] = field(default_factory=dict)

    def is_remote(self) -> bool:
        """Return True if CLI should operate as an HTTP client."""
        return self.remote_url is not None and self.remote_url.strip() != ""

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the configuration to a plain dictionary."""
        return asdict(self)


def _deep_update(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """Recursively update ``base`` with values from ``override``."""
    for key, value in override.items():
        if isinstance(value, dict) and key in base and isinstance(base[key], dict):
            _deep_update(base[key], value)
        else:
            base[key] = value
    return base


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
        # Any unknown keys go into the extra bag.
        for key, value in file_data.items():
            if key not in cfg.to_dict():
                cfg.extra[key] = value

    # Environment variables override the config file.
    if os.getenv("SMARTUSBHUB_PORT"):
        cfg.port = os.getenv("SMARTUSBHUB_PORT")
    if os.getenv("SMARTUSBHUB_REMOTE"):
        cfg.remote_url = os.getenv("SMARTUSBHUB_REMOTE")
    if os.getenv("SMARTUSBHUB_HOST"):
        cfg.host = os.getenv("SMARTUSBHUB_HOST")
    if os.getenv("SMARTUSBHUB_HTTP_PORT"):
        try:
            cfg.http_port = int(os.getenv("SMARTUSBHUB_HTTP_PORT"))
        except ValueError as exc:
            raise RuntimeError("SMARTUSBHUB_HTTP_PORT must be an integer") from exc
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
