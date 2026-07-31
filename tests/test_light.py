"""Tests for the Fanimation light entity default brightness logic.

Pure unit tests — no HA test harness required.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.fanimation.const import (
    CONF_DEFAULT_BRIGHTNESS,
    DEFAULT_BRIGHTNESS_LAST_USED,
    DOWNLIGHT_MAX,
)
from custom_components.fanimation.device import FanimationState


def _make_light(default_brightness: int = DEFAULT_BRIGHTNESS_LAST_USED):
    """Create a FanimationLight with mocked coordinator for unit testing.

    ``async_set_state`` echoes the requested brightness back as a verified
    ``FanimationState`` (the hardware accepting the command), mirroring the
    fan tests — ``_last_brightness`` bookkeeping reads from the verified
    response. Tests simulating rejection/comm failure override the mock.
    """
    from custom_components.fanimation.light import FanimationLight

    async def _echo_state(downlight: int | None = None, **_kwargs: Any) -> FanimationState:
        return FanimationState(downlight=downlight if downlight is not None else 0)

    mock_coordinator = MagicMock()
    mock_coordinator.device = MagicMock()
    mock_coordinator.device.mac = "AA:BB:CC:DD:EE:FF"
    mock_coordinator.device.name = "Test Fan"
    mock_coordinator.device.async_set_state = AsyncMock(side_effect=_echo_state)
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


class TestLastBrightnessBookkeeping:
    """``_last_brightness`` must reflect what the *hardware confirmed*, not what
    was requested — the same lesson as the fan's ``_last_speed`` (Issue #1).
    """

    @pytest.mark.asyncio
    async def test_last_brightness_synced_to_verified_response(self) -> None:
        light, _ = _make_light()
        await light.async_turn_on(**{"brightness": 128})  # HA 128 → fan 50
        assert light._last_brightness == 50

    @pytest.mark.asyncio
    async def test_last_brightness_not_updated_on_communication_failure(self) -> None:
        """A None response (BLE failure) must not pin an unapplied value."""
        light, coord = _make_light()
        light._last_brightness = 75
        coord.device.async_set_state = AsyncMock(return_value=None)

        await light.async_turn_on(**{"brightness": 255})

        assert light._last_brightness == 75

    @pytest.mark.asyncio
    async def test_last_brightness_not_updated_when_hardware_reports_off(self) -> None:
        """A verified 'light off' response must not become the last-used level."""
        light, coord = _make_light()
        light._last_brightness = 75
        coord.device.async_set_state = AsyncMock(return_value=FanimationState(downlight=0))

        await light.async_turn_on(**{"brightness": 255})

        assert light._last_brightness == 75

    def test_brightness_getter_has_no_side_effects(self) -> None:
        """Reading ``brightness`` must not mutate ``_last_brightness`` — RF
        tracking lives in the coordinator-update hook, not the getter."""
        light, coord = _make_light()
        light._last_brightness = 75
        coord.data = FanimationState(downlight=22)

        assert light.brightness == round(22 * 255 / DOWNLIGHT_MAX)
        assert light._last_brightness == 75

    def test_coordinator_update_tracks_rf_remote_brightness(self) -> None:
        """A poll showing a non-zero brightness (e.g. set via RF remote) becomes
        the new last-used value; an off state leaves it alone."""
        light, coord = _make_light()
        light.async_write_ha_state = MagicMock()
        light._last_brightness = 75

        coord.data = FanimationState(downlight=22)
        light._handle_coordinator_update()
        assert light._last_brightness == 22

        coord.data = FanimationState(downlight=0)
        light._handle_coordinator_update()
        assert light._last_brightness == 22  # off does not clobber last-used
        assert light.async_write_ha_state.call_count == 2
