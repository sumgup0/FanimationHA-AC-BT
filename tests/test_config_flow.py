"""Tests for the Fanimation BLE config flow.

These tests verify the Bluetooth discovery flow, manual MAC entry,
duplicate-MAC abort, and unreachable-device error handling.

**Requires the full HA test harness (Linux CI only).**
``pytest-homeassistant-custom-component`` provides the ``hass`` fixture
and patches HA internals; it does not load on Windows (``fcntl`` missing).
"""

from __future__ import annotations

import sys

import pytest

# Skip this entire module on Windows — the HA test harness requires Linux.
pytestmark = pytest.mark.skipif(
    sys.platform == "win32",
    reason="Config-flow tests require the full HA test framework (Linux CI only)",
)

from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant import config_entries
from homeassistant.components.bluetooth import BluetoothServiceInfoBleak
from homeassistant.const import CONF_MAC, CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.fanimation.const import CONF_SPEED_COUNT, DOMAIN

from .conftest import TEST_MAC, TEST_NAME


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Let the HA test harness discover our custom component."""
    yield


@pytest.fixture(autouse=True)
async def mock_bluetooth_deps(hass: HomeAssistant):
    """Mark bluetooth dependencies as already set up.

    Our manifest declares ``dependencies: ["bluetooth", "bluetooth_adapters"]``.
    Without this, HA tries to fully initialise those integrations during
    ``flow.async_init``, which fails in CI (no BLE adapter hardware).
    Adding them to ``hass.config.components`` tells the dependency checker
    they are already loaded — so it skips their setup entirely.
    """
    hass.config.components.add("bluetooth")
    hass.config.components.add("bluetooth_adapters")
    yield


# Fake Bluetooth discovery info matching a "CeilingFan" device
FAKE_DISCOVERY = BluetoothServiceInfoBleak(
    name="CeilingFan",
    address=TEST_MAC,
    rssi=-60,
    manufacturer_data={},
    service_data={},
    service_uuids=["0000e000-0000-1000-8000-00805f9b34fb"],
    source="local",
    device=MagicMock(),
    advertisement=MagicMock(),
    connectable=True,
    time=0,
    tx_power=None,
)


def _mock_services_with_chars() -> MagicMock:
    """Create a mock BleakGATTServiceCollection with our expected characteristics."""
    services = MagicMock()
    services.get_characteristic = MagicMock(return_value=MagicMock())
    return services


def _mock_services_without_chars() -> MagicMock:
    """Create a mock BleakGATTServiceCollection missing our characteristics."""
    services = MagicMock()
    services.get_characteristic = MagicMock(return_value=None)
    return services


# ---------------------------------------------------------------------------
# Bluetooth discovery flow
# ---------------------------------------------------------------------------


class TestBluetoothDiscovery:
    """Tests for the Bluetooth auto-discovery flow."""

    async def test_discovery_shows_confirm_form(self, hass: HomeAssistant) -> None:
        """Bluetooth discovery should show a confirmation form."""
        with (
            patch(
                "custom_components.fanimation.config_flow.bluetooth.async_ble_device_from_address",
                return_value=MagicMock(),
            ),
            patch(
                "custom_components.fanimation.config_flow.establish_connection",
            ) as mock_conn,
        ):
            # Mock the BLE client with valid GATT characteristics
            mock_client = AsyncMock()
            mock_client.services = _mock_services_with_chars()
            mock_client.disconnect = AsyncMock()
            mock_conn.return_value = mock_client

            result = await hass.config_entries.flow.async_init(
                DOMAIN,
                context={"source": config_entries.SOURCE_BLUETOOTH},
                data=FAKE_DISCOVERY,
            )

        assert result["type"] is FlowResultType.FORM
        assert result["step_id"] == "bluetooth_confirm"

    async def test_discovery_confirm_creates_entry(self, hass: HomeAssistant) -> None:
        """Confirming Bluetooth discovery should create a config entry."""
        with (
            patch(
                "custom_components.fanimation.config_flow.bluetooth.async_ble_device_from_address",
                return_value=MagicMock(),
            ),
            patch(
                "custom_components.fanimation.config_flow.establish_connection",
            ) as mock_conn,
        ):
            mock_client = AsyncMock()
            mock_client.services = _mock_services_with_chars()
            mock_client.disconnect = AsyncMock()
            mock_conn.return_value = mock_client

            # Start the discovery flow
            result = await hass.config_entries.flow.async_init(
                DOMAIN,
                context={"source": config_entries.SOURCE_BLUETOOTH},
                data=FAKE_DISCOVERY,
            )

            # Submit the confirmation form with a custom name
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"],
                user_input={CONF_NAME: "Office Fan", CONF_SPEED_COUNT: "3"},
            )

        assert result["type"] is FlowResultType.CREATE_ENTRY
        assert result["title"] == "Office Fan"
        assert result["data"][CONF_MAC] == TEST_MAC
        assert result["data"][CONF_NAME] == "Office Fan"
        assert result["data"][CONF_SPEED_COUNT] == 3  # coerced to int by schema

    async def test_discovery_not_fanimation_aborts(self, hass: HomeAssistant) -> None:
        """Discovery of a non-Fanimation device should abort."""
        with (
            patch(
                "custom_components.fanimation.config_flow.bluetooth.async_ble_device_from_address",
                return_value=MagicMock(),
            ),
            patch(
                "custom_components.fanimation.config_flow.establish_connection",
            ) as mock_conn,
        ):
            # Mock client WITHOUT the expected GATT characteristics
            mock_client = AsyncMock()
            mock_client.services = _mock_services_without_chars()
            mock_client.disconnect = AsyncMock()
            mock_conn.return_value = mock_client

            result = await hass.config_entries.flow.async_init(
                DOMAIN,
                context={"source": config_entries.SOURCE_BLUETOOTH},
                data=FAKE_DISCOVERY,
            )

        assert result["type"] is FlowResultType.ABORT
        assert result["reason"] == "not_fanimation"


# ---------------------------------------------------------------------------
# Manual MAC entry flow
# ---------------------------------------------------------------------------


class TestManualEntry:
    """Tests for the manual MAC address entry flow."""

    async def test_manual_shows_form(self, hass: HomeAssistant) -> None:
        """User step should show the manual entry form."""
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_USER},
        )
        assert result["type"] is FlowResultType.FORM
        assert result["step_id"] == "user"

    async def test_manual_valid_mac_creates_entry(self, hass: HomeAssistant) -> None:
        """Valid MAC with reachable device should create a config entry."""
        with (
            patch(
                "custom_components.fanimation.config_flow.bluetooth.async_ble_device_from_address",
                return_value=MagicMock(),
            ),
            patch(
                "custom_components.fanimation.config_flow.establish_connection",
            ) as mock_conn,
        ):
            mock_client = AsyncMock()
            mock_client.services = _mock_services_with_chars()
            mock_client.disconnect = AsyncMock()
            mock_conn.return_value = mock_client

            result = await hass.config_entries.flow.async_init(
                DOMAIN,
                context={"source": config_entries.SOURCE_USER},
            )

            result = await hass.config_entries.flow.async_configure(
                result["flow_id"],
                user_input={
                    CONF_MAC: TEST_MAC,
                    CONF_NAME: TEST_NAME,
                    CONF_SPEED_COUNT: "6",
                },
            )

        assert result["type"] is FlowResultType.CREATE_ENTRY
        assert result["title"] == TEST_NAME
        assert result["data"][CONF_MAC] == TEST_MAC.upper()
        assert result["data"][CONF_SPEED_COUNT] == 6

    async def test_manual_unreachable_device_shows_error(self, hass: HomeAssistant) -> None:
        """Unreachable device should show cannot_connect error."""
        with patch(
            "custom_components.fanimation.config_flow.bluetooth.async_ble_device_from_address",
            return_value=None,  # device not found
        ):
            result = await hass.config_entries.flow.async_init(
                DOMAIN,
                context={"source": config_entries.SOURCE_USER},
            )

            result = await hass.config_entries.flow.async_configure(
                result["flow_id"],
                user_input={
                    CONF_MAC: TEST_MAC,
                    CONF_NAME: TEST_NAME,
                    CONF_SPEED_COUNT: "3",
                },
            )

        assert result["type"] is FlowResultType.FORM
        assert result["errors"] == {"base": "cannot_connect"}

    async def test_manual_connection_exception_shows_error(self, hass: HomeAssistant) -> None:
        """BLE connection failure should show cannot_connect error."""
        with (
            patch(
                "custom_components.fanimation.config_flow.bluetooth.async_ble_device_from_address",
                return_value=MagicMock(),
            ),
            patch(
                "custom_components.fanimation.config_flow.establish_connection",
                side_effect=Exception("BLE connect timeout"),
            ),
        ):
            result = await hass.config_entries.flow.async_init(
                DOMAIN,
                context={"source": config_entries.SOURCE_USER},
            )

            result = await hass.config_entries.flow.async_configure(
                result["flow_id"],
                user_input={
                    CONF_MAC: TEST_MAC,
                    CONF_NAME: TEST_NAME,
                    CONF_SPEED_COUNT: "3",
                },
            )

        assert result["type"] is FlowResultType.FORM
        assert result["errors"] == {"base": "cannot_connect"}


# ---------------------------------------------------------------------------
# Duplicate MAC prevention
# ---------------------------------------------------------------------------


class TestDuplicatePrevention:
    """Tests for preventing duplicate config entries."""

    async def test_duplicate_mac_aborts_discovery(self, hass: HomeAssistant) -> None:
        """Discovery of an already-configured MAC should abort."""
        # Create an existing entry for the same MAC
        existing = MockConfigEntry(
            domain=DOMAIN,
            unique_id=TEST_MAC.upper(),
            data={CONF_MAC: TEST_MAC.upper(), CONF_NAME: TEST_NAME},
        )
        existing.add_to_hass(hass)

        with (
            patch(
                "custom_components.fanimation.config_flow.bluetooth.async_ble_device_from_address",
                return_value=MagicMock(),
            ),
            patch(
                "custom_components.fanimation.config_flow.establish_connection",
            ) as mock_conn,
        ):
            mock_client = AsyncMock()
            mock_client.services = _mock_services_with_chars()
            mock_client.disconnect = AsyncMock()
            mock_conn.return_value = mock_client

            result = await hass.config_entries.flow.async_init(
                DOMAIN,
                context={"source": config_entries.SOURCE_BLUETOOTH},
                data=FAKE_DISCOVERY,
            )

        assert result["type"] is FlowResultType.ABORT
        assert result["reason"] == "already_configured"

    async def test_duplicate_mac_aborts_manual(self, hass: HomeAssistant) -> None:
        """Manual entry of an already-configured MAC should abort."""
        # Create an existing entry for the same MAC
        existing = MockConfigEntry(
            domain=DOMAIN,
            unique_id=TEST_MAC.upper(),
            data={CONF_MAC: TEST_MAC.upper(), CONF_NAME: TEST_NAME},
        )
        existing.add_to_hass(hass)

        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_USER},
        )

        with patch(
            "custom_components.fanimation.config_flow.bluetooth.async_ble_device_from_address",
            return_value=MagicMock(),
        ):
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"],
                user_input={
                    CONF_MAC: TEST_MAC,
                    CONF_NAME: TEST_NAME,
                    CONF_SPEED_COUNT: "3",
                },
            )

        assert result["type"] is FlowResultType.ABORT
        assert result["reason"] == "already_configured"
