"""Tests for the Fanimation sleep-timer (number) entity.

Pure unit tests — no HA harness required (mirrors test_light.py). Covers the native
value, the fan-must-be-running guard (the translatable HomeAssistantError), the
cancel / no-state edge cases, the extra-state attributes, and platform setup.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.exceptions import HomeAssistantError
from homeassistant.util import dt as dt_util

from custom_components.fanimation.const import DOMAIN
from custom_components.fanimation.device import FanimationState


def _make_coordinator(speed: int = 1, timer_minutes: int = 0):
    """Build a mocked coordinator shaped like the real one (see test_light.py).

    ``async_set_state`` emulates the BTCR9 firmware rule under test: a timer
    only takes while the motor runs (``speed`` here plays the *actual* motor
    state), otherwise the verified response reads timer 0. Tests that need a
    different device behaviour override the mock's ``return_value``.
    """

    async def _echo_state(timer_minutes: int | None = None, **_kwargs: Any) -> FanimationState:
        accepted = timer_minutes if (timer_minutes is not None and speed > 0) else 0
        return FanimationState(speed=speed, timer_minutes=accepted)

    coordinator = MagicMock()
    coordinator.device = MagicMock()
    coordinator.device.mac = "AA:BB:CC:DD:EE:FF"
    coordinator.device.name = "Test Fan"
    coordinator.device.async_set_state = AsyncMock(side_effect=_echo_state)
    coordinator.async_start_fast_poll = AsyncMock()
    coordinator.data = FanimationState(speed=speed, timer_minutes=timer_minutes)
    coordinator.connection_failures = 0
    coordinator.first_failure_at = None
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
    """Fan really off → firmware ignores the timer (verified 0) → translatable error."""
    timer, coordinator = _make_timer(speed=0)

    with pytest.raises(HomeAssistantError) as exc_info:
        await timer.async_set_native_value(30)

    # The rule under test: a translation_key, not a hard-coded English message.
    assert exc_info.value.translation_domain == DOMAIN
    assert exc_info.value.translation_key == "timer_requires_fan_on"
    # The command is attempted (the firmware ignores it harmlessly); the error
    # comes from the verified response, not a pre-check against cached state.
    coordinator.device.async_set_state.assert_called_once_with(timer_minutes=30)


@pytest.mark.asyncio
async def test_cancel_timer_allowed_while_fan_off() -> None:
    # Setting 0 cancels the timer and must be allowed even with the fan stopped.
    timer, coordinator = _make_timer(speed=0)

    await timer.async_set_native_value(0)

    coordinator.device.async_set_state.assert_called_once_with(timer_minutes=0)


@pytest.mark.asyncio
async def test_set_timer_trusts_device_over_stale_cache() -> None:
    """RF-remote regression: cached state says the fan is off, but it is actually
    running (the remote change hasn't been polled yet). The timer must be
    accepted based on the device's verified response, not rejected up front
    from minutes-stale cache."""
    timer, coordinator = _make_timer(speed=0)  # cache: off
    coordinator.device.async_set_state = AsyncMock(
        return_value=FanimationState(speed=2, timer_minutes=45)  # hardware: running
    )

    await timer.async_set_native_value(45)  # must not raise

    coordinator.device.async_set_state.assert_called_once_with(timer_minutes=45)


@pytest.mark.asyncio
async def test_set_timer_comm_failure_does_not_raise() -> None:
    """A None response (BLE failure) must not surface as 'fan must be running' —
    availability is the coordinator's concern, not a timer misuse."""
    timer, coordinator = _make_timer(speed=1)
    coordinator.device.async_set_state = AsyncMock(return_value=None)

    await timer.async_set_native_value(30)

    coordinator.async_start_fast_poll.assert_awaited_once()


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
    """Cover the base entity's connection_status formatting (entity.py).

    The elapsed time comes from the coordinator's ``first_failure_at`` streak
    timestamp — real downtime, not a failure-count estimate (which overstated
    wildly during 1 s fast-poll bursts).
    """

    def test_connected_when_no_failures(self) -> None:
        timer, coordinator = _make_timer()
        coordinator.connection_failures = 0
        assert timer.extra_state_attributes["connection_status"] == "connected"

    def test_fresh_failure_burst_shows_under_a_minute(self) -> None:
        """3 fast-poll failures seconds apart must read '<1 min', not '~15 min'."""
        timer, coordinator = _make_timer()
        coordinator.connection_failures = 3
        coordinator.first_failure_at = dt_util.utcnow() - timedelta(seconds=3)
        status = timer.extra_state_attributes["connection_status"]
        assert status == "unreachable (3 attempts, <1 min)"

    def test_missing_streak_timestamp_falls_back_to_under_a_minute(self) -> None:
        timer, coordinator = _make_timer()
        coordinator.connection_failures = 1
        coordinator.first_failure_at = None
        assert "<1 min" in timer.extra_state_attributes["connection_status"]

    def test_single_failure_is_singular(self) -> None:
        timer, coordinator = _make_timer()
        coordinator.connection_failures = 1
        coordinator.first_failure_at = dt_util.utcnow() - timedelta(minutes=5)
        status = timer.extra_state_attributes["connection_status"]
        assert status == "unreachable (1 attempt, ~5 min)"

    def test_minutes_window_is_plural(self) -> None:
        timer, coordinator = _make_timer()
        coordinator.connection_failures = 2
        coordinator.first_failure_at = dt_util.utcnow() - timedelta(minutes=10)
        status = timer.extra_state_attributes["connection_status"]
        assert "2 attempts" in status
        assert "~10 min" in status

    def test_hours_window(self) -> None:
        timer, coordinator = _make_timer()
        coordinator.connection_failures = 12
        coordinator.first_failure_at = dt_util.utcnow() - timedelta(hours=2)
        assert "~2 hr" in timer.extra_state_attributes["connection_status"]

    def test_days_window(self) -> None:
        timer, coordinator = _make_timer()
        coordinator.connection_failures = 288
        coordinator.first_failure_at = dt_util.utcnow() - timedelta(days=3)
        assert "~3 day(s)" in timer.extra_state_attributes["connection_status"]
