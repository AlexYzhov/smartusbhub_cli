"""Shared helpers: output formatting, channel parsing, JSON serialization."""

from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from typing import Any, Dict, List, Optional


# Help text shared by every Typer ``--ch`` option.
CHANNEL_OPTION_HELP = (
    "Channel number(s) to select. Repeat --ch for multiple channels "
    "(e.g. --ch 1 --ch 3) or use --all."
)

# Help text shared by every Typer ``--all`` option.
ALL_CHANNELS_HELP = "Select all four channels (1-4)."


def format_channel_error(value: Any) -> str:
    """Build a consistent, user-friendly error for invalid channel inputs."""
    return (
        f"Invalid channel '{value}'. "
        "Channels must be integers from 1 to 4. "
        "Use --ch N (repeatable), positional arguments, or --all."
    )


def validate_interlock_channel(value: Any) -> int:
    """Validate an interlock channel argument (0 for all-off, or 1-4)."""
    try:
        ch = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"Invalid channel '{value}'. "
            "Channel must be 0 (all-off) or an integer from 1 to 4."
        ) from exc
    if ch not in (0, 1, 2, 3, 4):
        raise ValueError(
            f"Invalid channel '{value}'. "
            "Channel must be 0 (all-off) or an integer from 1 to 4."
        )
    return ch


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
            raise ValueError(format_channel_error(ch))
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
    success: bool = True,
    error: Optional[str] = None,
    pretty: bool = False,
) -> str:
    """Format a command result for stdout."""
    payload: Dict[str, Any] = {"success": success}
    if data is not None:
        payload["data"] = _serialize_value(data)
    if error:
        payload["error"] = error
    if pretty:
        return _pretty_format_payload(payload)
    return json.dumps(payload, default=str)


# ---------------------------------------------------------------------------
# lsusb / lspci style pretty formatter
# ---------------------------------------------------------------------------


def _pretty_format_payload(payload: Dict[str, Any]) -> str:
    """Render the full response envelope like lsusb/lspci."""
    lines: List[str] = []
    success = payload.get("success")
    lines.append(f"Status: {'OK' if success else 'FAILED'}")

    error = payload.get("error")
    if error:
        lines.append(f"Error: {error}")

    data = payload.get("data")
    if data is not None:
        lines.append(_pretty_format(data))

    return "\n".join(lines)



def _pretty_format(value: Any, title: Optional[str] = None, indent: int = 0) -> str:
    """Render a value in a structured, lsusb-like text format."""
    prefix = "  " * indent
    lines: List[str] = []

    if isinstance(value, dict):
        # Section title
        if title:
            lines.append(f"{prefix}{title}")

        # Special case: {"channel": n, "voltage": x} / {"channel": n, "current": x}
        if "channel" in value and len(value) == 2:
            channel = value["channel"]
            key = [k for k in value if k != "channel"][0]
            unit = _unit_for(key)
            lines.append(
                f"{prefix}  Channel {channel}: {_pretty_scalar(value[key])}{unit}"
            )
            return "\n".join(lines)

        # Special case: {"version": ...} inline
        if "version" in value and len(value) == 1:
            lines.append(f"{prefix}  Version: {_pretty_scalar(value['version'])}")
            return "\n".join(lines)

        # Special case: {"enabled": bool}
        if "enabled" in value and len(value) == 1:
            lines.append(f"{prefix}  Enabled: {_pretty_scalar(value['enabled'])}")
            return "\n".join(lines)

        # Special case: {"mode": str}
        if "mode" in value and len(value) == 1:
            lines.append(f"{prefix}  Mode: {_pretty_scalar(value['mode'])}")
            return "\n".join(lines)

        # Special case: {"address": int}
        if "address" in value and len(value) == 1:
            addr = value["address"]
            lines.append(f"{prefix}  Address: {_pretty_scalar(addr)}")
            return "\n".join(lines)

        # Special case: {"reset": bool}
        if "reset" in value and len(value) == 1:
            lines.append(f"{prefix}  Reset: {_pretty_scalar(value['reset'])}")
            return "\n".join(lines)

        # Special case: {"interlock": bool, "channel": int}
        if "interlock" in value and "channel" in value and len(value) == 2:
            lines.append(
                f"{prefix}  Channel {value['channel']}: "
                f"{'interlocked' if value['interlock'] else 'not interlocked'}"
            )
            return "\n".join(lines)

        # Keys look like channel numbers -> channel list
        if value and all(str(k).isdigit() for k in value.keys()):
            for ch in sorted(int(k) for k in value.keys()):
                v = value[str(ch)]
                if isinstance(v, dict) and "enabled" in v and "value" in v:
                    # For default power/dataline just show the on/off value;
                    # the separate enabled/disabled flag reads like an opposite.
                    lines.append(
                        f"{prefix}  Channel {ch}: {_pretty_scalar(v['value'])}"
                    )
                elif isinstance(v, dict):
                    lines.append(f"{prefix}  Channel {ch}:")
                    for sub_k, sub_v in v.items():
                        if (
                            isinstance(sub_v, dict)
                            and "enabled" in sub_v
                            and "value" in sub_v
                        ):
                            lines.append(
                                f"{prefix}    {_label(sub_k)}: "
                                f"{_pretty_scalar(sub_v['value'])}"
                            )
                        else:
                            unit = _unit_for(sub_k)
                            lines.append(
                                f"{prefix}    {_label(sub_k)}: "
                                f"{_pretty_scalar(sub_v)}{unit}"
                            )
                else:
                    unit = _unit_for(title or "")
                    lines.append(
                        f"{prefix}  Channel {ch}: {_pretty_scalar(v)}{unit}"
                    )
            return "\n".join(lines)

        # Generic dict: render key-value pairs, recurse for nested values
        for k, v in value.items():
            if isinstance(v, (dict, list)):
                lines.append(_pretty_format(v, title=_title_case(k), indent=indent + 1))
            else:
                label = _label(k)
                unit = _unit_for(k)
                lines.append(f"{prefix}  {label}: {_pretty_scalar(v)}{unit}")

        return "\n".join(lines)

    if isinstance(value, list):
        if title:
            lines.append(f"{prefix}{title}")
        for item in value:
            rendered = _pretty_format(item, indent=indent + 1)
            if rendered:
                lines.append(rendered)
        return "\n".join(lines)

    scalar = _pretty_scalar(value)
    if title:
        unit = _unit_for(title)
        lines.append(f"{prefix}{title}: {scalar}{unit}")
    else:
        lines.append(f"{prefix}{scalar}")
    return "\n".join(lines)



def _pretty_scalar(value: Any) -> str:
    """Format a scalar for pretty output."""
    if isinstance(value, bool):
        return "on" if value else "off"
    if isinstance(value, float):
        return f"{value:.3f}"
    if isinstance(value, int) and 0 <= value <= 0xFFFF:
        # Show small ints as-is; hex formatting is left to callers if needed.
        return str(value)
    return str(value)



def _title_case(key: str) -> str:
    """Convert a snake_case key to a Title Case section name."""
    return " ".join(part.capitalize() for part in key.replace("_", " ").split())



def _label(key: str) -> str:
    """Convert a snake_case key to a label."""
    return " ".join(part.capitalize() for part in key.replace("_", " ").split())



def _unit_for(key: str) -> str:
    """Return an optional unit suffix for known measurement keys."""
    k = key.lower()
    if "voltage" in k:
        return " V"
    if "current" in k:
        return " A"
    return ""



class OutputFormatter:
    """Stateful formatter used by CLI / server to emit responses."""

    def __init__(self, pretty: bool = False) -> None:
        self.pretty = pretty

    def ok(self, data: Any) -> str:
        """Format a successful response."""
        return format_output(
            data,
            success=True,
            pretty=self.pretty,
        )

    def fail(self, message: str) -> str:
        """Format an error response."""
        return format_output(
            None,
            success=False,
            error=message,
            pretty=self.pretty,
        )
