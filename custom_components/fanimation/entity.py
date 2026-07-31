"""Base entity for Fanimation BLE integration."""

from __future__ import annotations

from typing import Any

from homeassistant.helpers.device_registry import CONNECTION_BLUETOOTH, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .coordinator import FanimationCoordinator


class FanimationEntity(CoordinatorEntity[FanimationCoordinator]):
    """Base class for all Fanimation entities."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: FanimationCoordinator,
        entry_id: str,
    ) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.device.mac)},
            connections={(CONNECTION_BLUETOOTH, coordinator.device.mac)},
            name=coordinator.device.name,
            manufacturer="Fanimation",
            model="BTCR9 FanSync Bluetooth",
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return connection status and the RF-sync note on all entities."""
        failures = self.coordinator.connection_failures
        if failures == 0:
            status = "connected"
        else:
            # Real elapsed downtime from the streak start. A failure-count
            # estimate (count x POLL_SLOW) overstates wildly during 1 s
            # fast-poll bursts: 3 failures in ~3 s would read as "~15 min".
            started = self.coordinator.first_failure_at
            minutes = 0 if started is None else int((dt_util.utcnow() - started).total_seconds() // 60)
            if minutes < 1:
                time_str = "<1 min"
            elif minutes < 60:
                time_str = f"~{minutes} min"
            elif minutes < 1440:
                time_str = f"~{minutes // 60} hr"
            else:
                time_str = f"~{minutes // 1440} day(s)"
            attempt_word = "attempt" if failures == 1 else "attempts"
            status = f"unreachable ({failures} {attempt_word}, {time_str})"
        return {
            "connection_status": status,
            "rf_remote_sync": "State is verified before every command — RF remote changes are always respected",
        }
