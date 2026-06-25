"""Shared pytest fixtures."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict

import pytest

# Make the upstream ``smartusbhub`` package importable from the workspace layout.
_UPSTREAM_ROOT = Path(__file__).resolve().parents[2] / "smartusbhub"
if str(_UPSTREAM_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(_UPSTREAM_ROOT.parent))


class FakeSmartUSBHub:
    """Test double for ``smartusbhub.SmartUSBHub``.

    Uses class-level state so multiple ``HubProtocol`` / CLI invocations within
    a single test share the same simulated device state.
    """

    _state: Dict[str, Any] = {
        "power": {1: False, 2: False, 3: False, 4: False},
        "dataline": {1: False, 2: False, 3: False, 4: False},
        "default_power": {ch: {"enabled": 0, "value": 0} for ch in range(1, 5)},
        "default_dataline": {ch: {"enabled": 0, "value": 0} for ch in range(1, 5)},
        "voltage": {1: 5100, 2: 5000, 3: 4900, 4: 4800},
        "current": {1: 100, 2: 200, 3: 300, 4: 400},
        "auto_restore_status": 0,
        "button_control_status": 1,
        "operate_mode": 0,
        "device_address": 0x0001,
        "firmware_version": 15,
        "hardware_version": 3,
    }

    @classmethod
    def reset(cls) -> None:
        cls._state = {
            "power": {1: False, 2: False, 3: False, 4: False},
            "dataline": {1: False, 2: False, 3: False, 4: False},
            "default_power": {ch: {"enabled": 0, "value": 0} for ch in range(1, 5)},
            "default_dataline": {ch: {"enabled": 0, "value": 0} for ch in range(1, 5)},
            "voltage": {1: 5100, 2: 5000, 3: 4900, 4: 4800},
            "current": {1: 100, 2: 200, 3: 300, 4: 400},
            "auto_restore_status": 0,
            "button_control_status": 1,
            "operate_mode": 0,
            "device_address": 0x0001,
            "firmware_version": 15,
            "hardware_version": 3,
        }

    def __init__(self, port: str) -> None:
        self.port = port

    def disconnect(self) -> None:
        pass

    @classmethod
    def scan_available_ports(cls) -> list[str]:
        return ["/dev/fakehub"]

    @classmethod
    def scan_and_connect(cls) -> "FakeSmartUSBHub":
        return cls("/dev/fakehub")

    def set_channel_power(self, *channels: int, state: int) -> bool:
        for ch in channels:
            self._state["power"][ch] = bool(state)
        return True

    def get_channel_power_status(self, *channels: int) -> Any:
        if len(channels) == 1:
            return int(self._state["power"][channels[0]])
        return {ch: int(self._state["power"][ch]) for ch in channels}

    def set_channel_power_interlock(self, channel: int | None) -> bool:
        return True

    def set_channel_dataline(self, *channels: int, state: int) -> bool:
        for ch in channels:
            self._state["dataline"][ch] = bool(state)
        return True

    def get_channel_dataline_status(self, *channels: int) -> Dict[int, int]:
        return {ch: int(self._state["dataline"][ch]) for ch in channels}

    def get_channel_voltage(self, channel: int) -> int:
        return self._state["voltage"][channel]

    def get_channel_current(self, channel: int) -> int:
        return self._state["current"][channel]

    def set_default_power_status(
        self, *channels: int, enable: int, status: int = 0
    ) -> bool:
        for ch in channels:
            self._state["default_power"][ch] = {"enabled": enable, "value": status}
        return True

    def get_default_power_status(self, *channels: int) -> Dict[int, Dict[str, int]]:
        return {ch: self._state["default_power"][ch] for ch in channels}

    def set_default_dataline_status(
        self, *channels: int, enable: int, status: int = 0
    ) -> bool:
        for ch in channels:
            self._state["default_dataline"][ch] = {"enabled": enable, "value": status}
        return True

    def get_default_dataline_status(self, *channels: int) -> Dict[int, Dict[str, int]]:
        return {ch: self._state["default_dataline"][ch] for ch in channels}

    def set_auto_restore(self, enable: bool) -> bool:
        self._state["auto_restore_status"] = 1 if enable else 0
        return True

    def get_auto_restore_status(self) -> int:
        return self._state["auto_restore_status"]

    def set_button_control(self, enable: bool) -> bool:
        self._state["button_control_status"] = 1 if enable else 0
        return True

    def get_button_control_status(self) -> int:
        return self._state["button_control_status"]

    def set_operate_mode(self, mode: int) -> bool:
        self._state["operate_mode"] = mode
        return True

    def get_operate_mode(self) -> int:
        return self._state["operate_mode"]

    def set_device_address(self, address: int) -> bool:
        self._state["device_address"] = address
        return True

    def get_device_address(self) -> int:
        return self._state["device_address"]

    def factory_reset(self) -> bool:
        return True

    def get_firmware_version(self) -> int:
        return self._state["firmware_version"]

    def get_hardware_version(self) -> int:
        return self._state["hardware_version"]

    def get_device_info(self) -> Dict[str, Any]:
        return {
            "id": self.port.split("/")[-1],
            "address": self._state["device_address"],
            "hardware_version": self._state["hardware_version"],
            "firmware_version": self._state["firmware_version"],
            "operate_mode": "normal"
            if self._state["operate_mode"] == 0
            else "interlock",
            "auto_restore": "enabled"
            if self._state["auto_restore_status"]
            else "disabled",
            "button_control_status": "enabled"
            if self._state["button_control_status"]
            else "disabled",
        }


@pytest.fixture
def fake_hub_class():
    """Return the test double class for patching."""
    return FakeSmartUSBHub


@pytest.fixture
def fake_hub():
    """Return an instance of the test double."""
    return FakeSmartUSBHub("/dev/fakehub")


@pytest.fixture
def mock_hub(monkeypatch, fake_hub_class):
    """Patch ``smartusbhub_cli.protocol.SmartUSBHub`` with the test double."""
    from smartusbhub_cli import protocol as protocol_module

    fake_hub_class.reset()
    monkeypatch.setattr(protocol_module, "SmartUSBHub", fake_hub_class)
    return fake_hub_class
