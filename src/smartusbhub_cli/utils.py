"""Shared helpers: output formatting, channel parsing, JSON serialization."""

from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from typing import Any, Dict, List, Optional


def channels_to_bitmask(channels: List[int]) -> int:
    """Convert a list of 1-based channel numbers to the device bitmask."""
    mask = 0
    for ch in channels:
        if ch not in (1, 2, 3, 4):
            raise ValueError(f"Invalid channel: {ch}")
        mask |= 1 << (ch - 1)
    return mask


def bitmask_to_channels(mask: int) -> List[int]:
    """Convert a device bitmask to a sorted list of 1-based channel numbers."""
    return [i + 1 for i in range(4) if mask & (1 << i)]


def resolve_channels(
    channels: List[int], all_channels: bool = False, default: Optional[List[int]] = None
) -> List[int]:
    """Resolve a repeated ``--ch`` list and ``--all`` flag into a channel list.

    If ``all_channels`` is True, returns ``[1, 2, 3, 4]``. Otherwise returns the
    unique, sorted channels supplied via ``--ch``. If no channels were supplied,
    ``default`` is returned (defaults to all channels).
    """
    if all_channels:
        return [1, 2, 3, 4]
    unique = sorted(set(channels))
    if not unique:
        return list(default) if default is not None else [1, 2, 3, 4]
    for ch in unique:
        if ch not in (1, 2, 3, 4):
            raise ValueError(f"Invalid channel: {ch}")
    return unique


def _serialize_value(value: Any) -> Any:
    """Normalize values for JSON output."""
    if is_dataclass(value) and not isinstance(value, type):
        return asdict(value)
    if isinstance(value, dict):
        return {str(k): _serialize_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_serialize_value(v) for v in value]
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def format_output(
    data: Any,
    human_readable: bool = False,
    success: bool = True,
    error: Optional[str] = None,
) -> str:
    """Format a command result for stdout."""
    payload: Dict[str, Any] = {"success": success}
    if data is not None:
        payload["data"] = _serialize_value(data)
    if error:
        payload["error"] = error
    if human_readable:
        return _human_format(payload)
    return json.dumps(payload, indent=2, default=str)


def _human_format(payload: Dict[str, Any]) -> str:
    """Render the JSON envelope in a compact human-readable form."""
    lines: List[str] = []
    success = payload.get("success")
    lines.append(f"Success: {success}")
    data = payload.get("data")
    if data is not None:
        lines.append(_human_value(data, indent=0))
    error = payload.get("error")
    if error:
        lines.append(f"Error: {error}")
    return "\n".join(lines)


def _human_value(value: Any, indent: int = 0) -> str:
    """Recursively format a value for human-readable output."""
    prefix = "  " * indent
    if isinstance(value, dict):
        parts = []
        for k, v in value.items():
            if isinstance(v, (dict, list)):
                parts.append(f"{prefix}{k}:")
                parts.append(_human_value(v, indent + 1))
            else:
                parts.append(f"{prefix}{k}: {_human_scalar(v)}")
        return "\n".join(parts)
    if isinstance(value, list):
        parts = []
        for item in value:
            parts.append(_human_value(item, indent + 1))
        return "\n".join(parts)
    return f"{prefix}{_human_scalar(value)}"


def _human_scalar(value: Any) -> str:
    """Format a scalar value for human-readable output."""
    if isinstance(value, bool):
        return "on" if value else "off"
    if isinstance(value, float):
        return f"{value:.3f}"
    return str(value)


class OutputFormatter:
    """Stateful formatter used by CLI / server to emit responses."""

    def __init__(self, human_readable: bool = False) -> None:
        self.human_readable = human_readable

    def ok(self, data: Any) -> str:
        """Format a successful response."""
        return format_output(data, human_readable=self.human_readable, success=True)

    def fail(self, message: str) -> str:
        """Format an error response."""
        return format_output(
            None, human_readable=self.human_readable, success=False, error=message
        )
