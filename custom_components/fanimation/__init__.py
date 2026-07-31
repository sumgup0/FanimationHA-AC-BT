"""Fanimation BLE Ceiling Fan integration for Home Assistant."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_MAC, CONF_NAME
from homeassistant.core import HomeAssistant

from .const import LOGGER, PLATFORMS
from .coordinator import FanimationCoordinator
from .device import FanimationDevice

type FanimationConfigEntry = ConfigEntry[FanimationCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: FanimationConfigEntry) -> bool:
    """Set up Fanimation BLE from a config entry."""
    mac = entry.data[CONF_MAC]
    name = entry.data[CONF_NAME]

    LOGGER.info("Setting up Fanimation fan: %s (%s)", name, mac)

    # Create device and coordinator
    device = FanimationDevice(hass, mac, name)
    coordinator = FanimationCoordinator(hass, device, entry)

    # First refresh — if it fails, raise ConfigEntryNotReady so HA
    # retries with exponential backoff instead of leaving entities
    # permanently unavailable.
    await coordinator.async_config_entry_first_refresh()

    # Store coordinator on the config entry for platform access
    entry.runtime_data = coordinator

    # Single owner of reloads: this listener fires on ANY entry change (options
    # flow, reconfigure flow), so the flows themselves must use non-reloading
    # abort helpers — see async_step_reconfigure.
    entry.async_on_unload(entry.add_update_listener(_async_entry_updated))

    # Forward setup to entity platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def _async_entry_updated(hass: HomeAssistant, entry: FanimationConfigEntry) -> None:
    """Reload the integration when the config entry changes.

    Covers both the options flow and the reconfigure flow. Entity attributes
    such as speed_count and the reverse-direction feature flag are fixed at
    construction, so a reload is how a settings change takes effect. HA only
    calls this when the entry actually changed, so an unchanged submit is a
    no-op rather than a needless reconnect.
    """
    LOGGER.info("Configuration changed for %s — reloading", entry.title)
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: FanimationConfigEntry) -> bool:
    """Unload a config entry.

    Must clean up all resources: cancel pending tasks, disconnect BLE.
    """
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        coordinator = entry.runtime_data
        await coordinator.device.disconnect()
        LOGGER.info("Unloaded Fanimation fan: %s", entry.title)

    return unload_ok
