"""Diagnostics support for the Fanimation BLE integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_MAC
from homeassistant.core import HomeAssistant

from . import FanimationConfigEntry

# The MAC is the only identifying value worth hiding from shared diagnostics.
TO_REDACT = {CONF_MAC}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    entry: FanimationConfigEntry,
) -> dict[str, Any]:
    """Return diagnostics for a config entry.

    The decoded protocol state — including the ``direction`` and ``fan_type``
    bytes — is included verbatim. It carries no personal data and is exactly
    what's needed to triage behaviour reports such as Issue #4 (DC-fan
    direction), so it is deliberately not redacted.
    """
    coordinator = entry.runtime_data
    state = coordinator.data

    return {
        "entry": {
            "title": entry.title,
            "data": async_redact_data(dict(entry.data), TO_REDACT),
            "options": dict(entry.options),
        },
        "coordinator": {
            "last_update_success": coordinator.last_update_success,
            "update_interval_seconds": (
                coordinator.update_interval.total_seconds() if coordinator.update_interval else None
            ),
            "connection_failures": coordinator.connection_failures,
        },
        "state": (
            {
                "speed": state.speed,
                "direction": state.direction,
                "uplight": state.uplight,
                "downlight": state.downlight,
                "timer_minutes": state.timer_minutes,
                "fan_type": state.fan_type,
            }
            if state is not None
            else None
        ),
    }
