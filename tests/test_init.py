"""Tests for the integration setup/unload entry points (__init__.py).

Pure unit tests: HA's config-entry machinery is mocked and the coordinator's
first refresh is patched, so ``async_setup_entry`` exercises only its own
orchestration — no real BLE, no HA refresh scheduler.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.const import CONF_MAC, CONF_NAME

from custom_components.fanimation import (
    _async_options_updated,
    async_setup_entry,
    async_unload_entry,
)
from custom_components.fanimation.const import PLATFORMS
from custom_components.fanimation.coordinator import FanimationCoordinator

from .conftest import TEST_MAC, TEST_NAME


def _make_entry():
    """Build a config entry shaped like a real one for setup/unload."""
    entry = MagicMock()
    entry.data = {CONF_MAC: TEST_MAC, CONF_NAME: TEST_NAME}
    entry.entry_id = "test_entry"
    entry.title = TEST_NAME
    return entry


class TestSetupEntry:
    @pytest.mark.asyncio
    async def test_setup_creates_coordinator_and_forwards_platforms(self) -> None:
        hass = MagicMock()
        hass.config_entries.async_forward_entry_setups = AsyncMock()
        entry = _make_entry()

        with patch.object(
            FanimationCoordinator, "async_config_entry_first_refresh", new_callable=AsyncMock
        ) as mock_first_refresh:
            result = await async_setup_entry(hass, entry)

        assert result is True
        # Real coordinator constructed and stored on the entry for platform access.
        assert isinstance(entry.runtime_data, FanimationCoordinator)
        mock_first_refresh.assert_awaited_once()
        # Our options-update listener is registered (reload-on-change) and its
        # unsub wired for cleanup. Note async_on_unload is also called by HA's
        # DataUpdateCoordinator for its own async_shutdown, so assert our call
        # specifically rather than the total count.
        entry.add_update_listener.assert_called_once_with(_async_options_updated)
        entry.async_on_unload.assert_any_call(entry.add_update_listener.return_value)
        # Platforms forwarded exactly once with the integration's PLATFORMS.
        hass.config_entries.async_forward_entry_setups.assert_awaited_once_with(entry, PLATFORMS)


class TestOptionsUpdated:
    @pytest.mark.asyncio
    async def test_options_update_triggers_reload(self) -> None:
        hass = MagicMock()
        hass.config_entries.async_reload = AsyncMock()
        entry = _make_entry()

        await _async_options_updated(hass, entry)

        hass.config_entries.async_reload.assert_awaited_once_with(entry.entry_id)


class TestUnloadEntry:
    @pytest.mark.asyncio
    async def test_unload_success_disconnects_device(self) -> None:
        hass = MagicMock()
        hass.config_entries.async_unload_platforms = AsyncMock(return_value=True)
        entry = _make_entry()
        entry.runtime_data = MagicMock()
        entry.runtime_data.device.disconnect = AsyncMock()

        result = await async_unload_entry(hass, entry)

        assert result is True
        hass.config_entries.async_unload_platforms.assert_awaited_once_with(entry, PLATFORMS)
        entry.runtime_data.device.disconnect.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_unload_failure_skips_disconnect(self) -> None:
        hass = MagicMock()
        hass.config_entries.async_unload_platforms = AsyncMock(return_value=False)
        entry = _make_entry()
        entry.runtime_data = MagicMock()
        entry.runtime_data.device.disconnect = AsyncMock()

        result = await async_unload_entry(hass, entry)

        assert result is False
        entry.runtime_data.device.disconnect.assert_not_awaited()
