"""Fan entity for Fanimation BLE integration."""

from __future__ import annotations

import math
from typing import Any

from homeassistant.components.fan import (
    DIRECTION_FORWARD,
    DIRECTION_REVERSE,
    FanEntity,
    FanEntityFeature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util.percentage import (
    percentage_to_ranged_value,
    ranged_value_to_percentage,
)

from . import FanimationConfigEntry
from .const import (
    CONF_DEFAULT_SPEED,
    CONF_SPEED_COUNT,
    CONF_SUPPORTS_REVERSE,
    DEFAULT_SPEED_COUNT,
    DEFAULT_SPEED_LAST_USED,
    DIR_FORWARD,
    DIR_REVERSE,
    SPEED_LOW,
    SPEED_OFF,
    fan_type_supports_reverse,
    speed_for_preset,
)
from .coordinator import FanimationCoordinator
from .entity import FanimationEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: FanimationConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the fan entity."""
    coordinator = entry.runtime_data
    async_add_entities([FanimationFan(coordinator, entry)])


class FanimationFan(FanimationEntity, FanEntity):
    """Fanimation ceiling fan entity."""

    _attr_name = None  # Primary entity — uses device name only

    def __init__(
        self,
        coordinator: FanimationCoordinator,
        entry: FanimationConfigEntry,
    ) -> None:
        """Initialize the fan entity."""
        super().__init__(coordinator, entry.entry_id)
        self._attr_unique_id = f"{coordinator.device.mac}_fan"
        # Speed count: options-flow value wins, then install-time data, then default.
        self._speed_count = entry.options.get(
            CONF_SPEED_COUNT,
            entry.data.get(CONF_SPEED_COUNT, DEFAULT_SPEED_COUNT),
        )
        self._attr_speed_count = self._speed_count
        self._last_speed = SPEED_LOW  # default for turn_on without speed

        # Reverse direction is opt-in. It defaults ON only for fan types known to
        # reverse electronically (DC); the options toggle overrides either way.
        # supported_features is fixed at construction and the integration reloads
        # on options change, so toggling re-creates the entity with the right set.
        detected = coordinator.data is not None and fan_type_supports_reverse(coordinator.data.fan_type)
        self._supports_reverse: bool = entry.options.get(CONF_SUPPORTS_REVERSE, detected)
        features = FanEntityFeature.SET_SPEED | FanEntityFeature.TURN_ON | FanEntityFeature.TURN_OFF
        if self._supports_reverse:
            features |= FanEntityFeature.DIRECTION
        self._attr_supported_features = features

    @property
    def is_on(self) -> bool | None:
        """Return True if the fan is on."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.speed > SPEED_OFF

    @property
    def percentage(self) -> int | None:
        """Return the current speed percentage.

        Hardware speeds outside ``[1, speed_count]`` are clamped to the configured
        max so a misconfigured speed_count never crashes the entity (Issue #1).
        """
        if self.coordinator.data is None:
            return None
        speed = self.coordinator.data.speed
        if speed == SPEED_OFF:
            return 0
        # Clamp incoming speed: an out-of-range value (e.g. 5 reported by a
        # 32-speed fan when the user has speed_count=3 misconfigured) would
        # otherwise extrapolate above 100% and break the slider UI.
        clamped = max(1, min(self._speed_count, speed))
        return ranged_value_to_percentage((1, self._speed_count), clamped)

    @property
    def current_direction(self) -> str | None:
        """Return the current rotation direction from verified device state (byte[3]).

        Only meaningful when reverse support is enabled; the probe confirmed
        byte[3] reads back reliably on reverse-capable (DC) fans.
        """
        if self.coordinator.data is None:
            return None
        return DIRECTION_REVERSE if self.coordinator.data.direction == DIR_REVERSE else DIRECTION_FORWARD

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

        preset_speed = speed_for_preset(default_speed, self._speed_count)
        if preset_speed is not None:
            await self._async_set_speed(preset_speed)
        else:
            # "last_used" or unrecognized — use last known speed
            await self._async_set_speed(self._last_speed)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the fan."""
        await self._async_set_speed(SPEED_OFF)

    async def async_set_direction(self, direction: str) -> None:
        """Set the fan rotation direction.

        Reverse-capable (DC) fans change direction instantly — whether stopped or
        spinning — so this just sends the new direction and refreshes. No
        stop-and-wait sequence is needed (confirmed by hardware probe).
        """
        new_dir = DIR_REVERSE if direction == DIRECTION_REVERSE else DIR_FORWARD
        await self.coordinator.device.async_set_state(direction=new_dir)
        await self.coordinator.async_start_fast_poll()

    async def async_set_percentage(self, percentage: int) -> None:
        """Set fan speed by percentage."""
        if percentage == 0:
            await self._async_set_speed(SPEED_OFF)
            return
        # ceil keeps small percentages > 0 from rounding to off; clamp guards
        # against rounding past max at exactly 100%.
        raw = math.ceil(percentage_to_ranged_value((1, self._speed_count), percentage))
        speed = max(1, min(self._speed_count, raw))
        await self._async_set_speed(speed)

    async def _async_set_speed(self, speed: int) -> None:
        """Set fan speed and trigger fast poll.

        ``_last_speed`` is updated from the *verified* response, not the requested
        value. If speed_count is misconfigured (e.g. set to 6 on a 3-speed fan),
        the firmware silently turns off when it receives a SPEED byte it can't
        honour. Pinning ``_last_speed`` to the rejected value would put
        ``async_turn_on`` (with default = "Last Used") into a stuck-off loop:
        every toggle resends the bad value and the fan stays off.
        """
        state = await self.coordinator.device.async_set_state(speed=speed)
        if state is not None and state.speed > SPEED_OFF:
            self._last_speed = state.speed
        await self.coordinator.async_start_fast_poll()
