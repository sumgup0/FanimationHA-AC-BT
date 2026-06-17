"""Tests for the Fanimation sleep-timer (number) entity.

Pure unit tests — no HA harness required (mirrors test_light.py). Covers the native
value, the fan-must-be-running guard (the translatable HomeAssistantError), the
cancel / no-state edge cases, the extra-state attributes, and platform setup.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.exceptions import HomeAssistantError

from custom_components.fanimation.const import DOMAIN, POLL_SLOW
from custom_components.fanimation.device import FanimationState


def _make_coordinator(speed: int = 1, timer_minutes: int = 0):
    """Build a mocked coordinator shaped like the real one (see test_light.py)."""
    coordinator = MagicMock()
    coordinator.device = MagicMock()
    coordinator.device.mac = "AA:BB:CC:DD:EE:FF"
    coordinator.device.name = "Test Fan"
    coordinator.device.async_set_state = AsyncMock()
    coordinator.async_start_fast_poll = AsyncMock()
    coordinator.data = FanimationState(speed=speed, timer_minutes=timer_minutes)
    coordinator.connection_failures = 0
    return coordinator


def _make_timer(speed: int = 1, timer_minutes: int = 0):
    """Create a FanimationTimer backed by a mocked coordinator."""
    from custom_components.fanimation.number import FanimationTimer

    coordinator = _make_coordinator(speed=speed, timer_minutes=timer_minutes)
    return FanimationTimer(coordinator, "test_entry"), coordinator


def test_unique_id_and_native_value() -> None:
    timer, _ = _make_timer(timer_minutes=120)
    assert timer._attr_unique_id == "AA:BB:CC:DD:EE:FF_timer"
    assert timer.native_value == 120


def test_native_value_is_none_without_data() -> None:
    timer, coordinator = _make_timer()
    coordinator.data = None
    assert timer.native_value is None


@pytest.mark.asyncio
async def test_set_timer_while_running_sends_command() -> None:
    timer, coordinator = _make_timer(speed=1)

    await timer.async_set_native_value(30)

    coordinator.device.async_set_state.assert_called_once_with(timer_minutes=30)
    coordinator.async_start_fast_poll.assert_awaited_once()


@pytest.mark.asyncio
async def test_set_timer_while_fan_off_raises_translatable() -> None:
    timer, coordinator = _make_timer(speed=0)

    with pytest.raises(HomeAssistantError) as exc_info:
        await timer.async_set_native_value(30)

    # The rule under test: a translation_key, not a hard-coded English message.
    assert exc_info.value.translation_domain == DOMAIN
    assert exc_info.value.translation_key == "timer_requires_fan_on"
    coordinator.device.async_set_state.assert_not_called()


@pytest.mark.asyncio
async def test_cancel_timer_allowed_while_fan_off() -> None:
    # Setting 0 cancels the timer and must be allowed even with the fan stopped.
    timer, coordinator = _make_timer(speed=0)

    await timer.async_set_native_value(0)

    coordinator.device.async_set_state.assert_called_once_with(timer_minutes=0)


@pytest.mark.asyncio
async def test_set_timer_without_state_does_not_raise() -> None:
    # No coordinator data yet → the running-check is skipped and the command is sent.
    timer, coordinator = _make_timer(speed=0)
    coordinator.data = None

    await timer.async_set_native_value(30)

    coordinator.device.async_set_state.assert_called_once_with(timer_minutes=30)


def test_extra_state_attributes_extend_base() -> None:
    timer, _ = _make_timer()

    attrs = timer.extra_state_attributes

    assert attrs["connection_status"] == "connected"  # inherited from FanimationEntity
    assert "Fan must be running" in attrs["timer_note"]
    assert "rf_remote_sync" in attrs


@pytest.mark.asyncio
async def test_async_setup_entry_adds_single_timer() -> None:
    from custom_components.fanimation.number import FanimationTimer, async_setup_entry

    coordinator = _make_coordinator()
    entry = MagicMock()
    entry.runtime_data = coordinator
    entry.entry_id = "test_entry"

    added: list = []
    await async_setup_entry(MagicMock(), entry, lambda entities: added.extend(entities))

    assert len(added) == 1
    assert isinstance(added[0], FanimationTimer)


class TestConnectionStatus:
    """Cover the base entity's connection_status formatting (entity.py)."""

    def test_connected_when_no_failures(self) -> None:
        timer, coordinator = _make_timer()
        coordinator.connection_failures = 0
        assert timer.extra_state_attributes["connection_status"] == "connected"

    def test_single_failure_is_singular(self) -> None:
        timer, coordinator = _make_timer()
        coordinator.connection_failures = 1
        status = timer.extra_state_attributes["connection_status"]
        assert status == f"unreachable (1 attempt, ~{POLL_SLOW // 60} min)"

    def test_minutes_window_is_plural(self) -> None:
        timer, coordinator = _make_timer()
        coordinator.connection_failures = 2
        status = timer.extra_state_attributes["connection_status"]
        assert "2 attempts" in status
        assert "min" in status

    def test_hours_window(self) -> None:
        timer, coordinator = _make_timer()
        coordinator.connection_failures = 3600 // POLL_SLOW  # 60 min → "~1 hr"
        assert "hr" in timer.extra_state_attributes["connection_status"]

    def test_days_window(self) -> None:
        timer, coordinator = _make_timer()
        coordinator.connection_failures = 86400 // POLL_SLOW  # 1440 min → "~1 day(s)"
        assert "day(s)" in timer.extra_state_attributes["connection_status"]
