"""DataUpdateCoordinator for Fanimation BLE fans."""

from __future__ import annotations

from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CONF_NOTIFY_ON_DISCONNECT,
    CONF_UNAVAILABLE_THRESHOLD,
    DEFAULT_NOTIFY_ON_DISCONNECT,
    DEFAULT_UNAVAILABLE_THRESHOLD,
    DOMAIN,
    LOGGER,
    POLL_FAST,
    POLL_FAST_CYCLES,
    POLL_SLOW,
)
from .device import FanimationDevice, FanimationState


class FanimationCoordinator(DataUpdateCoordinator[FanimationState]):
    """Coordinator that polls the fan via BLE and manages fast/slow poll cycles."""

    def __init__(self, hass: HomeAssistant, device: FanimationDevice, entry: ConfigEntry) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            LOGGER,
            name=f"{DOMAIN}_{device.mac}",
            update_interval=timedelta(seconds=POLL_SLOW),
            config_entry=entry,
        )
        self.device = device
        self._fast_poll_remaining = 0
        self._connection_failures = 0
        self._notification_active = False

    @property
    def connection_failures(self) -> int:
        """Return the number of consecutive connection failures."""
        return self._connection_failures

    def _get_option(self, key: str, default):
        """Read an option from the config entry, with fallback default."""
        if self.config_entry and self.config_entry.options:
            return self.config_entry.options.get(key, default)
        return default

    async def _async_update_data(self) -> FanimationState:
        """Poll the fan for current state with tiered availability.

        The BLE connection is kept alive between polls so that user
        commands (light toggle, speed change) respond instantly instead
        of waiting 10-20 s for a fresh BLE connection.  If the fan
        drops the connection on its own, ``_on_disconnect`` sets the
        client to ``None`` and the next poll/command reconnects
        transparently.  Disconnect only happens on error (to force a
        clean reconnect) or when the config entry is unloaded.

        Tiered availability:
        - On failure, return last-known state (if available) instead of
          immediately raising UpdateFailed.
        - After ``unavailable_threshold`` consecutive failures, raise
          UpdateFailed so HA marks entities unavailable.
        - If threshold is 0, never raise (always return last-known state).
        - If no prior state exists, always raise (can't show stale data
          that doesn't exist).
        """
        try:
            state = await self.device.async_get_status()
        except Exception as err:
            # Disconnect on failure to force clean reconnect next time
            await self.device.disconnect()
            return await self._async_handle_failure(
                f"Connection to {self.device.name} failed: {err}"
            )

        if state is None:
            return await self._async_handle_failure(
                f"No response from {self.device.name}"
            )

        # --- Success ---
        was_failing = self._connection_failures > 0
        self._connection_failures = 0

        # Dismiss notification on recovery
        if was_failing:
            await self._async_dismiss_notification()

        # Manage fast/slow polling transition
        if self._fast_poll_remaining > 0:
            self._fast_poll_remaining -= 1
            if self._fast_poll_remaining == 0:
                self.update_interval = timedelta(seconds=POLL_SLOW)
                LOGGER.debug("Reverting to slow poll for %s", self.device.name)

        return state

    async def _async_handle_failure(self, error_msg: str) -> FanimationState:
        """Handle a poll failure with tiered availability logic.

        Increments the failure counter, optionally fires a persistent
        notification on the first failure, and decides whether to return
        last-known state (soft unavailable) or raise UpdateFailed (hard
        unavailable) based on the configured threshold.
        """
        self._connection_failures += 1

        # --- Persistent notification (fires once on first failure) ---
        notify = self._get_option(CONF_NOTIFY_ON_DISCONNECT, DEFAULT_NOTIFY_ON_DISCONNECT)
        if notify and self._connection_failures == 1:
            await self._async_create_notification()

        # --- Availability decision ---
        threshold = self._get_option(CONF_UNAVAILABLE_THRESHOLD, DEFAULT_UNAVAILABLE_THRESHOLD)

        if threshold > 0 and self._connection_failures >= threshold:
            # Hard unavailable — dismiss notification (HA shows unavailable natively)
            await self._async_dismiss_notification()
            raise UpdateFailed(
                f"{error_msg} after {self._connection_failures} attempts"
            )

        if self.data is not None:
            # Soft unavailable — return stale data, entities stay available
            LOGGER.warning(
                "%s (%d failures) — returning last known state",
                error_msg,
                self._connection_failures,
            )
            return self.data

        # No prior state at all — must raise regardless of threshold
        raise UpdateFailed(f"{error_msg} and no prior state available")

    async def async_start_fast_poll(self) -> None:
        """Switch to fast polling after a command."""
        self._fast_poll_remaining = POLL_FAST_CYCLES
        self.update_interval = timedelta(seconds=POLL_FAST)
        LOGGER.debug(
            "Fast polling for %s (%d cycles)",
            self.device.name,
            POLL_FAST_CYCLES,
        )
        await self.async_request_refresh()

    def _notification_id(self) -> str:
        """Return a deterministic notification ID for this fan."""
        return f"fanimation_{self.device.mac.replace(':', '_')}_unreachable"

    async def _async_create_notification(self) -> None:
        """Fire a persistent notification that the fan is unreachable."""
        if self._notification_active:
            return
        self._notification_active = True
        try:
            await self.hass.services.async_call(
                "persistent_notification",
                "create",
                {
                    "notification_id": self._notification_id(),
                    "title": f"Fanimation: {self.device.name} unreachable",
                    "message": (
                        f"{self.device.name} has not responded to Bluetooth polls. "
                        f"The integration will keep trying. Entities show last known state."
                    ),
                },
            )
        except Exception:  # noqa: S110
            pass  # Don't let notification failure break polling

    async def _async_dismiss_notification(self) -> None:
        """Dismiss the unreachable notification."""
        if not self._notification_active:
            return
        self._notification_active = False
        try:
            await self.hass.services.async_call(
                "persistent_notification",
                "dismiss",
                {"notification_id": self._notification_id()},
            )
        except Exception:  # noqa: S110
            pass
