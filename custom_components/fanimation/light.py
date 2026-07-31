"""Light entity for Fanimation BLE integration."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.components.light import ATTR_BRIGHTNESS, LightEntity
from homeassistant.components.light.const import ColorMode
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import FanimationConfigEntry
from .const import (
    CONF_DEFAULT_BRIGHTNESS,
    DEFAULT_BRIGHTNESS_LAST_USED,
    DOWNLIGHT_MAX,
)
from .entity import FanimationEntity
from .options import get_option

if TYPE_CHECKING:
    from .coordinator import FanimationCoordinator

# Serialise commands: every BLE write goes through the shared device-level lock,
# so one in-flight command at a time matches HA's BLE convention.
PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: FanimationConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the light entity."""
    coordinator = entry.runtime_data
    async_add_entities([FanimationLight(coordinator, entry.entry_id)])


class FanimationLight(FanimationEntity, LightEntity):
    """Fanimation downlight entity."""

    _attr_color_mode = ColorMode.BRIGHTNESS
    _attr_translation_key = "downlight"

    def __init__(
        self,
        coordinator: FanimationCoordinator,
        entry_id: str,
    ) -> None:
        """Initialize the light entity."""
        super().__init__(coordinator, entry_id)
        # Instance (not class) attribute: overriding LightEntity's instance var with a
        # ClassVar trips mypy [misc], and a bare class-level mutable set trips ruff RUF012.
        self._attr_supported_color_modes = {ColorMode.BRIGHTNESS}
        self._attr_unique_id = f"{coordinator.device.mac}_light"
        self._last_brightness = DOWNLIGHT_MAX  # default for turn_on without brightness

    @property
    def is_on(self) -> bool | None:
        """Return True if the light is on."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.downlight > 0

    @property
    def brightness(self) -> int | None:
        """Return brightness (HA 0-255 scale)."""
        if self.coordinator.data is None:
            return None
        # Scale fan 0-100 → HA 0-255
        return round(self.coordinator.data.downlight * 255 / DOWNLIGHT_MAX)

    @callback
    def _handle_coordinator_update(self) -> None:
        """Track the last non-zero brightness from each poll, then write state.

        Polling is the only way RF-remote changes reach us, so "last used"
        brightness is captured here — a state hook — rather than as a side
        effect inside the ``brightness`` getter.
        """
        data = self.coordinator.data
        if data is not None and data.downlight > 0:
            self._last_brightness = data.downlight
        super()._handle_coordinator_update()

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on the light."""
        if ATTR_BRIGHTNESS in kwargs:
            # Explicit brightness from user — always use it
            fan_brightness = round(kwargs[ATTR_BRIGHTNESS] * DOWNLIGHT_MAX / 255)
            fan_brightness = max(1, min(fan_brightness, DOWNLIGHT_MAX))
        else:
            # Check for user-configured fixed default brightness
            default_brightness = get_option(
                self.coordinator.config_entry, CONF_DEFAULT_BRIGHTNESS, DEFAULT_BRIGHTNESS_LAST_USED
            )

            if default_brightness > 0:
                fan_brightness = default_brightness
            else:
                # 0 means "last_used" — current behavior
                fan_brightness = self._last_brightness

        # ``_last_brightness`` is updated from the *verified* response, not the
        # requested value — same lesson as the fan's ``_last_speed`` (Issue #1):
        # a value the hardware didn't actually apply must not become "last used".
        state = await self.coordinator.device.async_set_state(downlight=fan_brightness)
        if state is not None and state.downlight > 0:
            self._last_brightness = state.downlight
        await self.coordinator.async_start_fast_poll()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the light."""
        await self.coordinator.device.async_set_state(downlight=0)
        await self.coordinator.async_start_fast_poll()
