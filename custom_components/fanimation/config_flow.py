"""Config flow for Fanimation BLE integration."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from bleak_retry_connector import BleakClientWithServiceCache, establish_connection
from homeassistant.components import bluetooth
from homeassistant.components.bluetooth import BluetoothServiceInfoBleak
from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlowWithConfigEntry
from homeassistant.const import CONF_MAC, CONF_NAME
from homeassistant.data_entry_flow import section
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .const import (
    CHAR_NOTIFY,
    CHAR_WRITE,
    CONF_DEFAULT_BRIGHTNESS,
    CONF_DEFAULT_SPEED,
    CONF_NOTIFY_ON_DISCONNECT,
    CONF_UNAVAILABLE_THRESHOLD,
    DEFAULT_BRIGHTNESS_LAST_USED,
    DEFAULT_NOTIFY_ON_DISCONNECT,
    DEFAULT_SPEED_HIGH,
    DEFAULT_SPEED_LAST_USED,
    DEFAULT_SPEED_LOW,
    DEFAULT_SPEED_MEDIUM,
    DEFAULT_UNAVAILABLE_THRESHOLD,
    DOMAIN,
    LOGGER,
    MAX_UNAVAILABLE_THRESHOLD,
)

SERVICE_UUID = "0000e000-0000-1000-8000-00805f9b34fb"


class FanimationConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Fanimation BLE Ceiling Fan."""

    VERSION = 1

    @staticmethod
    def async_get_options_flow(config_entry: ConfigEntry) -> FanimationOptionsFlow:
        """Return the options flow handler."""
        return FanimationOptionsFlow(config_entry)

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._discovery_info: BluetoothServiceInfoBleak | None = None
        self._mac: str | None = None
        self._discovered_name: str | None = None

    async def _async_validate_device(self, mac: str) -> bool:
        """Connect to the fan and verify expected GATT characteristics exist.

        Returns True if the device looks like a Fanimation BTCR9.
        This is the test-before-configure check.
        """
        ble_device = bluetooth.async_ble_device_from_address(self.hass, mac.upper(), connectable=True)
        if not ble_device:
            return False

        try:
            client = await establish_connection(
                BleakClientWithServiceCache,
                ble_device,
                name="config_flow_validation",
                max_attempts=2,
            )
            try:
                # Verify the expected service and characteristics exist
                services = client.services
                write_char = services.get_characteristic(CHAR_WRITE)
                notify_char = services.get_characteristic(CHAR_NOTIFY)
                if write_char is None or notify_char is None:
                    LOGGER.debug(
                        "Device %s missing expected characteristics (write=%s, notify=%s)",
                        mac,
                        write_char,
                        notify_char,
                    )
                    return False
                return True
            finally:
                await client.disconnect()
        except Exception as err:
            LOGGER.debug("Validation connect to %s failed: %s", mac, err)
            return False

    async def async_step_bluetooth(self, discovery_info: BluetoothServiceInfoBleak) -> ConfigFlowResult:
        """Handle Bluetooth discovery."""
        LOGGER.debug(
            "Bluetooth discovery: %s (%s)",
            discovery_info.name,
            discovery_info.address,
        )

        self._discovery_info = discovery_info
        self._mac = discovery_info.address
        self._discovered_name = discovery_info.name or "Fanimation Fan"

        # Set unique ID to MAC address — prevents duplicates
        await self.async_set_unique_id(self._mac.upper())
        self._abort_if_unique_id_configured()

        # Validate the device has the expected GATT characteristics
        # (prevents false positives from other devices named "CeilingFan")
        if not await self._async_validate_device(self._mac):
            return self.async_abort(reason="not_fanimation")

        # Show confirmation to user
        self.context["title_placeholders"] = {
            "name": self._discovered_name,
            "mac": self._mac,
        }
        return await self.async_step_bluetooth_confirm()

    async def async_step_bluetooth_confirm(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Confirm Bluetooth discovery."""
        if user_input is not None:
            name = user_input.get(CONF_NAME, self._discovered_name)
            return self.async_create_entry(
                title=name,
                data={
                    CONF_MAC: self._mac,
                    CONF_NAME: name,
                },
            )

        return self.async_show_form(
            step_id="bluetooth_confirm",
            description_placeholders={
                "name": self._discovered_name,
                "mac": self._mac,
            },
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_NAME, default=self._discovered_name): str,
                }
            ),
        )

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Handle manual setup."""
        errors: dict[str, str] = {}

        if user_input is not None:
            mac = user_input[CONF_MAC].upper()
            name = user_input[CONF_NAME]

            # Set unique ID to prevent duplicates
            await self.async_set_unique_id(mac)
            self._abort_if_unique_id_configured()

            # Test-before-configure: verify the device is reachable
            # and has the expected GATT characteristics
            if not await self._async_validate_device(mac):
                errors["base"] = "cannot_connect"
            else:
                return self.async_create_entry(
                    title=name,
                    data={
                        CONF_MAC: mac,
                        CONF_NAME: name,
                    },
                )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_MAC): vol.All(
                        str,
                        vol.Match(r"^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$"),
                    ),
                    vol.Required(CONF_NAME, default="Fanimation Fan"): str,
                }
            ),
            errors=errors,
        )


class FanimationOptionsFlow(OptionsFlowWithConfigEntry):
    """Handle options for Fanimation BLE."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Manage the options."""
        if user_input is not None:
            # Flatten sections into a single options dict
            flat = {}
            flat.update(user_input.get("defaults", {}))
            flat.update(user_input.get("connection", {}))
            # NumberSelector returns float; cast to int for type safety
            if CONF_DEFAULT_BRIGHTNESS in flat:
                flat[CONF_DEFAULT_BRIGHTNESS] = int(flat[CONF_DEFAULT_BRIGHTNESS])
            if CONF_UNAVAILABLE_THRESHOLD in flat:
                flat[CONF_UNAVAILABLE_THRESHOLD] = int(flat[CONF_UNAVAILABLE_THRESHOLD])
            return self.async_create_entry(data=flat)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required("defaults"): section(
                        self._defaults_section_schema(),
                        {"collapsed": False},
                    ),
                    vol.Required("connection"): section(
                        self._connection_section_schema(),
                        {"collapsed": False},
                    ),
                }
            ),
        )

    def _defaults_section_schema(self) -> vol.Schema:
        """Build schema for fan & light defaults section."""
        return vol.Schema(
            {
                vol.Required(
                    CONF_DEFAULT_SPEED,
                    default=self.options.get(CONF_DEFAULT_SPEED, DEFAULT_SPEED_LAST_USED),
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=[
                            DEFAULT_SPEED_LAST_USED,
                            DEFAULT_SPEED_LOW,
                            DEFAULT_SPEED_MEDIUM,
                            DEFAULT_SPEED_HIGH,
                        ],
                        translation_key=CONF_DEFAULT_SPEED,
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Required(
                    CONF_DEFAULT_BRIGHTNESS,
                    default=self.options.get(CONF_DEFAULT_BRIGHTNESS, DEFAULT_BRIGHTNESS_LAST_USED),
                ): NumberSelector(NumberSelectorConfig(min=0, max=100, step=1, mode=NumberSelectorMode.SLIDER)),
            }
        )

    def _connection_section_schema(self) -> vol.Schema:
        """Build schema for connection & availability section."""
        return vol.Schema(
            {
                vol.Required(
                    CONF_NOTIFY_ON_DISCONNECT,
                    default=self.options.get(CONF_NOTIFY_ON_DISCONNECT, DEFAULT_NOTIFY_ON_DISCONNECT),
                ): bool,
                vol.Required(
                    CONF_UNAVAILABLE_THRESHOLD,
                    default=self.options.get(CONF_UNAVAILABLE_THRESHOLD, DEFAULT_UNAVAILABLE_THRESHOLD),
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=0,
                        max=MAX_UNAVAILABLE_THRESHOLD,
                        step=1,
                        mode=NumberSelectorMode.BOX,
                    )
                ),
            }
        )
