"""Tests for the Fanimation light entity default brightness logic.

Pure unit tests — no HA test harness required.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.fanimation.const import (
    CONF_DEFAULT_BRIGHTNESS,
    DEFAULT_BRIGHTNESS_LAST_USED,
    DOWNLIGHT_MAX,
)
from custom_components.fanimation.device import FanimationState


def _make_light(default_brightness: int = DEFAULT_BRIGHTNESS_LAST_USED):
    """Create a FanimationLight with mocked coordinator for unit testing."""
    from custom_components.fanimation.light import FanimationLight

    mock_coordinator = MagicMock()
    mock_coordinator.device = MagicMock()
    mock_coordinator.device.mac = "AA:BB:CC:DD:EE:FF"
    mock_coordinator.device.name = "Test Fan"
    mock_coordinator.device.async_set_state = AsyncMock()
    mock_coordinator.async_start_fast_poll = AsyncMock()
    mock_coordinator.data = FanimationState(downlight=0)
    mock_coordinator.connection_failures = 0
    mock_coordinator.config_entry = MagicMock()
    mock_coordinator.config_entry.options = {CONF_DEFAULT_BRIGHTNESS: default_brightness}
    mock_coordinator.config_entry.entry_id = "test_entry"

    light = FanimationLight(mock_coordinator, "test_entry")
    return light, mock_coordinator


class TestDefaultBrightness:

    @pytest.mark.asyncio
    async def test_turn_on_last_used_default(self) -> None:
        light, mock_coord = _make_light(DEFAULT_BRIGHTNESS_LAST_USED)
        light._last_brightness = 75

        await light.async_turn_on()

        mock_coord.device.async_set_state.assert_called_once_with(downlight=75)

    @pytest.mark.asyncio
    async def test_turn_on_fixed_brightness(self) -> None:
        light, mock_coord = _make_light(50)
        light._last_brightness = 100  # should be ignored

        await light.async_turn_on()

        mock_coord.device.async_set_state.assert_called_once_with(downlight=50)

    @pytest.mark.asyncio
    async def test_turn_on_with_explicit_brightness_overrides_option(self) -> None:
        light, mock_coord = _make_light(50)

        # HA brightness 128 ≈ fan brightness 50, but let's use 255 → 100
        await light.async_turn_on(**{"brightness": 255})

        mock_coord.device.async_set_state.assert_called_once_with(downlight=DOWNLIGHT_MAX)

    @pytest.mark.asyncio
    async def test_turn_on_no_option_set_uses_last_brightness(self) -> None:
        light, mock_coord = _make_light(DEFAULT_BRIGHTNESS_LAST_USED)
        mock_coord.config_entry.options = {}
        light._last_brightness = 80

        await light.async_turn_on()

        mock_coord.device.async_set_state.assert_called_once_with(downlight=80)

    @pytest.mark.asyncio
    async def test_turn_on_fixed_brightness_min(self) -> None:
        light, mock_coord = _make_light(1)

        await light.async_turn_on()

        mock_coord.device.async_set_state.assert_called_once_with(downlight=1)

    @pytest.mark.asyncio
    async def test_turn_on_fixed_brightness_max(self) -> None:
        light, mock_coord = _make_light(100)

        await light.async_turn_on()

        mock_coord.device.async_set_state.assert_called_once_with(downlight=100)
