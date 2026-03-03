"""Tests for the Fanimation fan entity default speed logic.

Pure unit tests — no HA test harness required. Test the turn-on
speed selection logic based on options configuration.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.fanimation.const import (
    CONF_DEFAULT_SPEED,
    DEFAULT_SPEED_LAST_USED,
    SPEED_HIGH,
    SPEED_LOW,
    SPEED_MED,
)
from custom_components.fanimation.device import FanimationState


def _make_fan(default_speed: str = DEFAULT_SPEED_LAST_USED):
    """Create a FanimationFan with mocked coordinator for unit testing."""
    from custom_components.fanimation.fan import FanimationFan

    mock_coordinator = MagicMock()
    mock_coordinator.device = MagicMock()
    mock_coordinator.device.mac = "AA:BB:CC:DD:EE:FF"
    mock_coordinator.device.name = "Test Fan"
    mock_coordinator.device.async_set_state = AsyncMock()
    mock_coordinator.async_start_fast_poll = AsyncMock()
    mock_coordinator.data = FanimationState(speed=0)
    mock_coordinator.connection_failures = 0
    mock_coordinator.config_entry = MagicMock()
    mock_coordinator.config_entry.options = {CONF_DEFAULT_SPEED: default_speed}
    mock_coordinator.config_entry.entry_id = "test_entry"

    fan = FanimationFan(mock_coordinator, "test_entry")
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
