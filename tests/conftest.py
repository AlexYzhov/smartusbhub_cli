"""Shared pytest fixtures."""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock

import pytest

from smartusbhub_cli import protocol as protocol_module


class FakePortInfo:
    """Minimal object returned by ``serial.tools.list_ports.comports``."""

    def __init__(self, device: str, vid: int, pid: int) -> None:
        self.device = device
        self.vid = vid
        self.pid = pid


class FakeSerial:
    """In-memory serial port that emulates SmartUSBHub protocol responses."""

    def __init__(self, port: str, *args: Any, **kwargs: Any) -> None:
        self.port = port
        self.is_open = True
        self._state: Dict[str, Any] = {
            "power": {1: False, 2: False, 3: False, 4: False},
            "dataline": {1: False, 2: False, 3: False, 4: False},
            "default_power": {ch: {"enabled": 0, "value": 0} for ch in range(1, 5)},
            "default_dataline": {ch: {"enabled": 0, "value": 0} for ch in range(1, 5)},
            "voltage": {1: 5100, 2: 5000, 3: 4900, 4: 4800},
            "current": {1: 100, 2: 200, 3: 300, 4: 400},
            "auto_restore": 0,
            "button_control": 1,
            "operate_mode": 0,
            "device_address": 0x0001,
            "firmware_version": 15,
            "hardware_version": 3,
        }
        self._written: bytes = b""
        self._read_buffer: bytearray = bytearray()

    def reset(self) -> None:
        self._state = {
            "power": {1: False, 2: False, 3: False, 4: False},
            "dataline": {1: False, 2: False, 3: False, 4: False},
            "default_power": {ch: {"enabled": 0, "value": 0} for ch in range(1, 5)},
            "default_dataline": {ch: {"enabled": 0, "value": 0} for ch in range(1, 5)},
            "voltage": {1: 5100, 2: 5000, 3: 4900, 4: 4800},
            "current": {1: 100, 2: 200, 3: 300, 4: 400},
            "auto_restore": 0,
            "button_control": 1,
            "operate_mode": 0,
            "device_address": 0x0001,
            "firmware_version": 15,
            "hardware_version": 3,
        }
        self._read_buffer.clear()

    @property
    def in_waiting(self) -> int:
        return len(self._read_buffer)

    def write(self, data: bytes) -> int:
        self._written = data
        self._handle_command(data)
        return len(data)

    def read(self, size: int = 1) -> bytes:
        if size > len(self._read_buffer):
            size = len(self._read_buffer)
        chunk = bytes(self._read_buffer[:size])
        self._read_buffer[:size] = b""
        return chunk

    def flush(self) -> None:
        pass

    def reset_input_buffer(self) -> None:
        self._read_buffer.clear()

    def close(self) -> None:
        pass

    def _emit(self, cmd: int, channel: int, value: int, extra: Optional[List[int]] = None) -> None:
        if extra is None:
            checksum = (cmd + channel + value) & 0xFF
            self._read_buffer.extend([0x55, 0x5A, cmd, channel, value, checksum])
        else:
            checksum = (cmd + channel + extra[0] + extra[1]) & 0xFF
            self._read_buffer.extend([0x55, 0x5A, cmd, channel, extra[0], extra[1], checksum])

    @staticmethod
    def _mask_to_channels(mask: int) -> List[int]:
        return [i for i in range(1, 5) if mask & (1 << (i - 1))]

    def _handle_command(self, data: bytes) -> None:
        if len(data) < 6:
            return
        cmd = data[2]
        channel = data[3]
        value = data[4]

        if cmd == protocol_module.CMD_SET_CHANNEL_POWER:
            for ch in self._mask_to_channels(channel):
                self._state["power"][ch] = bool(value)
            self._emit(cmd, channel, value)

        elif cmd == protocol_module.CMD_GET_CHANNEL_POWER_STATUS:
            for ch in self._mask_to_channels(channel):
                self._emit(cmd, 1 << (ch - 1), int(self._state["power"][ch]))

        elif cmd == protocol_module.CMD_SET_CHANNEL_POWER_INTERLOCK:
            if channel == 0:
                for ch in range(1, 5):
                    self._state["power"][ch] = False
            else:
                for ch in self._mask_to_channels(channel):
                    self._state["power"][ch] = False
            self._emit(cmd, channel, value)

        elif cmd == protocol_module.CMD_SET_CHANNEL_DATALINE:
            for ch in self._mask_to_channels(channel):
                self._state["dataline"][ch] = bool(value)
            self._emit(cmd, channel, value)

        elif cmd == protocol_module.CMD_GET_CHANNEL_DATALINE_STATUS:
            for ch in self._mask_to_channels(channel):
                self._emit(cmd, 1 << (ch - 1), int(self._state["dataline"][ch]))

        elif cmd == protocol_module.CMD_GET_CHANNEL_VOLTAGE:
            voltage = self._state["voltage"][self._mask_to_channels(channel)[0]]
            self._emit(cmd, channel, voltage, [(voltage >> 8) & 0xFF, voltage & 0xFF])

        elif cmd == protocol_module.CMD_GET_CHANNEL_CURRENT:
            current = self._state["current"][self._mask_to_channels(channel)[0]]
            self._emit(cmd, channel, current, [(current >> 8) & 0xFF, current & 0xFF])

        elif cmd == protocol_module.CMD_SET_DEFAULT_POWER_STATUS:
            enable, status = data[4], data[5]
            for ch in self._mask_to_channels(channel):
                self._state["default_power"][ch] = {"enabled": enable, "value": status}
            self._emit(cmd, channel, 0, [enable, status])

        elif cmd == protocol_module.CMD_GET_DEFAULT_POWER_STATUS:
            for ch in self._mask_to_channels(channel):
                dp = self._state["default_power"][ch]
                self._emit(cmd, 1 << (ch - 1), 0, [dp["enabled"], dp["value"]])

        elif cmd == protocol_module.CMD_SET_DEFAULT_DATALINE_STATUS:
            enable, status = data[4], data[5]
            for ch in self._mask_to_channels(channel):
                self._state["default_dataline"][ch] = {"enabled": enable, "value": status}
            self._emit(cmd, channel, 0, [enable, status])

        elif cmd == protocol_module.CMD_GET_DEFAULT_DATALINE_STATUS:
            for ch in self._mask_to_channels(channel):
                dd = self._state["default_dataline"][ch]
                self._emit(cmd, 1 << (ch - 1), 0, [dd["enabled"], dd["value"]])

        elif cmd == protocol_module.CMD_SET_AUTO_RESTORE:
            self._state["auto_restore"] = int(value)
            self._emit(cmd, channel, value)

        elif cmd == protocol_module.CMD_GET_AUTO_RESTORE_STATUS:
            self._emit(cmd, channel, self._state["auto_restore"])

        elif cmd == protocol_module.CMD_SET_BUTTON_CONTROL:
            self._state["button_control"] = int(value)
            self._emit(cmd, channel, value)

        elif cmd == protocol_module.CMD_GET_BUTTON_CONTROL_STATUS:
            self._emit(cmd, channel, self._state["button_control"])

        elif cmd == protocol_module.CMD_SET_OPERATE_MODE:
            self._state["operate_mode"] = int(value)
            self._emit(cmd, channel, value)

        elif cmd == protocol_module.CMD_GET_OPERATE_MODE:
            self._emit(cmd, channel, self._state["operate_mode"])

        elif cmd == protocol_module.CMD_SET_DEVICE_ADDRESS:
            address = (channel << 8) | value
            self._state["device_address"] = address
            self._emit(cmd, channel, value)

        elif cmd == protocol_module.CMD_GET_DEVICE_ADDRESS:
            address = self._state["device_address"]
            self._emit(cmd, (address >> 8) & 0xFF, address & 0xFF)

        elif cmd == protocol_module.CMD_FACTORY_RESET:
            self.reset()
            self._emit(cmd, channel, value)

        elif cmd == protocol_module.CMD_GET_FIRMWARE_VERSION:
            self._emit(cmd, channel, self._state["firmware_version"])

        elif cmd == protocol_module.CMD_GET_HARDWARE_VERSION:
            self._emit(cmd, channel, self._state["hardware_version"])


@pytest.fixture
def fake_serial(monkeypatch):
    """Patch serial.Serial so all HubProtocol instances use FakeSerial."""
    opened: List[FakeSerial] = []

    # Share device state across FakeSerial instances so multiple HubProtocol
    # lifecycles within a single test see the same simulated hub.
    shared_state: Dict[str, Dict[str, Any]] = {}

    def fake_constructor(port: str, *args: Any, **kwargs: Any) -> FakeSerial:
        fake = FakeSerial(port, *args, **kwargs)
        if port in shared_state:
            fake._state = shared_state[port]
        else:
            fake.reset()
            shared_state[port] = fake._state
        opened.append(fake)
        return fake

    monkeypatch.setattr(protocol_module.serial, "Serial", fake_constructor)
    monkeypatch.setattr(
        protocol_module.serial.tools.list_ports,
        "comports",
        lambda: [FakePortInfo("/dev/fakehub", protocol_module.VID_SMARTUSBHUB, protocol_module.PID_SMARTUSBHUB)],
    )
    yield opened
    for fake in opened:
        fake.close()


@pytest.fixture
def mock_hub(fake_serial):
    """Provide a single FakeSerial instance for tests that need direct access."""
    return fake_serial


@pytest.fixture
def fake_hub_class():
    """Backward-compatible alias for tests that reference the old fake hub class."""
    return MagicMock


@pytest.fixture(autouse=True)
def _disable_rich_color(monkeypatch):
    """Disable Rich/Typer colored output so assertions are CI-safe."""
    monkeypatch.setenv("NO_COLOR", "1")
    monkeypatch.setenv("TERM", "dumb")
