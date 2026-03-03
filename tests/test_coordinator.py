"""Tests for the Fanimation coordinator tiered availability logic.

These are pure unit tests that mock the device layer and test the
coordinator's failure counting, state preservation, and notification
logic. They run on all platforms (no HA test harness required).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.fanimation.const import (
    CONF_NOTIFY_ON_DISCONNECT,
    CONF_UNAVAILABLE_THRESHOLD,
    DEFAULT_NOTIFY_ON_DISCONNECT,
    DEFAULT_UNAVAILABLE_THRESHOLD,
)
from custom_components.fanimation.device import FanimationState


def _make_coordinator(
    unavailable_threshold: int = DEFAULT_UNAVAILABLE_THRESHOLD,
    notify_on_disconnect: bool = DEFAULT_NOTIFY_ON_DISCONNECT,
):
    """Create a coordinator with mocked HA and device for unit testing.

    Returns (coordinator, mock_device, mock_hass).
    """
    from custom_components.fanimation.coordinator import FanimationCoordinator

    mock_hass = MagicMock()
    mock_hass.services = MagicMock()
    mock_hass.services.async_call = AsyncMock()

    mock_device = MagicMock()
    mock_device.mac = "AA:BB:CC:DD:EE:FF"
    mock_device.name = "Test Fan"
    mock_device.async_get_status = AsyncMock()
    mock_device.disconnect = AsyncMock()

    mock_entry = MagicMock()
    mock_entry.options = {
        CONF_UNAVAILABLE_THRESHOLD: unavailable_threshold,
        CONF_NOTIFY_ON_DISCONNECT: notify_on_disconnect,
    }

    coordinator = FanimationCoordinator(mock_hass, mock_device, mock_entry)
    return coordinator, mock_device, mock_hass


class TestTieredAvailability:
    """Tests for the tiered availability logic."""

    @pytest.mark.asyncio
    async def test_success_resets_failures(self) -> None:
        coordinator, mock_device, _ = _make_coordinator()
        mock_device.async_get_status.return_value = FanimationState(speed=1)

        result = await coordinator._async_update_data()

        assert result.speed == 1
        assert coordinator.connection_failures == 0

    @pytest.mark.asyncio
    async def test_failure_below_threshold_returns_last_state(self) -> None:
        coordinator, mock_device, _ = _make_coordinator(unavailable_threshold=12)
        coordinator.data = FanimationState(speed=2, downlight=50)
        mock_device.async_get_status.side_effect = Exception("BLE timeout")

        result = await coordinator._async_update_data()

        assert result.speed == 2
        assert result.downlight == 50
        assert coordinator.connection_failures == 1

    @pytest.mark.asyncio
    async def test_failure_at_threshold_raises_update_failed(self) -> None:
        from homeassistant.helpers.update_coordinator import UpdateFailed

        coordinator, mock_device, _ = _make_coordinator(unavailable_threshold=3)
        coordinator.data = FanimationState(speed=1)
        mock_device.async_get_status.side_effect = Exception("BLE timeout")

        for _i in range(2):
            result = await coordinator._async_update_data()
            assert result is not None

        with pytest.raises(UpdateFailed):
            await coordinator._async_update_data()

        assert coordinator.connection_failures == 3

    @pytest.mark.asyncio
    async def test_threshold_zero_never_raises(self) -> None:
        coordinator, mock_device, _ = _make_coordinator(unavailable_threshold=0)
        coordinator.data = FanimationState(speed=1)
        mock_device.async_get_status.side_effect = Exception("BLE timeout")

        for _ in range(100):
            result = await coordinator._async_update_data()
            assert result is not None

        assert coordinator.connection_failures == 100

    @pytest.mark.asyncio
    async def test_no_prior_state_always_raises(self) -> None:
        from homeassistant.helpers.update_coordinator import UpdateFailed

        coordinator, mock_device, _ = _make_coordinator(unavailable_threshold=0)
        mock_device.async_get_status.side_effect = Exception("BLE timeout")

        with pytest.raises(UpdateFailed):
            await coordinator._async_update_data()

    @pytest.mark.asyncio
    async def test_success_after_failures_resets_counter(self) -> None:
        coordinator, mock_device, _ = _make_coordinator(unavailable_threshold=12)
        coordinator.data = FanimationState(speed=1)

        mock_device.async_get_status.side_effect = Exception("BLE timeout")
        for _ in range(5):
            await coordinator._async_update_data()
        assert coordinator.connection_failures == 5

        mock_device.async_get_status.side_effect = None
        mock_device.async_get_status.return_value = FanimationState(speed=3)
        result = await coordinator._async_update_data()

        assert result.speed == 3
        assert coordinator.connection_failures == 0

    @pytest.mark.asyncio
    async def test_none_response_below_threshold_returns_last_state(self) -> None:
        coordinator, mock_device, _ = _make_coordinator(unavailable_threshold=12)
        coordinator.data = FanimationState(speed=2)
        mock_device.async_get_status.return_value = None

        result = await coordinator._async_update_data()

        assert result.speed == 2
        assert coordinator.connection_failures == 1

    @pytest.mark.asyncio
    async def test_none_response_at_threshold_raises(self) -> None:
        from homeassistant.helpers.update_coordinator import UpdateFailed

        coordinator, mock_device, _ = _make_coordinator(unavailable_threshold=2)
        coordinator.data = FanimationState(speed=1)
        mock_device.async_get_status.return_value = None

        await coordinator._async_update_data()  # failure 1

        with pytest.raises(UpdateFailed):
            await coordinator._async_update_data()  # failure 2 = threshold


class TestPersistentNotification:
    """Tests for the persistent notification logic."""

    @pytest.mark.asyncio
    async def test_notification_fires_on_first_failure(self) -> None:
        coordinator, mock_device, mock_hass = _make_coordinator(notify_on_disconnect=True)
        coordinator.data = FanimationState(speed=1)
        mock_device.async_get_status.side_effect = Exception("BLE timeout")

        await coordinator._async_update_data()

        mock_hass.services.async_call.assert_called_once()
        call_args = mock_hass.services.async_call.call_args
        assert call_args[0][0] == "persistent_notification"
        assert call_args[0][1] == "create"

    @pytest.mark.asyncio
    async def test_notification_does_not_refire_on_subsequent_failures(self) -> None:
        coordinator, mock_device, mock_hass = _make_coordinator(notify_on_disconnect=True)
        coordinator.data = FanimationState(speed=1)
        mock_device.async_get_status.side_effect = Exception("BLE timeout")

        await coordinator._async_update_data()
        await coordinator._async_update_data()

        create_calls = [
            c for c in mock_hass.services.async_call.call_args_list
            if c[0][1] == "create"
        ]
        assert len(create_calls) == 1

    @pytest.mark.asyncio
    async def test_notification_dismissed_on_recovery(self) -> None:
        coordinator, mock_device, mock_hass = _make_coordinator(notify_on_disconnect=True)
        coordinator.data = FanimationState(speed=1)

        mock_device.async_get_status.side_effect = Exception("BLE timeout")
        await coordinator._async_update_data()

        mock_device.async_get_status.side_effect = None
        mock_device.async_get_status.return_value = FanimationState(speed=1)
        await coordinator._async_update_data()

        dismiss_calls = [
            c for c in mock_hass.services.async_call.call_args_list
            if c[0][1] == "dismiss"
        ]
        assert len(dismiss_calls) == 1

    @pytest.mark.asyncio
    async def test_notification_disabled_does_not_fire(self) -> None:
        coordinator, mock_device, mock_hass = _make_coordinator(notify_on_disconnect=False)
        coordinator.data = FanimationState(speed=1)
        mock_device.async_get_status.side_effect = Exception("BLE timeout")

        await coordinator._async_update_data()

        mock_hass.services.async_call.assert_not_called()
