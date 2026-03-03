"""Fan entity for Fanimation BLE integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.fan import FanEntity, FanEntityFeature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util.percentage import (
    ordered_list_item_to_percentage,
    percentage_to_ordered_list_item,
)

from . import FanimationConfigEntry
from .const import (
    CONF_DEFAULT_SPEED,
    DEFAULT_SPEED_LAST_USED,
    SPEED_COUNT,
    SPEED_HIGH,
    SPEED_LOW,
    SPEED_MED,
    SPEED_OFF,
    SPEED_OPTION_MAP,
)
from .coordinator import FanimationCoordinator
from .entity import FanimationEntity

ORDERED_NAMED_FAN_SPEEDS = [SPEED_LOW, SPEED_MED, SPEED_HIGH]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: FanimationConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the fan entity."""
    coordinator = entry.runtime_data
    async_add_entities([FanimationFan(coordinator, entry.entry_id)])


class FanimationFan(FanimationEntity, FanEntity):
    """Fanimation ceiling fan entity."""

    _attr_speed_count = SPEED_COUNT
    _attr_supported_features = FanEntityFeature.SET_SPEED | FanEntityFeature.TURN_ON | FanEntityFeature.TURN_OFF
    _attr_name = None  # Primary entity — uses device name only

    def __init__(
        self,
        coordinator: FanimationCoordinator,
        entry_id: str,
    ) -> None:
        """Initialize the fan entity."""
        super().__init__(coordinator, entry_id)
        self._attr_unique_id = f"{coordinator.device.mac}_fan"
        self._last_speed = SPEED_LOW  # default for turn_on without speed

    @property
    def is_on(self) -> bool | None:
        """Return True if the fan is on."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.speed > SPEED_OFF

    @property
    def percentage(self) -> int | None:
        """Return the current speed percentage."""
        if self.coordinator.data is None:
            return None
        speed = self.coordinator.data.speed
        if speed == SPEED_OFF:
            return 0
        return ordered_list_item_to_percentage(ORDERED_NAMED_FAN_SPEEDS, speed)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        attrs = super().extra_state_attributes
        attrs["rf_remote_sync"] = "State is verified before every command — RF remote changes are always respected"
        return attrs

    async def async_turn_on(
        self,
        percentage: int | None = None,
        preset_mode: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Turn on the fan."""
        if percentage is not None:
            await self.async_set_percentage(percentage)
            return

        # Check for user-configured fixed default speed
        default_speed = DEFAULT_SPEED_LAST_USED
        if self.coordinator.config_entry and self.coordinator.config_entry.options:
            default_speed = self.coordinator.config_entry.options.get(CONF_DEFAULT_SPEED, DEFAULT_SPEED_LAST_USED)

        if default_speed in SPEED_OPTION_MAP:
            await self._async_set_speed(SPEED_OPTION_MAP[default_speed])
        else:
            # "last_used" or unrecognized — use last known speed
            await self._async_set_speed(self._last_speed)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the fan."""
        await self._async_set_speed(SPEED_OFF)

    async def async_set_percentage(self, percentage: int) -> None:
        """Set fan speed by percentage."""
        if percentage == 0:
            await self._async_set_speed(SPEED_OFF)
        else:
            speed = percentage_to_ordered_list_item(ORDERED_NAMED_FAN_SPEEDS, percentage)
            await self._async_set_speed(speed)

    async def _async_set_speed(self, speed: int) -> None:
        """Set fan speed and trigger fast poll."""
        if speed > SPEED_OFF:
            self._last_speed = speed
        await self.coordinator.device.async_set_state(speed=speed)
        await self.coordinator.async_start_fast_poll()
