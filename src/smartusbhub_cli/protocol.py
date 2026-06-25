"""Low-level and high-level protocol interface for SmartUSBHub.

This module wraps the existing ``smartusbhub`` library (``SmartUSBHub`` class)
with a thin stateless facade that is easy to use from CLI, HTTP, and MCP modes.
"""

from __future__ import annotations

import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Type

import serial

# Make the upstream package importable when running from the workspace layout.
# The upstream ``smartusbhub`` package is expected to live next to this project.
_UPSTREAM_DIR = Path(__file__).resolve().parents[3] / "smartusbhub"
if _UPSTREAM_DIR.exists() and str(_UPSTREAM_DIR.parent) not in sys.path:
    sys.path.insert(0, str(_UPSTREAM_DIR.parent))

SmartUSBHub: Optional[Type] = None


def _ensure_upstream_imported() -> Type:
    """Lazy import of the upstream ``SmartUSBHub`` class.

    Importing lazily allows unit tests to patch this module's ``SmartUSBHub``
    reference before any real serial hardware is touched, and lets the CLI run
    ``--help`` without requiring the upstream package to be installed.
    """
    global SmartUSBHub
    if SmartUSBHub is None:
        # The upstream package does not re-export SmartUSBHub from its
        # ``__init__.py``, so we import the class from the submodule directly.
        from smartusbhub.smartusbhub import SmartUSBHub as _SmartUSBHub

        SmartUSBHub = _SmartUSBHub
    return SmartUSBHub


@dataclass
class HubState:
    """Snapshot of hub state returned by ``get_device_info``."""

    id: Optional[str] = None
    address: Optional[int] = None
    hardware_version: Optional[str] = None
    firmware_version: Optional[str] = None
    operate_mode: Optional[str] = None
    auto_restore: Optional[bool] = None
    button_control: Optional[bool] = None
    channel_power: Dict[int, bool] = field(default_factory=dict)
    channel_dataline: Dict[int, bool] = field(default_factory=dict)
    channel_voltage: Dict[int, float] = field(default_factory=dict)
    channel_current: Dict[int, float] = field(default_factory=dict)
    default_power: Dict[int, Dict[str, bool]] = field(default_factory=dict)
    default_dataline: Dict[int, Dict[str, bool]] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


class HubError(Exception):
    """Base exception for hub protocol errors."""


class HubNotFoundError(HubError):
    """Raised when no SmartUSBHub is detected or the serial port is unavailable."""


class HubTimeoutError(HubError):
    """Raised when the device does not respond in time."""


class HubProtocol:
    """Facade over the SmartUSBHub serial protocol."""

    def __init__(self, port: str, baudrate: int = 115200, timeout: float = 0.5) -> None:
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self._hub: Optional[SmartUSBHub] = None
        self._closed = False

    @staticmethod
    def scan_ports() -> List[str]:
        """Return a list of serial port names that look like a SmartUSBHub."""
        return _ensure_upstream_imported().scan_available_ports()

    @classmethod
    def scan_and_connect(cls) -> Optional["HubProtocol"]:
        """Scan for a hub and return a connected ``HubProtocol``."""
        try:
            hub = _ensure_upstream_imported().scan_and_connect()
        except Exception as exc:
            raise HubNotFoundError(f"No SmartUSBHub found: {exc}") from exc
        if hub is None:
            return None
        return cls(hub.port)

    @property
    def hub(self):
        """Lazy access to the underlying ``SmartUSBHub`` instance."""
        if self._closed:
            raise HubNotFoundError("Hub connection is closed")
        if self._hub is None:
            try:
                self._hub = _ensure_upstream_imported()(self.port)
            except serial.SerialException as exc:
                raise HubNotFoundError(
                    f"Could not open serial port {self.port}: {exc}"
                ) from exc
            except Exception as exc:
                raise HubError(f"Failed to connect to hub on {self.port}: {exc}") from exc
        return self._hub

    def close(self) -> None:
        """Close the serial connection."""
        self._closed = True
        if self._hub is not None:
            try:
                self._hub.disconnect()
            except Exception:
                pass
            self._hub = None

    def _check_ack(self, ok: bool, operation: str) -> None:
        if not ok:
            raise HubTimeoutError(f"Timeout waiting for {operation} ACK")

    def _check_value(self, value: Optional[object], operation: str) -> object:
        if value is None:
            raise HubTimeoutError(f"Timeout reading {operation}")
        return value

    # ------------------------------------------------------------------
    # Power
    # ------------------------------------------------------------------
    def set_power(self, channels: List[int], state: bool) -> Dict[int, bool]:
        """Turn power ON/OFF for the given channels."""
        self._check_ack(
            self.hub.set_channel_power(*channels, state=int(state)),
            "set channel power",
        )
        return self.get_power(channels)

    def get_power(self, channels: List[int]) -> Dict[int, bool]:
        """Get power status for the given channels."""
        result = self.hub.get_channel_power_status(*channels)
        self._check_value(result, "channel power status")
        if isinstance(result, dict):
            return {ch: bool(result.get(ch, False)) for ch in channels}
        # Single channel returns an int/bool directly.
        return {channels[0]: bool(result)}

    def set_interlock(self, channel: int) -> bool:
        """Set interlock on a single channel."""
        # channel=0 is used by the CLI to mean "all off" per the upstream API.
        target: Optional[int] = channel if channel != 0 else None
        self._check_ack(
            self.hub.set_channel_power_interlock(target),
            "set channel power interlock",
        )
        return True

    # ------------------------------------------------------------------
    # Dataline
    # ------------------------------------------------------------------
    def set_dataline(self, channels: List[int], state: bool) -> Dict[int, bool]:
        """Connect/disconnect USB data lines for the given channels."""
        self._check_ack(
            self.hub.set_channel_dataline(*channels, state=int(state)),
            "set channel dataline",
        )
        return self.get_dataline(channels)

    def get_dataline(self, channels: List[int]) -> Dict[int, bool]:
        """Get data-line connection status for the given channels."""
        result = self.hub.get_channel_dataline_status(*channels)
        self._check_value(result, "channel dataline status")
        return {ch: bool(result.get(ch, False)) for ch in channels}

    # ------------------------------------------------------------------
    # Measurements
    # ------------------------------------------------------------------
    def get_voltage(self, channel: int) -> float:
        """Return voltage reading for a single channel (volts)."""
        mv = self.hub.get_channel_voltage(channel)
        self._check_value(mv, f"channel {channel} voltage")
        return float(mv) / 1000.0

    def get_current(self, channel: int) -> float:
        """Return current reading for a single channel (amps)."""
        ma = self.hub.get_channel_current(channel)
        self._check_value(ma, f"channel {channel} current")
        return float(ma) / 1000.0

    # ------------------------------------------------------------------
    # Config
    # ------------------------------------------------------------------
    def set_default_power(
        self, channels: List[int], enable: bool, state: Optional[bool] = None
    ) -> Dict[int, Dict[str, bool]]:
        """Set default power status for the given channels."""
        status = int(state) if state is not None else 0
        self._check_ack(
            self.hub.set_default_power_status(
                *channels, enable=int(enable), status=status
            ),
            "set default power status",
        )
        return self.get_default_power(channels)

    def get_default_power(self, channels: List[int]) -> Dict[int, Dict[str, bool]]:
        """Get default power status for the given channels."""
        result = self.hub.get_default_power_status(*channels)
        self._check_value(result, "default power status")
        return {
            ch: {"enabled": bool(v["enabled"]), "value": bool(v["value"])}
            for ch, v in result.items()
            if ch in channels
        }

    def set_default_dataline(
        self, channels: List[int], enable: bool, state: Optional[bool] = None
    ) -> Dict[int, Dict[str, bool]]:
        """Set default dataline status for the given channels."""
        status = int(state) if state is not None else 0
        self._check_ack(
            self.hub.set_default_dataline_status(
                *channels, enable=int(enable), status=status
            ),
            "set default dataline status",
        )
        return self.get_default_dataline(channels)

    def get_default_dataline(self, channels: List[int]) -> Dict[int, Dict[str, bool]]:
        """Get default dataline status for the given channels."""
        result = self.hub.get_default_dataline_status(*channels)
        self._check_value(result, "default dataline status")
        return {
            ch: {"enabled": bool(v["enabled"]), "value": bool(v["value"])}
            for ch, v in result.items()
            if ch in channels
        }

    def set_auto_restore(self, enable: bool) -> bool:
        """Enable or disable auto restore."""
        self._check_ack(self.hub.set_auto_restore(enable), "set auto restore")
        return enable

    def get_auto_restore(self) -> bool:
        """Return auto restore status."""
        value = self.hub.get_auto_restore_status()
        self._check_value(value, "auto restore status")
        return bool(value)

    def set_button_control(self, enable: bool) -> bool:
        """Enable or disable button control."""
        self._check_ack(self.hub.set_button_control(enable), "set button control")
        return enable

    def get_button_control(self) -> bool:
        """Return button control status."""
        value = self.hub.get_button_control_status()
        self._check_value(value, "button control status")
        return bool(value)

    def set_operate_mode(self, mode: str) -> str:
        """Set operate mode to ``normal`` or ``interlock``."""
        mode_code = self._mode_to_code(mode)
        self._check_ack(self.hub.set_operate_mode(mode_code), "set operate mode")
        return mode

    def get_operate_mode(self) -> str:
        """Return current operate mode."""
        value = self.hub.get_operate_mode()
        self._check_value(value, "operate mode")
        return self._code_to_mode(int(value))

    @staticmethod
    def _mode_to_code(mode: str) -> int:
        mode = mode.lower()
        if mode in ("normal", "0"):
            return 0
        if mode in ("interlock", "1"):
            return 1
        raise ValueError(f"Invalid operate mode: {mode}")

    @staticmethod
    def _code_to_mode(code: int) -> str:
        if code == 0:
            return "normal"
        if code == 1:
            return "interlock"
        return f"unknown({code})"

    def set_device_address(self, address: int) -> int:
        """Set the 16-bit device address."""
        if not (0 <= address <= 0xFFFF):
            raise ValueError("Address must be between 0x0000 and 0xFFFF")
        self._check_ack(self.hub.set_device_address(address), "set device address")
        return address

    def get_device_address(self) -> int:
        """Return the current 16-bit device address."""
        value = self.hub.get_device_address()
        self._check_value(value, "device address")
        return int(value)

    def factory_reset(self) -> bool:
        """Perform a factory reset."""
        self._check_ack(self.hub.factory_reset(), "factory reset")
        return True

    def get_firmware_version(self) -> str:
        """Return firmware version string."""
        value = self.hub.get_firmware_version()
        self._check_value(value, "firmware version")
        return f"V1.{value}"

    def get_hardware_version(self) -> str:
        """Return hardware version string."""
        value = self.hub.get_hardware_version()
        self._check_value(value, "hardware version")
        return f"V1.{value}"

    def get_device_info(self) -> HubState:
        """Return a full snapshot of the device state."""
        info = self.hub.get_device_info()
        self._check_value(info, "device info")
        state = HubState(
            id=info.get("id"),
            address=info.get("address"),
            hardware_version=f"V1.{info['hardware_version']}"
            if info.get("hardware_version") is not None
            else None,
            firmware_version=f"V1.{info['firmware_version']}"
            if info.get("firmware_version") is not None
            else None,
            operate_mode=info.get("operate_mode"),
            auto_restore=self._to_bool(info.get("auto_restore")),
            button_control=self._to_bool(info.get("button_control_status")),
        )
        state.channel_power = self.get_power([1, 2, 3, 4])
        state.channel_dataline = self.get_dataline([1, 2, 3, 4])
        state.channel_voltage = {ch: self.get_voltage(ch) for ch in range(1, 5)}
        state.channel_current = {ch: self.get_current(ch) for ch in range(1, 5)}
        state.default_power = self.get_default_power([1, 2, 3, 4])
        state.default_dataline = self.get_default_dataline([1, 2, 3, 4])
        return state

    @staticmethod
    def _to_bool(value: Optional[object]) -> Optional[bool]:
        if value is None:
            return None
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.lower() in ("enabled", "true", "1", "on", "yes")
        return bool(value)
