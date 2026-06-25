"""Tests for ``smartusbhub_cli.utils``."""

from __future__ import annotations

import json

import pytest

from smartusbhub_cli.utils import (
    bitmask_to_channels,
    channels_to_bitmask,
    format_output,
    resolve_channels,
)


def test_channels_to_bitmask_single():
    assert channels_to_bitmask([1]) == 0b0001
    assert channels_to_bitmask([4]) == 0b1000


def test_channels_to_bitmask_multiple():
    assert channels_to_bitmask([1, 3]) == 0b0101
    assert channels_to_bitmask([2, 4]) == 0b1010
    assert channels_to_bitmask([1, 2, 3, 4]) == 0b1111


def test_channels_to_bitmask_invalid():
    with pytest.raises(ValueError):
        channels_to_bitmask([0])
    with pytest.raises(ValueError):
        channels_to_bitmask([5])


def test_bitmask_to_channels():
    assert bitmask_to_channels(0b0101) == [1, 3]
    assert bitmask_to_channels(0b1010) == [2, 4]
    assert bitmask_to_channels(0b1111) == [1, 2, 3, 4]
    assert bitmask_to_channels(0b0000) == []


def test_resolve_channels_explicit():
    assert resolve_channels([3, 1, 3]) == [1, 3]


def test_resolve_channels_all():
    assert resolve_channels([], all_channels=True) == [1, 2, 3, 4]


def test_resolve_channels_default():
    assert resolve_channels([]) == [1, 2, 3, 4]
    assert resolve_channels([], default=[2, 4]) == [2, 4]


def test_resolve_channels_invalid():
    with pytest.raises(ValueError):
        resolve_channels([5])


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


def test_format_output_human():
    text = format_output({"enabled": True}, human_readable=True)
    assert "Success: True" in text
    assert "enabled: on" in text
