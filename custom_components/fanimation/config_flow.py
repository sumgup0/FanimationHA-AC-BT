"""Config flow for Fanimation BLE integration."""

from __future__ import annotations

import re
from typing import Any

import voluptuous as vol
from bleak_retry_connector import BleakClientWithServiceCache, establish_connection
from homeassistant.components import bluetooth
from homeassistant.components.bluetooth import BluetoothServiceInfoBleak
from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_MAC, CONF_NAME
from homeassistant.core import callback
from homeassistant.data_entry_flow import section
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import format_mac
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
    CONF_SPEED_COUNT,
    CONF_SUPPORTS_REVERSE,
    CONF_UNAVAILABLE_THRESHOLD,
    DEFAULT_BRIGHTNESS_LAST_USED,
    DEFAULT_NOTIFY_ON_DISCONNECT,
    DEFAULT_SPEED_COUNT,
    DEFAULT_SPEED_HIGH,
    DEFAULT_SPEED_LAST_USED,
    DEFAULT_SPEED_LOW,
    DEFAULT_SPEED_MEDIUM,
    DEFAULT_UNAVAILABLE_THRESHOLD,
    DOMAIN,
    LOGGER,
    MAX_SPEED_COUNT,
    MAX_UNAVAILABLE_THRESHOLD,
    MIN_SPEED_COUNT,
    SPEED_COUNT_COMMON,
    fan_type_supports_reverse,
)

SERVICE_UUID = "0000e000-0000-1000-8000-00805f9b34fb"

# Canonical MAC form after format_mac() normalization: lowercase colon-separated.
_MAC_RE = re.compile(r"^([0-9a-f]{2}:){5}[0-9a-f]{2}$")


def _normalize_mac(raw: str) -> str | None:
    """Normalise user MAC input to canonical uppercase colon form, or None if invalid.

    Accepts colon / dash / dot / bare-hex via ``format_mac``; validates the result
    against ``_MAC_RE`` before upper-casing. Shared by ``async_step_user`` and
    ``async_step_reconfigure`` so the validation lives in one place.
    """
    normalized = format_mac(raw.strip())
    if not _MAC_RE.match(normalized):
        return None
    return normalized.upper()


def _speed_count_field() -> vol.All:
    """Voluptuous validator for the speed-count form field.

    Renders as a dropdown of common values (1, 3, 6, 32) with ``custom_value=True``
    so users with unusual hardware can type any integer in [MIN, MAX]. Selector
    returns a string, so we coerce to int and range-check before persisting.

    Callers must pass form ``default`` values as ``str`` (e.g. ``str(DEFAULT_SPEED_COUNT)``)
    because the underlying SelectSelector compares defaults against its string options.
    """
    return vol.All(
        SelectSelector(
            SelectSelectorConfig(
                options=SPEED_COUNT_COMMON,
                custom_value=True,
                mode=SelectSelectorMode.DROPDOWN,
            )
        ),
        vol.Coerce(int),
        vol.Range(min=MIN_SPEED_COUNT, max=MAX_SPEED_COUNT),
    )


class FanimationConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Fanimation BLE Ceiling Fan."""

    VERSION = 1

    @staticmethod
    def async_get_options_flow(config_entry: ConfigEntry) -> FanimationOptionsFlow:
        """Return the options flow handler.

        No-arg construction: HA injects the entry, exposed via the
        ``OptionsFlow.config_entry`` property.
        """
        return FanimationOptionsFlow()

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._discovery_info: BluetoothServiceInfoBleak | None = None
        # Populated during Bluetooth discovery before async_step_bluetooth_confirm; "" until then.
        self._mac: str = ""
        self._discovered_name: str = ""

    async def _async_validate_device(self, mac: str) -> str | None:
        """Connect to the fan and verify expected GATT characteristics exist.

        Returns ``None`` when the device looks like a Fanimation BTCR9, else an
        error code: ``cannot_connect`` (not found or connection failed) versus
        ``not_fanimation`` (reachable but wrong GATT). The BTCR9 accepts only
        one BLE connection at a time, so a genuine fan that is busy with the
        FanSync app fails to *connect* — the distinction keeps it from being
        misreported as "not a Fanimation fan". This is the test-before-configure
        check.
        """
        ble_device = bluetooth.async_ble_device_from_address(self.hass, mac.upper(), connectable=True)
        if not ble_device:
            return "cannot_connect"

        try:
            client = await establish_connection(
                BleakClientWithServiceCache,
                ble_device,
                name="config_flow_validation",
                max_attempts=2,
            )
        except Exception as err:
            LOGGER.debug("Validation connect to %s failed: %s", mac, err)
            return "cannot_connect"

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
                return "not_fanimation"
            return None
        except Exception as err:
            LOGGER.debug("Validation of %s failed after connect: %s", mac, err)
            return "cannot_connect"
        finally:
            try:
                await client.disconnect()
            except Exception:  # noqa: S110
                pass  # Best-effort cleanup; the verdict above already stands

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
        if error := await self._async_validate_device(self._mac):
            return self.async_abort(reason=error)

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
                    CONF_SPEED_COUNT: user_input[CONF_SPEED_COUNT],
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
                    vol.Required(CONF_SPEED_COUNT, default=str(DEFAULT_SPEED_COUNT)): _speed_count_field(),
                }
            ),
        )

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Handle manual setup.

        MAC validation runs in the handler, not in the voluptuous schema:
        ``vol.Match`` is not JSON-serializable by ``voluptuous_serialize`` and
        causes the frontend to error when rendering the form (Issue #5).
        Accepting ``str`` in the schema and validating here also lets us
        normalize colon/dash/dot/bare-hex input via ``format_mac``.
        """
        errors: dict[str, str] = {}

        if user_input is not None:
            mac = _normalize_mac(user_input[CONF_MAC])
            if mac is None:
                errors[CONF_MAC] = "invalid_mac"
            else:
                name = user_input[CONF_NAME]

                # Set unique ID to prevent duplicates
                await self.async_set_unique_id(mac)
                self._abort_if_unique_id_configured()

                # Test-before-configure: verify the device is reachable
                # and has the expected GATT characteristics
                if error := await self._async_validate_device(mac):
                    errors["base"] = error
                else:
                    return self.async_create_entry(
                        title=name,
                        data={
                            CONF_MAC: mac,
                            CONF_NAME: name,
                            CONF_SPEED_COUNT: user_input[CONF_SPEED_COUNT],
                        },
                    )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_MAC): str,
                    vol.Required(CONF_NAME, default="Fanimation Fan"): str,
                    vol.Required(CONF_SPEED_COUNT, default=str(DEFAULT_SPEED_COUNT)): _speed_count_field(),
                }
            ),
            errors=errors,
        )

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Change the MAC / name of an existing entry without re-adding it.

        speed_count is intentionally not here — it is editable in the options flow.
        The MAC may change (fix a typo / replaced receiver); we re-validate the new
        address and block pointing at a fan that is already configured elsewhere.
        """
        reconfigure_entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}

        if user_input is not None:
            mac = _normalize_mac(user_input[CONF_MAC])
            if mac is None:
                errors[CONF_MAC] = "invalid_mac"
            else:
                name = user_input[CONF_NAME]
                if mac != reconfigure_entry.unique_id:
                    # MAC changed: re-key the entry and re-validate the new device.
                    await self.async_set_unique_id(mac)
                    self._abort_if_unique_id_configured()
                    if error := await self._async_validate_device(mac):
                        errors["base"] = error
                if not errors:
                    if mac != reconfigure_entry.unique_id:
                        self._async_migrate_mac_registry(reconfigure_entry, mac)
                    return self.async_update_reload_and_abort(
                        reconfigure_entry,
                        unique_id=mac,
                        title=name,
                        data_updates={CONF_MAC: mac, CONF_NAME: name},
                    )

        defaults = user_input or reconfigure_entry.data
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_MAC, default=defaults[CONF_MAC]): str,
                    vol.Required(CONF_NAME, default=defaults[CONF_NAME]): str,
                }
            ),
            errors=errors,
        )

    @callback
    def _async_migrate_mac_registry(self, entry: ConfigEntry, new_mac: str) -> None:
        """Re-key device and entity registry rows when reconfigure changes the MAC.

        Entity unique_ids (``{mac}_fan|_light|_timer``) and the device identity
        both embed the MAC. Without this migration a MAC change orphans the old
        device and its three entities and registers fresh ``_2``-suffixed ones,
        silently breaking automations, dashboards, and history that reference
        the fan.
        """
        old_mac = entry.data[CONF_MAC]
        entity_registry = er.async_get(self.hass)
        for domain, suffix in (("fan", "_fan"), ("light", "_light"), ("number", "_timer")):
            entity_id = entity_registry.async_get_entity_id(domain, DOMAIN, f"{old_mac}{suffix}")
            if entity_id:
                entity_registry.async_update_entity(entity_id, new_unique_id=f"{new_mac}{suffix}")
        device_registry = dr.async_get(self.hass)
        device = device_registry.async_get_device(identifiers={(DOMAIN, old_mac)})
        if device:
            device_registry.async_update_device(
                device.id,
                new_identifiers={(DOMAIN, new_mac)},
                new_connections={(dr.CONNECTION_BLUETOOTH, new_mac)},
            )


class FanimationOptionsFlow(OptionsFlow):
    """Handle options for Fanimation BLE.

    Subclasses plain ``OptionsFlow``: the ``OptionsFlowWithConfigEntry`` base
    is deprecated ("should not be referenced in new code", kept only for
    custom-integration back-compat) and this flow never needed its mutable
    options copy — all reads go straight to ``self.config_entry.options``.
    """

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
        current_speed_count = self.config_entry.options.get(
            CONF_SPEED_COUNT,
            self.config_entry.data.get(CONF_SPEED_COUNT, DEFAULT_SPEED_COUNT),
        )
        # Default the reverse toggle from the detected fan type (ON only for
        # confirmed-reversible DC fans), read from the live coordinator state.
        coordinator = getattr(self.config_entry, "runtime_data", None)
        data = getattr(coordinator, "data", None)
        detected_reverse = data is not None and fan_type_supports_reverse(data.fan_type)
        return vol.Schema(
            {
                vol.Required(
                    CONF_SPEED_COUNT,
                    default=str(current_speed_count),
                ): _speed_count_field(),
                vol.Required(
                    CONF_DEFAULT_SPEED,
                    default=self.config_entry.options.get(CONF_DEFAULT_SPEED, DEFAULT_SPEED_LAST_USED),
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
                    default=self.config_entry.options.get(CONF_DEFAULT_BRIGHTNESS, DEFAULT_BRIGHTNESS_LAST_USED),
                ): NumberSelector(NumberSelectorConfig(min=0, max=100, step=1, mode=NumberSelectorMode.SLIDER)),
                vol.Required(
                    CONF_SUPPORTS_REVERSE,
                    default=self.config_entry.options.get(CONF_SUPPORTS_REVERSE, detected_reverse),
                ): bool,
            }
        )

    def _connection_section_schema(self) -> vol.Schema:
        """Build schema for connection & availability section."""
        return vol.Schema(
            {
                vol.Required(
                    CONF_NOTIFY_ON_DISCONNECT,
                    default=self.config_entry.options.get(CONF_NOTIFY_ON_DISCONNECT, DEFAULT_NOTIFY_ON_DISCONNECT),
                ): bool,
                vol.Required(
                    CONF_UNAVAILABLE_THRESHOLD,
                    default=self.config_entry.options.get(CONF_UNAVAILABLE_THRESHOLD, DEFAULT_UNAVAILABLE_THRESHOLD),
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
