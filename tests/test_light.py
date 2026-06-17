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


class TestLightMisc:
    """Cover setup, is_on, brightness, extra attributes, and turn_off."""

    @pytest.mark.asyncio
    async def test_async_setup_entry_adds_one_light(self) -> None:
        from custom_components.fanimation.light import FanimationLight, async_setup_entry

        _, coordinator = _make_light()
        entry = MagicMock()
        entry.runtime_data = coordinator
        entry.entry_id = "test_entry"

        added: list = []
        await async_setup_entry(MagicMock(), entry, lambda e: added.extend(e))

        assert len(added) == 1
        assert isinstance(added[0], FanimationLight)

    def test_is_on_true_when_lit(self) -> None:
        light, coord = _make_light()
        coord.data = FanimationState(downlight=50)
        assert light.is_on is True

    def test_is_on_false_when_dark(self) -> None:
        light, coord = _make_light()
        coord.data = FanimationState(downlight=0)
        assert light.is_on is False

    def test_is_on_none_without_data(self) -> None:
        light, coord = _make_light()
        coord.data = None
        assert light.is_on is None

    def test_brightness_scales_to_ha_255(self) -> None:
        light, coord = _make_light()
        coord.data = FanimationState(downlight=DOWNLIGHT_MAX)
        assert light.brightness == 255

    def test_brightness_none_without_data(self) -> None:
        light, coord = _make_light()
        coord.data = None
        assert light.brightness is None

    def test_extra_state_attributes(self) -> None:
        light, _ = _make_light()
        assert "rf_remote_sync" in light.extra_state_attributes

    @pytest.mark.asyncio
    async def test_turn_off_sets_downlight_zero(self) -> None:
        light, coord = _make_light()
        await light.async_turn_off()
        coord.device.async_set_state.assert_called_once_with(downlight=0)
        coord.async_start_fast_poll.assert_awaited_once()
