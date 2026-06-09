"""Tests for the Fanimation fan entity speed handling.

Pure unit tests — no HA test harness required. Cover:
 * default-speed turn_on logic for last-used and named presets
 * slider math (percentage <-> raw speed) for arbitrary speed counts
 * Issue #1 regression: a fan reporting an out-of-range speed must NOT crash
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.components.fan import DIRECTION_FORWARD, DIRECTION_REVERSE, FanEntityFeature

from custom_components.fanimation.const import (
    CONF_DEFAULT_SPEED,
    CONF_SPEED_COUNT,
    CONF_SUPPORTS_REVERSE,
    DEFAULT_SPEED_LAST_USED,
    DIR_FORWARD,
    DIR_REVERSE,
    SPEED_HIGH,
    SPEED_LOW,
    SPEED_MED,
    fan_type_supports_reverse,
    speed_for_preset,
)
from custom_components.fanimation.device import FanimationState


def _make_fan(
    default_speed: str = DEFAULT_SPEED_LAST_USED,
    speed_count: int = 3,
    fan_type: int = 0,
    supports_reverse: bool | None = None,
):
    """Create a FanimationFan with mocked coordinator and entry for unit testing.

    ``async_set_state`` echoes the requested speed back as a ``FanimationState`` so
    that ``_last_speed`` bookkeeping (which now reads from the verified response)
    behaves as it would against real hardware that accepts the command. Tests that
    need to simulate firmware rejection or comm failure should override the mock
    with their own ``return_value``.

    ``fan_type`` seeds the coordinator state (0 = AC, 2 = DC) so the entity's
    reverse auto-detection can be exercised; ``supports_reverse`` (when not None)
    sets the options override.
    """
    from custom_components.fanimation.fan import FanimationFan

    async def _echo_state(speed: int | None = None, **_kwargs: Any) -> FanimationState:
        return FanimationState(speed=speed if speed is not None else 0)

    options: dict[str, Any] = {CONF_DEFAULT_SPEED: default_speed}
    if supports_reverse is not None:
        options[CONF_SUPPORTS_REVERSE] = supports_reverse

    mock_coordinator = MagicMock()
    mock_coordinator.device = MagicMock()
    mock_coordinator.device.mac = "AA:BB:CC:DD:EE:FF"
    mock_coordinator.device.name = "Test Fan"
    mock_coordinator.device.async_set_state = AsyncMock(side_effect=_echo_state)
    mock_coordinator.async_start_fast_poll = AsyncMock()
    mock_coordinator.data = FanimationState(speed=0, fan_type=fan_type)
    mock_coordinator.connection_failures = 0
    mock_coordinator.config_entry = MagicMock()
    mock_coordinator.config_entry.options = dict(options)
    mock_coordinator.config_entry.entry_id = "test_entry"

    mock_entry = MagicMock()
    mock_entry.entry_id = "test_entry"
    mock_entry.options = dict(options)
    mock_entry.data = {CONF_SPEED_COUNT: speed_count}

    fan = FanimationFan(mock_coordinator, mock_entry)
    return fan, mock_coordinator


class TestDefaultSpeed:
    @pytest.mark.asyncio
    async def test_turn_on_last_used_default(self) -> None:
        fan, mock_coord = _make_fan(DEFAULT_SPEED_LAST_USED)
        fan._last_speed = SPEED_MED

        await fan.async_turn_on()

        mock_coord.device.async_set_state.assert_called_once_with(speed=SPEED_MED)

    @pytest.mark.asyncio
    async def test_turn_on_fixed_low(self) -> None:
        fan, mock_coord = _make_fan("low")
        fan._last_speed = SPEED_HIGH  # should be ignored

        await fan.async_turn_on()

        mock_coord.device.async_set_state.assert_called_once_with(speed=SPEED_LOW)

    @pytest.mark.asyncio
    async def test_turn_on_fixed_medium(self) -> None:
        fan, mock_coord = _make_fan("medium")

        await fan.async_turn_on()

        mock_coord.device.async_set_state.assert_called_once_with(speed=SPEED_MED)

    @pytest.mark.asyncio
    async def test_turn_on_fixed_high(self) -> None:
        fan, mock_coord = _make_fan("high")

        await fan.async_turn_on()

        mock_coord.device.async_set_state.assert_called_once_with(speed=SPEED_HIGH)

    @pytest.mark.asyncio
    async def test_turn_on_with_percentage_overrides_option(self) -> None:
        fan, mock_coord = _make_fan("low")

        await fan.async_turn_on(percentage=100)

        # Should use the explicit percentage (high), not the option (low)
        mock_coord.device.async_set_state.assert_called_once_with(speed=SPEED_HIGH)

    @pytest.mark.asyncio
    async def test_turn_on_no_option_set_uses_last_speed(self) -> None:
        """When options dict has no default_speed key, fall back to last_used."""
        fan, mock_coord = _make_fan(DEFAULT_SPEED_LAST_USED)
        mock_coord.config_entry.options = {}  # no option set at all
        fan._last_speed = SPEED_HIGH

        await fan.async_turn_on()

        mock_coord.device.async_set_state.assert_called_once_with(speed=SPEED_HIGH)


class TestSpeedForPreset:
    """Verify low/medium/high scale proportionally with speed_count."""

    @pytest.mark.parametrize(
        ("count", "expected_low", "expected_medium", "expected_high"),
        [
            (1, 1, 1, 1),  # 1-speed fan: all presets collapse to 1 (clamped, never 0)
            (3, 1, 2, 3),  # 3-speed AC fan — preserves original behaviour
            (6, 2, 4, 6),  # 6-speed DC fan
            (32, 11, 21, 32),  # 32-speed DC fan — close to issue author's (10, 20, 31)
        ],
    )
    def test_preset_mapping(self, count: int, expected_low: int, expected_medium: int, expected_high: int) -> None:
        assert speed_for_preset("low", count) == expected_low
        assert speed_for_preset("medium", count) == expected_medium
        assert speed_for_preset("high", count) == expected_high

    def test_unknown_preset_returns_none(self) -> None:
        assert speed_for_preset("last_used", 32) is None
        assert speed_for_preset("turbo", 32) is None


class TestSliderMath:
    """Verify percentage <-> raw-speed translation for any speed_count."""

    @pytest.mark.parametrize(
        ("count", "raw_speed", "expected_pct"),
        [
            # HA's ranged_value_to_percentage((1, N), v) = int(v * 100 // N)
            (3, 1, 33),
            (3, 2, 66),
            (3, 3, 100),
            (6, 3, 50),
            (6, 6, 100),
            (32, 16, 50),
            (32, 32, 100),
        ],
    )
    def test_percentage_read(self, count: int, raw_speed: int, expected_pct: int) -> None:
        fan, mock_coord = _make_fan(speed_count=count)
        mock_coord.data = FanimationState(speed=raw_speed)
        assert fan.percentage == expected_pct

    @pytest.mark.parametrize(
        ("count", "percentage", "expected_speed"),
        [
            # Round-trip from each speed's percentage back to that speed.
            # ceil(N * pct/100), clamped to [1, N].
            (3, 0, 0),  # 0% → off
            (3, 33, 1),
            (3, 66, 2),
            (3, 100, 3),
            (6, 50, 3),
            (6, 100, 6),
            (32, 50, 16),
            (32, 100, 32),
            (1, 100, 1),  # 1-speed fan
        ],
    )
    @pytest.mark.asyncio
    async def test_set_percentage(self, count: int, percentage: int, expected_speed: int) -> None:
        fan, mock_coord = _make_fan(speed_count=count)
        await fan.async_set_percentage(percentage)
        mock_coord.device.async_set_state.assert_called_once_with(speed=expected_speed)

    def test_percentage_off_returns_zero(self) -> None:
        fan, mock_coord = _make_fan(speed_count=32)
        mock_coord.data = FanimationState(speed=0)
        assert fan.percentage == 0


class TestIssue1Regression:
    """Regression: a fan reporting an out-of-range speed must not crash the entity.

    Issue #1: a 32-speed DC fan set to speed=5 by RF remote, with the integration
    misconfigured for speed_count=3, used to raise ValueError and mark the entity
    unavailable. After the fix, the entity stays available and pegs at 100%.
    """

    @pytest.mark.parametrize("raw_speed", [4, 5, 16, 32])
    def test_out_of_range_speed_does_not_raise(self, raw_speed: int) -> None:
        fan, mock_coord = _make_fan(speed_count=3)
        mock_coord.data = FanimationState(speed=raw_speed)
        # Must not raise; clamped to 100%.
        assert fan.percentage == 100

    def test_in_range_speed_still_works(self) -> None:
        fan, mock_coord = _make_fan(speed_count=3)
        mock_coord.data = FanimationState(speed=2)
        assert fan.percentage == 66


class TestLastSpeedBookkeeping:
    """Regression: ``_last_speed`` must reflect what the *hardware accepted*, not
    what we *asked for*. If the firmware silently rejects an out-of-range speed
    (BTT9 on a 3-speed fan treats SPEED bytes >= 4 as off), pinning ``_last_speed``
    to the rejected value puts ``async_turn_on`` into a stuck-off loop: every
    "Last Used" turn-on resends the bad value and the fan stays off.
    """

    @pytest.mark.asyncio
    async def test_last_speed_not_updated_when_hardware_reports_off(self) -> None:
        """speed_count=6 misconfig on 3-speed fan: requested 5, fan reports off."""
        fan, mock_coord = _make_fan(speed_count=6)
        fan._last_speed = SPEED_MED  # last known good
        mock_coord.device.async_set_state = AsyncMock(
            return_value=FanimationState(speed=0)  # firmware silently rejected
        )

        await fan.async_set_percentage(83)  # → raw speed=5

        # Must NOT be pinned to the rejected value, or "Last Used" turn-on will
        # resend speed=5 forever and the fan will stay off.
        assert fan._last_speed == SPEED_MED

    @pytest.mark.asyncio
    async def test_last_speed_synced_to_verified_response(self) -> None:
        """Successful command: ``_last_speed`` reflects what hardware confirmed."""
        fan, mock_coord = _make_fan(speed_count=3)
        mock_coord.device.async_set_state = AsyncMock(return_value=FanimationState(speed=SPEED_MED))

        await fan.async_set_percentage(66)  # → raw speed=2

        assert fan._last_speed == SPEED_MED

    @pytest.mark.asyncio
    async def test_last_speed_not_updated_on_communication_failure(self) -> None:
        """If ``async_set_state`` returns None (BLE error), keep prior _last_speed."""
        fan, mock_coord = _make_fan(speed_count=3)
        fan._last_speed = SPEED_HIGH
        mock_coord.device.async_set_state = AsyncMock(return_value=None)

        await fan.async_set_percentage(33)

        assert fan._last_speed == SPEED_HIGH

    @pytest.mark.asyncio
    async def test_turn_off_does_not_clobber_last_speed(self) -> None:
        """Turning off must not reset ``_last_speed`` to 0 — turn_on needs it."""
        fan, mock_coord = _make_fan(speed_count=3)
        fan._last_speed = SPEED_MED
        # Hardware reports off after explicit turn-off (this is the normal case).
        mock_coord.device.async_set_state = AsyncMock(return_value=FanimationState(speed=0))

        await fan.async_turn_off()

        # Still SPEED_MED so a subsequent "Last Used" turn-on goes back to medium.
        assert fan._last_speed == SPEED_MED


class TestFanTypeReverseDetection:
    """The reverse heuristic: only the confirmed DC fan_type (2) is reversible."""

    @pytest.mark.parametrize(("fan_type", "expected"), [(2, True), (0, False), (1, False), (3, False)])
    def test_helper(self, fan_type: int, expected: bool) -> None:
        assert fan_type_supports_reverse(fan_type) is expected


class TestIssue4Direction:
    """Issue #4: opt-in reverse direction, auto-defaulting ON only for DC fans.

    AC fans (fan_type 0) hide the control; DC fans (fan_type 2) show it by
    default; the options toggle overrides either way. Reverse is instant — the
    hardware probe confirmed DC fans reverse while stopped or spinning.
    """

    def test_direction_hidden_for_ac_fan(self) -> None:
        fan, _ = _make_fan(fan_type=0)
        assert not (fan.supported_features & FanEntityFeature.DIRECTION)

    def test_direction_auto_shown_for_dc_fan(self) -> None:
        fan, _ = _make_fan(fan_type=2)
        assert fan.supported_features & FanEntityFeature.DIRECTION

    def test_option_forces_on_for_undetected_fan(self) -> None:
        fan, _ = _make_fan(fan_type=0, supports_reverse=True)
        assert fan.supported_features & FanEntityFeature.DIRECTION

    def test_option_forces_off_for_detected_fan(self) -> None:
        fan, _ = _make_fan(fan_type=2, supports_reverse=False)
        assert not (fan.supported_features & FanEntityFeature.DIRECTION)

    def test_current_direction_mapping(self) -> None:
        fan, coord = _make_fan(fan_type=2)
        coord.data = FanimationState(speed=1, direction=DIR_REVERSE, fan_type=2)
        assert fan.current_direction == DIRECTION_REVERSE
        coord.data = FanimationState(speed=1, direction=DIR_FORWARD, fan_type=2)
        assert fan.current_direction == DIRECTION_FORWARD

    def test_current_direction_none_without_data(self) -> None:
        fan, coord = _make_fan(fan_type=2)
        coord.data = None
        assert fan.current_direction is None

    @pytest.mark.asyncio
    async def test_set_direction_reverse_sends_command(self) -> None:
        fan, coord = _make_fan(fan_type=2)
        await fan.async_set_direction(DIRECTION_REVERSE)
        coord.device.async_set_state.assert_called_once_with(direction=DIR_REVERSE)
        coord.async_start_fast_poll.assert_called_once()

    @pytest.mark.asyncio
    async def test_set_direction_forward_sends_command(self) -> None:
        fan, coord = _make_fan(fan_type=2)
        await fan.async_set_direction(DIRECTION_FORWARD)
        coord.device.async_set_state.assert_called_once_with(direction=DIR_FORWARD)
