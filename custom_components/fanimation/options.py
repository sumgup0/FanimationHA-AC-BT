"""Config-entry option helpers shared by the platforms, coordinator, and flows.

The "read an option with a fallback" logic used to be re-implemented in four
places (coordinator, fan, light, options flow) that had to stay semantically
in sync — in particular the load-bearing speed-count precedence. This module
is its single home.
"""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry

from .const import CONF_SPEED_COUNT, DEFAULT_SPEED_COUNT


def get_option(entry: ConfigEntry | None, key: str, default: Any) -> Any:
    """Read an option from a config entry, tolerating a missing entry or options."""
    if entry and entry.options:
        return entry.options.get(key, default)
    return default


def resolved_speed_count(entry: ConfigEntry) -> int:
    """Resolve the speed count: options-flow value wins, then install-time data, then default."""
    return int(entry.options.get(CONF_SPEED_COUNT, entry.data.get(CONF_SPEED_COUNT, DEFAULT_SPEED_COUNT)))
