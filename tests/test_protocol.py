"""Tests for ``smartusbhub_cli.protocol``."""

from __future__ import annotations

import pytest

from smartusbhub_cli.protocol import HubNotFoundError, HubProtocol, HubTimeoutError


def test_hub_protocol_power(mock_hub):
    proto = HubProtocol("/dev/fakehub")
    assert proto.set_power([1, 3], True) is True
    result = proto.get_power([1, 2, 3, 4])
    assert result[1] is True
    assert result[3] is True


def test_hub_protocol_power_timeout(mock_hub, monkeypatch):
    from smartusbhub_cli import protocol as protocol_module

    class SilentSerial:
        def __init__(self, port: str, *args: object, **kwargs: object) -> None:
            self.port = port

        @property
        def in_waiting(self) -> int:
            return 0

        def write(self, data: bytes) -> int:
            return len(data)

        def read(self, size: int = 1) -> bytes:
            return b""

        def flush(self) -> None:
            pass

        def close(self) -> None:
            pass

    monkeypatch.setattr(protocol_module.serial, "Serial", SilentSerial)
    proto = HubProtocol("/dev/fakehub", timeout=0.05)
    with pytest.raises(HubTimeoutError):
        proto.set_power([1], True)


def test_hub_protocol_interlock(mock_hub):
    proto = HubProtocol("/dev/fakehub")
    assert proto.set_interlock(1) is True
    assert proto.set_interlock(0) is True


def test_hub_protocol_dataline(mock_hub):
    proto = HubProtocol("/dev/fakehub")
    assert proto.set_dataline([2, 4], True) is True
    result = proto.get_dataline([2, 4])
    assert result[2] is True
    assert result[4] is True


def test_hub_protocol_measurements(mock_hub):
    proto = HubProtocol("/dev/fakehub")
    assert proto.get_voltage(1) == 5.1
    assert proto.get_current(1) == 0.1


def test_hub_protocol_default_power(mock_hub):
    proto = HubProtocol("/dev/fakehub")
    assert proto.set_default_power([1], enable=True, state=True) is True
    result = proto.get_default_power([1])
    assert result[1] == {"enabled": True, "value": True}


def test_hub_protocol_default_dataline(mock_hub):
    proto = HubProtocol("/dev/fakehub")
    assert proto.set_default_dataline([2], enable=True, state=False) is True
    result = proto.get_default_dataline([2])
    assert result[2] == {"enabled": True, "value": False}


def test_hub_protocol_auto_restore(mock_hub):
    proto = HubProtocol("/dev/fakehub")
    assert proto.set_auto_restore(True) is True
    assert proto.get_auto_restore() is True


def test_hub_protocol_button_control(mock_hub):
    proto = HubProtocol("/dev/fakehub")
    assert proto.set_button_control(False) is False
    assert proto.get_button_control() is False


def test_hub_protocol_operate_mode(mock_hub):
    proto = HubProtocol("/dev/fakehub")
    assert proto.set_operate_mode("interlock") == "interlock"
    assert proto.get_operate_mode() == "interlock"
    assert proto.set_operate_mode("normal") == "normal"


def test_hub_protocol_device_address(mock_hub):
    proto = HubProtocol("/dev/fakehub")
    assert proto.set_device_address(0x1234) == 0x1234
    assert proto.get_device_address() == 0x1234


def test_hub_protocol_device_address_out_of_range(mock_hub):
    proto = HubProtocol("/dev/fakehub")
    with pytest.raises(ValueError):
        proto.set_device_address(0x10000)


def test_hub_protocol_factory_reset(mock_hub):
    proto = HubProtocol("/dev/fakehub")
    assert proto.factory_reset() is True


def test_hub_protocol_versions(mock_hub):
    proto = HubProtocol("/dev/fakehub")
    assert proto.get_firmware_version() == "V1.15"
    assert proto.get_hardware_version() == "V1.3"


def test_hub_protocol_device_info(mock_hub):
    proto = HubProtocol("/dev/fakehub")
    info = proto.get_device_info()
    assert info.operate_mode == "normal"
    assert info.hardware_version == "V1.3"
    assert info.firmware_version == "V1.15"
    assert info.channel_power == {1: False, 2: False, 3: False, 4: False}


def test_hub_protocol_scan_ports(mock_hub):
    assert HubProtocol.scan_ports() == ["/dev/fakehub"]


def test_hub_protocol_scan_and_connect(mock_hub):
    proto = HubProtocol.scan_and_connect()
    assert proto is not None
    assert proto.port == "/dev/fakehub"


def test_hub_protocol_close_is_safe(mock_hub):
    proto = HubProtocol("/dev/fakehub")
    proto.close()
    with pytest.raises(HubNotFoundError):
        proto.set_power([1], True)
