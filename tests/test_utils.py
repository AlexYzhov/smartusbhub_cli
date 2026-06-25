"""Tests for ``smartusbhub_cli.utils``."""

from __future__ import annotations

import json

import pytest

from smartusbhub_cli.utils import (
    format_output,
    resolve_channels,
)


def test_resolve_channels_explicit():
    assert resolve_channels([3, 1, 3]) == [1, 3]


def test_resolve_channels_all():
    assert resolve_channels([], all_channels=True) == [1, 2, 3, 4]


def test_resolve_channels_default():
    assert resolve_channels([]) == [1, 2, 3, 4]
    assert resolve_channels([], default=[2, 4]) == [2, 4]


def test_resolve_channels_invalid():
    with pytest.raises(ValueError, match="Invalid channel"):
        resolve_channels([5])
    with pytest.raises(ValueError, match="Channels must be integers from 1 to 4"):
        resolve_channels([0])


def test_format_output_json():
    text = format_output({"foo": 1})
    parsed = json.loads(text)
    assert parsed["success"] is True
    assert parsed["data"] == {"foo": 1}
    assert "error" not in parsed


def test_format_output_error():
    text = format_output(None, success=False, error="boom")
    parsed = json.loads(text)
    assert parsed["success"] is False
    assert parsed["error"] == "boom"
    assert "data" not in parsed


def test_format_output_pretty():
    text = format_output({"1": True, "2": False}, pretty=True)
    assert "Status: OK" in text
    assert "Channel 1: on" in text
    assert "Channel 2: off" in text


def test_format_output_pretty_measurement():
    text = format_output({"channel": 1, "voltage": 5.1}, pretty=True)
    assert "Status: OK" in text
    assert "Channel 1: 5.100 V" in text


def test_format_output_pretty_error():
    text = format_output(None, success=False, error="no device", pretty=True)
    assert "Status: FAILED" in text
    assert "Error: no device" in text
