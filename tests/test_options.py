"""Tests for the shared config-entry option helpers (options.py).

Pure unit tests — no HA harness required. These helpers replaced four
hand-rolled copies of the same fallback logic (coordinator, fan, light,
options flow), so their precedence rules are pinned here directly.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from custom_components.fanimation.const import CONF_SPEED_COUNT, DEFAULT_SPEED_COUNT
from custom_components.fanimation.options import get_option, resolved_speed_count


def _entry(options: dict | None = None, data: dict | None = None) -> MagicMock:
    entry = MagicMock()
    entry.options = options if options is not None else {}
    entry.data = data if data is not None else {}
    return entry


class TestGetOption:
    def test_returns_value_when_option_set(self) -> None:
        assert get_option(_entry(options={"key": 5}), "key", 1) == 5

    def test_returns_default_when_key_missing(self) -> None:
        assert get_option(_entry(options={"other": 5}), "key", 1) == 1

    def test_returns_default_when_options_empty(self) -> None:
        assert get_option(_entry(options={}), "key", 1) == 1

    def test_returns_default_when_entry_is_none(self) -> None:
        assert get_option(None, "key", 1) == 1


class TestResolvedSpeedCount:
    """Precedence: options-flow value wins, then install-time data, then default."""

    def test_options_value_wins_over_data(self) -> None:
        entry = _entry(options={CONF_SPEED_COUNT: 32}, data={CONF_SPEED_COUNT: 6})
        assert resolved_speed_count(entry) == 32

    def test_falls_back_to_install_time_data(self) -> None:
        entry = _entry(options={}, data={CONF_SPEED_COUNT: 6})
        assert resolved_speed_count(entry) == 6

    def test_falls_back_to_default(self) -> None:
        assert resolved_speed_count(_entry()) == DEFAULT_SPEED_COUNT
