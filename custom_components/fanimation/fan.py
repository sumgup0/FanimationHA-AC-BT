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
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util.percentage import (
    percentage_to_ranged_value,
    ranged_value_to_percentage,
)

from . import FanimationConfigEntry
from .const import (
    CONF_DEFAULT_SPEED,
    CONF_SUPPORTS_REVERSE,
    DEFAULT_SPEED_LAST_USED,
    DIR_FORWARD,
    DIR_REVERSE,
    DOMAIN,
    SPEED_LOW,
    SPEED_OFF,
    fan_type_supports_reverse,
    speed_for_preset,
)
from .coordinator import FanimationCoordinator
from .entity import FanimationEntity
from .options import get_option, resolved_speed_count

# Serialise commands: every BLE write goes through the shared device-level lock,
# so one in-flight command at a time matches HA's BLE convention.
PARALLEL_UPDATES = 1


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
        self._entry_id = entry.entry_id
        self._attr_unique_id = f"{coordinator.device.mac}_fan"
        self._speed_count = resolved_speed_count(entry)
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
    def _speed_count_issue_id(self) -> str:
        """Deterministic repair-issue id for this fan's speed-count mismatch."""
        return f"speed_count_out_of_range_{self._entry_id}"

    async def async_added_to_hass(self) -> None:
        """Register the coordinator listener and evaluate the speed-count issue once."""
        await super().async_added_to_hass()
        self._evaluate_speed_count_issue()

    async def async_will_remove_from_hass(self) -> None:
        """Clear any open speed-count repair issue when the entity is removed.

        Covers integration removal: the in-range self-heal only runs while the
        entity is alive, so without this a stale issue would linger until the
        next restart (the issue is non-persistent).
        """
        ir.async_delete_issue(self.hass, DOMAIN, self._speed_count_issue_id)
        await super().async_will_remove_from_hass()

    @callback
    def _handle_coordinator_update(self) -> None:
        """Re-evaluate the speed-count issue on each poll, then write entity state."""
        self._evaluate_speed_count_issue()
        super()._handle_coordinator_update()

    @callback
    def _evaluate_speed_count_issue(self) -> None:
        """Raise or clear a repair issue when the fan reports a speed above speed_count.

        A hardware speed greater than the configured ``speed_count`` (e.g. a
        32-speed DC fan left at the default 3) is a user-fixable misconfiguration:
        ``percentage`` clamps the slider to the configured max, so higher speeds
        set by the RF remote read as the top step. The repair issue points the
        user at the options flow to raise the count, and clears automatically
        once the reported speed is back in range — including after the user fixes
        the option and the entry reloads.
        """
        data = self.coordinator.data
        if data is not None and data.speed > self._speed_count:
            ir.async_create_issue(
                self.hass,
                DOMAIN,
                self._speed_count_issue_id,
                is_fixable=False,
                severity=ir.IssueSeverity.WARNING,
                translation_key="speed_count_out_of_range",
                translation_placeholders={
                    "name": self.coordinator.device.name,
                    "reported_speed": str(data.speed),
                    "speed_count": str(self._speed_count),
                },
            )
        else:
            ir.async_delete_issue(self.hass, DOMAIN, self._speed_count_issue_id)

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
        default_speed = get_option(self.coordinator.config_entry, CONF_DEFAULT_SPEED, DEFAULT_SPEED_LAST_USED)

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
