"""Native serial protocol implementation for SmartUSBHub.

This module implements the 6/7-byte framed binary protocol directly on top of
``pyserial``. It does **not** depend on the upstream ``smartusbhub`` package,
which keeps the CLI self-contained and makes the PyInstaller binary truly
standalone.
"""

from __future__ import annotations

import logging
import time
from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional, Tuple

import serial
import serial.tools.list_ports

VID_SMARTUSBHUB = 0x1A86
PID_SMARTUSBHUB = 0xFE0C

HEADER_0 = 0x55
HEADER_1 = 0x5A

BAUDRATE_DEFAULT = 115200
TIMEOUT_DEFAULT = 0.5
VERSION_PREFIX = "V1"

# Command bytes
CMD_GET_CHANNEL_POWER_STATUS = 0x00
CMD_SET_CHANNEL_POWER = 0x01
CMD_SET_CHANNEL_POWER_INTERLOCK = 0x02
CMD_GET_CHANNEL_VOLTAGE = 0x03
CMD_GET_CHANNEL_CURRENT = 0x04
CMD_SET_CHANNEL_DATALINE = 0x05
CMD_SET_OPERATE_MODE = 0x06
CMD_GET_OPERATE_MODE = 0x07
CMD_GET_CHANNEL_DATALINE_STATUS = 0x08
CMD_SET_BUTTON_CONTROL = 0x09
CMD_GET_BUTTON_CONTROL_STATUS = 0x0A
CMD_SET_DEFAULT_POWER_STATUS = 0x0B
CMD_GET_DEFAULT_POWER_STATUS = 0x0C
CMD_SET_DEFAULT_DATALINE_STATUS = 0x0D
CMD_GET_DEFAULT_DATALINE_STATUS = 0x0E
CMD_SET_AUTO_RESTORE = 0x0F
CMD_GET_AUTO_RESTORE_STATUS = 0x10
CMD_SET_DEVICE_ADDRESS = 0x11
CMD_GET_DEVICE_ADDRESS = 0x12
CMD_FACTORY_RESET = 0xFC
CMD_GET_FIRMWARE_VERSION = 0xFD
CMD_GET_HARDWARE_VERSION = 0xFE

CHANNEL_MASK = {1: 0x01, 2: 0x02, 3: 0x04, 4: 0x08}
ALL_CHANNELS_MASK = 0x0F

logger = logging.getLogger(__name__)


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


def _channels_to_mask(channels: List[int]) -> int:
    mask = 0
    for ch in channels:
        if ch not in CHANNEL_MASK:
            raise ValueError(f"Invalid channel: {ch}")
        mask |= CHANNEL_MASK[ch]
    return mask


def _mask_to_channels(mask: int) -> List[int]:
    return [i for i in range(1, 5) if mask & CHANNEL_MASK[i]]


def _build_frame(cmd: int, channel_mask: int, data: Optional[List[int]] = None) -> bytes:
    if data is None:
        data = [0x00]
    payload = [channel_mask] + data
    checksum = (cmd + sum(payload)) & 0xFF
    return bytes([HEADER_0, HEADER_1, cmd] + payload + [checksum])


def _parse_frames(buffer: bytearray) -> Tuple[List[Tuple[int, int, int, List[int]]], int]:
    """Parse as many complete frames as possible from ``buffer``.

    Returns a list of (cmd, channel, value, extra_bytes) tuples and the number
    of bytes consumed from the buffer. For 6-byte frames ``extra_bytes`` is
    empty; for 7-byte frames it contains the two payload bytes.
    """
    results: List[Tuple[int, int, int, List[int]]] = []
    consumed = 0
    while len(buffer) - consumed >= 6:
        start = consumed
        if buffer[start] != HEADER_0 or buffer[start + 1] != HEADER_1:
            consumed += 1
            continue

        cmd = buffer[start + 2]
        channel = buffer[start + 3]

        if cmd in {
            CMD_GET_CHANNEL_VOLTAGE,
            CMD_GET_CHANNEL_CURRENT,
            CMD_SET_DEFAULT_POWER_STATUS,
            CMD_SET_DEFAULT_DATALINE_STATUS,
            CMD_GET_DEFAULT_POWER_STATUS,
            CMD_GET_DEFAULT_DATALINE_STATUS,
        }:
            if len(buffer) - consumed < 7:
                break
            val0 = buffer[start + 4]
            val1 = buffer[start + 5]
            checksum = buffer[start + 6]
            if ((cmd + channel + val0 + val1) & 0xFF) != checksum:
                consumed += 1
                continue
            # Combine the two payload bytes into a single value for symmetry.
            value = (val0 << 8) | val1
            results.append((cmd, channel, value, [val0, val1]))
            consumed += 7
        else:
            value = buffer[start + 4]
            checksum = buffer[start + 5]
            if ((cmd + channel + value) & 0xFF) != checksum:
                consumed += 1
                continue
            results.append((cmd, channel, value, []))
            consumed += 6

    return results, consumed


class HubProtocol:
    """Facade over the SmartUSBHub serial protocol.

    The instance is intentionally stateless regarding the device: it opens the
    serial port on first use and can be closed explicitly. This makes it easy
    to use in short-lived CLI commands and long-running servers alike.
    """

    def __init__(
        self,
        port: str,
        baudrate: int = BAUDRATE_DEFAULT,
        timeout: float = TIMEOUT_DEFAULT,
    ) -> None:
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self._ser: Optional[serial.Serial] = None
        self._closed = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    @staticmethod
    def scan_ports() -> List[str]:
        """Return serial port names that look like a SmartUSBHub."""
        return [
            port_info.device
            for port_info in serial.tools.list_ports.comports()
            if port_info.vid == VID_SMARTUSBHUB and port_info.pid == PID_SMARTUSBHUB
        ]

    @classmethod
    def scan_and_connect(
        cls, baudrate: int = BAUDRATE_DEFAULT, timeout: float = TIMEOUT_DEFAULT
    ) -> Optional["HubProtocol"]:
        """Scan for a hub and return a connected ``HubProtocol``."""
        ports = cls.scan_ports()
        if not ports:
            return None
        return cls(ports[0], baudrate, timeout)

    @property
    def _serial(self) -> serial.Serial:
        if self._closed:
            raise HubNotFoundError("Hub connection is closed")
        if self._ser is None:
            try:
                self._ser = serial.Serial(
                    self.port,
                    self.baudrate,
                    timeout=self.timeout,
                    write_timeout=self.timeout,
                )
                # Some test doubles don't implement reset_input_buffer.
                reset = getattr(self._ser, "reset_input_buffer", None)
                if reset is not None:
                    reset()
            except serial.SerialException as exc:
                raise HubNotFoundError(
                    f"Could not open serial port {self.port}: {exc}"
                ) from exc
        return self._ser

    def close(self) -> None:
        """Close the serial connection."""
        self._closed = True
        if self._ser is not None and self._ser.is_open:
            try:
                self._ser.flush()
                self._ser.close()
            except Exception:
                pass
            self._ser = None

    def __enter__(self) -> "HubProtocol":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # ------------------------------------------------------------------
    # Low-level IO
    # ------------------------------------------------------------------
    def _send(self, frame: bytes) -> None:
        ser = self._serial
        ser.write(frame)
        ser.flush()
        logger.debug("Sent: %s", frame.hex(" "))

    def _receive(
        self,
        expected_cmd: int,
        expected_channels_mask: int = 0,
        timeout: Optional[float] = None,
    ) -> List[Tuple[int, int, int, List[int]]]:
        """Read responses for ``expected_cmd``.

        For most commands the device returns a single frame, so
        ``expected_channels_mask`` defaults to 0 and we return as soon as the
        first matching frame is seen.  Status queries for multiple channels can
        produce one response frame per channel (or one combined frame), in
        which case we keep reading until every requested channel bit has been
        covered.
        """
        deadline = time.monotonic() + (timeout or self.timeout)
        buffer = bytearray()
        matching: List[Tuple[int, int, int, List[int]]] = []
        covered_mask = 0

        while time.monotonic() < deadline:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            ser = self._serial
            ser.timeout = max(remaining, 0.01)
            chunk = ser.read(max(1, ser.in_waiting))
            if chunk:
                buffer.extend(chunk)
                frames, consumed = _parse_frames(buffer)
                buffer[:consumed] = b""
                for cmd, channel, value, extra in frames:
                    if cmd == expected_cmd:
                        matching.append((cmd, channel, value, extra))
                        covered_mask |= channel
                        if expected_channels_mask == 0:
                            return matching
                        if (covered_mask & expected_channels_mask) == expected_channels_mask:
                            return matching
            else:
                time.sleep(0.005)

        if expected_channels_mask and (covered_mask & expected_channels_mask) == expected_channels_mask:
            return matching

        raise HubTimeoutError(
            f"Timeout waiting for response to command 0x{expected_cmd:02X}"
        )

    def _transact(
        self,
        cmd: int,
        channels: List[int],
        data: Optional[List[int]] = None,
        timeout: Optional[float] = None,
    ) -> List[Tuple[int, int, int, List[int]]]:
        """Send a command and return parsed response frames."""
        if cmd == CMD_SET_DEVICE_ADDRESS:
            # Special case: channel byte is MSB, data is LSB.
            channel_mask = channels[0]
            frame_data = data or [0x00]
        else:
            channel_mask = _channels_to_mask(channels) if channels else 0x00
            frame_data = data if data is not None else [0x00]

        frame = _build_frame(cmd, channel_mask, frame_data)
        self._send(frame)

        # Multi-channel status queries may return one frame per channel.
        expected_channels_mask = 0
        if cmd in {
            CMD_GET_CHANNEL_POWER_STATUS,
            CMD_GET_CHANNEL_DATALINE_STATUS,
            CMD_GET_DEFAULT_POWER_STATUS,
            CMD_GET_DEFAULT_DATALINE_STATUS,
        }:
            expected_channels_mask = channel_mask

        return self._receive(cmd, expected_channels_mask, timeout)

    # ------------------------------------------------------------------
    # Power
    # ------------------------------------------------------------------
    def set_power(self, channels: List[int], state: bool) -> bool:
        self._transact(CMD_SET_CHANNEL_POWER, channels, [int(state)])
        return True

    def get_power(self, channels: List[int]) -> Dict[int, bool]:
        frames = self._transact(CMD_GET_CHANNEL_POWER_STATUS, channels)
        result: Dict[int, bool] = {}
        for _cmd, channel_mask, value, _extra in frames:
            for ch in _mask_to_channels(channel_mask):
                result[ch] = bool(value)
        # Ensure every requested channel is present.
        for ch in channels:
            result.setdefault(ch, False)
        return result

    def set_interlock(self, channel: int) -> bool:
        if channel == 0:
            self._transact(CMD_SET_CHANNEL_POWER_INTERLOCK, [], [0x00])
        else:
            self._transact(CMD_SET_CHANNEL_POWER_INTERLOCK, [channel], [0x01])
        return True

    # ------------------------------------------------------------------
    # Dataline
    # ------------------------------------------------------------------
    def set_dataline(self, channels: List[int], state: bool) -> bool:
        self._transact(CMD_SET_CHANNEL_DATALINE, channels, [int(state)])
        return True

    def get_dataline(self, channels: List[int]) -> Dict[int, bool]:
        frames = self._transact(CMD_GET_CHANNEL_DATALINE_STATUS, channels)
        result: Dict[int, bool] = {}
        for _cmd, channel_mask, value, _extra in frames:
            for ch in _mask_to_channels(channel_mask):
                result[ch] = bool(value)
        for ch in channels:
            result.setdefault(ch, False)
        return result

    # ------------------------------------------------------------------
    # Measurements
    # ------------------------------------------------------------------
    def get_voltage(self, channel: int) -> float:
        frames = self._transact(CMD_GET_CHANNEL_VOLTAGE, [channel])
        if not frames:
            raise HubTimeoutError("No voltage response")
        _cmd, _channel, value, _extra = frames[0]
        return float(value) / 1000.0

    def get_current(self, channel: int) -> float:
        frames = self._transact(CMD_GET_CHANNEL_CURRENT, [channel])
        if not frames:
            raise HubTimeoutError("No current response")
        _cmd, _channel, value, _extra = frames[0]
        return float(value) / 1000.0

    # ------------------------------------------------------------------
    # Config
    # ------------------------------------------------------------------
    def set_default_power(
        self, channels: List[int], enable: bool, state: Optional[bool] = None
    ) -> bool:
        status = int(state) if state is not None else 0
        self._transact(CMD_SET_DEFAULT_POWER_STATUS, channels, [int(enable), status])
        return True

    def get_default_power(self, channels: List[int]) -> Dict[int, Dict[str, bool]]:
        frames = self._transact(CMD_GET_DEFAULT_POWER_STATUS, channels, [0x00, 0x00])
        result: Dict[int, Dict[str, bool]] = {}
        for _cmd, channel_mask, _value, extra in frames:
            enable, status = extra[0], extra[1]
            for ch in _mask_to_channels(channel_mask):
                result[ch] = {"enabled": bool(enable), "value": bool(status)}
        for ch in channels:
            result.setdefault(ch, {"enabled": False, "value": False})
        return result

    def set_default_dataline(
        self, channels: List[int], enable: bool, state: Optional[bool] = None
    ) -> bool:
        status = int(state) if state is not None else 0
        self._transact(CMD_SET_DEFAULT_DATALINE_STATUS, channels, [int(enable), status])
        return True

    def get_default_dataline(self, channels: List[int]) -> Dict[int, Dict[str, bool]]:
        frames = self._transact(CMD_GET_DEFAULT_DATALINE_STATUS, channels, [0x00, 0x00])
        result: Dict[int, Dict[str, bool]] = {}
        for _cmd, channel_mask, _value, extra in frames:
            enable, status = extra[0], extra[1]
            for ch in _mask_to_channels(channel_mask):
                result[ch] = {"enabled": bool(enable), "value": bool(status)}
        for ch in channels:
            result.setdefault(ch, {"enabled": False, "value": False})
        return result

    def set_auto_restore(self, enable: bool) -> bool:
        self._transact(CMD_SET_AUTO_RESTORE, [], [int(enable)])
        return enable

    def get_auto_restore(self) -> bool:
        frames = self._transact(CMD_GET_AUTO_RESTORE_STATUS, [], [0x00])
        if not frames:
            raise HubTimeoutError("No auto-restore response")
        return bool(frames[0][2])

    def set_button_control(self, enable: bool) -> bool:
        self._transact(CMD_SET_BUTTON_CONTROL, [], [int(enable)])
        return enable

    def get_button_control(self) -> bool:
        frames = self._transact(CMD_GET_BUTTON_CONTROL_STATUS, [], [0x00])
        if not frames:
            raise HubTimeoutError("No button-control response")
        return bool(frames[0][2])

    def set_operate_mode(self, mode: str) -> str:
        code = self._mode_to_code(mode)
        self._transact(CMD_SET_OPERATE_MODE, [], [code])
        return mode

    def get_operate_mode(self) -> str:
        frames = self._transact(CMD_GET_OPERATE_MODE, [], [0x00])
        if not frames:
            raise HubTimeoutError("No operate-mode response")
        return self._code_to_mode(frames[0][2])

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
        if not (0 <= address <= 0xFFFF):
            raise ValueError("Address must be between 0x0000 and 0xFFFF")
        msb = (address >> 8) & 0xFF
        lsb = address & 0xFF
        self._transact(CMD_SET_DEVICE_ADDRESS, [msb], [lsb])
        return address

    def get_device_address(self) -> int:
        frames = self._transact(CMD_GET_DEVICE_ADDRESS, [], [0x00])
        if not frames:
            raise HubTimeoutError("No device-address response")
        _cmd, channel, value, _extra = frames[0]
        return (int(channel) << 8) | int(value)

    def factory_reset(self) -> bool:
        self._transact(CMD_FACTORY_RESET, [], [0x00])
        return True

    def get_firmware_version(self) -> str:
        frames = self._transact(CMD_GET_FIRMWARE_VERSION, [], [0x00])
        if not frames:
            raise HubTimeoutError("No firmware-version response")
        return f"{VERSION_PREFIX}.{frames[0][2]}"

    def get_hardware_version(self) -> str:
        frames = self._transact(CMD_GET_HARDWARE_VERSION, [], [0x00])
        if not frames:
            raise HubTimeoutError("No hardware-version response")
        return f"{VERSION_PREFIX}.{frames[0][2]}"

    def get_device_info(self) -> HubState:
        info_frames = {
            "hardware": self._transact(CMD_GET_HARDWARE_VERSION, [], [0x00]),
            "firmware": self._transact(CMD_GET_FIRMWARE_VERSION, [], [0x00]),
            "operate_mode": self._transact(CMD_GET_OPERATE_MODE, [], [0x00]),
            "auto_restore": self._transact(CMD_GET_AUTO_RESTORE_STATUS, [], [0x00]),
            "button_control": self._transact(CMD_GET_BUTTON_CONTROL_STATUS, [], [0x00]),
            "device_address": self._transact(CMD_GET_DEVICE_ADDRESS, [], [0x00]),
        }

        state = HubState(
            id=self.port.split("/")[-1],
            address=int(info_frames["device_address"][0][2]),
            hardware_version=f"{VERSION_PREFIX}.{info_frames['hardware'][0][2]}",
            firmware_version=f"{VERSION_PREFIX}.{info_frames['firmware'][0][2]}",
            operate_mode=self._code_to_mode(info_frames["operate_mode"][0][2]),
            auto_restore=bool(info_frames["auto_restore"][0][2]),
            button_control=bool(info_frames["button_control"][0][2]),
        )
        state.channel_power = self.get_power([1, 2, 3, 4])
        state.channel_dataline = self.get_dataline([1, 2, 3, 4])
        state.channel_voltage = {ch: self.get_voltage(ch) for ch in range(1, 5)}
        state.channel_current = {ch: self.get_current(ch) for ch in range(1, 5)}
        state.default_power = self.get_default_power([1, 2, 3, 4])
        state.default_dataline = self.get_default_dataline([1, 2, 3, 4])
        return state
