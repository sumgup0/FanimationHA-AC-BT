"""Tests for the Fanimation BLE options flow.

Requires the full HA test harness (Linux CI only).
"""

from __future__ import annotations

import sys

import pytest

pytestmark = pytest.mark.skipif(
    sys.platform == "win32",
    reason="Options-flow tests require the full HA test framework (Linux CI only)",
)

from homeassistant.const import CONF_MAC, CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.fanimation.const import (
    CONF_DEFAULT_BRIGHTNESS,
    CONF_DEFAULT_SPEED,
    CONF_NOTIFY_ON_DISCONNECT,
    CONF_UNAVAILABLE_THRESHOLD,
    DEFAULT_BRIGHTNESS_LAST_USED,
    DEFAULT_NOTIFY_ON_DISCONNECT,
    DEFAULT_SPEED_LAST_USED,
    DEFAULT_UNAVAILABLE_THRESHOLD,
    DOMAIN,
)

from .conftest import TEST_MAC, TEST_NAME


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Let the HA test harness discover our custom component."""
    yield


@pytest.fixture
def mock_entry(hass: HomeAssistant) -> MockConfigEntry:
    """Create a mock config entry for testing options flow."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=TEST_MAC.upper(),
        data={CONF_MAC: TEST_MAC.upper(), CONF_NAME: TEST_NAME},
    )
    entry.add_to_hass(hass)
    return entry


class TestOptionsFlow:
    """Tests for the options flow."""

    async def test_options_flow_shows_form(
        self, hass: HomeAssistant, mock_entry: MockConfigEntry
    ) -> None:
        """Options flow should show init form."""
        result = await hass.config_entries.options.async_init(mock_entry.entry_id)
        assert result["type"] is FlowResultType.FORM
        assert result["step_id"] == "init"

    async def test_options_flow_saves_defaults(
        self, hass: HomeAssistant, mock_entry: MockConfigEntry
    ) -> None:
        """Submitting options should save them to entry.options."""
        result = await hass.config_entries.options.async_init(mock_entry.entry_id)
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            user_input={
                "defaults": {
                    CONF_DEFAULT_SPEED: "medium",
                    CONF_DEFAULT_BRIGHTNESS: 75,
                },
                "connection": {
                    CONF_NOTIFY_ON_DISCONNECT: False,
                    CONF_UNAVAILABLE_THRESHOLD: 24,
                },
            },
        )
        assert result["type"] is FlowResultType.CREATE_ENTRY
        assert mock_entry.options[CONF_DEFAULT_SPEED] == "medium"
        assert mock_entry.options[CONF_DEFAULT_BRIGHTNESS] == 75
        assert mock_entry.options[CONF_NOTIFY_ON_DISCONNECT] is False
        assert mock_entry.options[CONF_UNAVAILABLE_THRESHOLD] == 24

    async def test_options_flow_preserves_defaults_when_unchanged(
        self, hass: HomeAssistant, mock_entry: MockConfigEntry
    ) -> None:
        """Submitting the form without changes should use defaults."""
        result = await hass.config_entries.options.async_init(mock_entry.entry_id)
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            user_input={
                "defaults": {
                    CONF_DEFAULT_SPEED: DEFAULT_SPEED_LAST_USED,
                    CONF_DEFAULT_BRIGHTNESS: DEFAULT_BRIGHTNESS_LAST_USED,
                },
                "connection": {
                    CONF_NOTIFY_ON_DISCONNECT: DEFAULT_NOTIFY_ON_DISCONNECT,
                    CONF_UNAVAILABLE_THRESHOLD: DEFAULT_UNAVAILABLE_THRESHOLD,
                },
            },
        )
        assert result["type"] is FlowResultType.CREATE_ENTRY
        assert mock_entry.options[CONF_DEFAULT_SPEED] == DEFAULT_SPEED_LAST_USED
        assert mock_entry.options[CONF_DEFAULT_BRIGHTNESS] == DEFAULT_BRIGHTNESS_LAST_USED
