"""Constants for the Fanimation BLE integration."""

from __future__ import annotations

import logging

from homeassistant.const import Platform

DOMAIN = "fanimation"
LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.FAN, Platform.LIGHT, Platform.NUMBER]

# BLE Protocol — Fan Controller Service (0xE000)
CHAR_WRITE = "0000e001-0000-1000-8000-00805f9b34fb"
CHAR_NOTIFY = "0000e002-0000-1000-8000-00805f9b34fb"

# DANGER ZONE — TI OAD (Over-the-Air Download) firmware update service.
# Writing to these characteristics can BRICK the fan. They exist on the
# device but must NEVER be used by this integration. Listed here as an
# explicit exclusion so no one accidentally adds them.
# OAD_SERVICE  = "539c6813-0ad0-2137-4f79-bf1a11984790"  # DO NOT USE
# OAD_IDENTIFY = "539c6813-0ad1-2137-4f79-bf1a11984790"  # DO NOT USE
# OAD_BLOCK    = "539c6813-0ad2-2137-4f79-bf1a11984790"  # DO NOT USE

START_BYTE = 0x53
CMD_GET_STATUS = 0x30
CMD_SET_STATE = 0x31
CMD_STATUS_RESPONSE = 0x32

# Fan speed protocol values
SPEED_OFF = 0
SPEED_LOW = 1
SPEED_MED = 2
SPEED_HIGH = 3

# Speed count is per-fan and user-configurable (AC fans typically 3, DC fans 6/32).
# Common values surfaced as dropdown options; users can type any int in [MIN, MAX].
DEFAULT_SPEED_COUNT = 3
MIN_SPEED_COUNT = 1
MAX_SPEED_COUNT = 99
SPEED_COUNT_COMMON: list[str] = ["1", "3", "6", "32"]

# Downlight
DOWNLIGHT_MIN = 0
DOWNLIGHT_MAX = 100

# Timer
TIMER_MIN = 0
TIMER_MAX = 360  # 6 hours in minutes

# Polling intervals (seconds)
POLL_SLOW = 300
POLL_FAST = 1
POLL_FAST_CYCLES = 3

# Options flow keys
CONF_DEFAULT_SPEED = "default_speed"
CONF_DEFAULT_BRIGHTNESS = "default_brightness"
CONF_NOTIFY_ON_DISCONNECT = "notify_on_disconnect"
CONF_UNAVAILABLE_THRESHOLD = "unavailable_threshold"
CONF_SPEED_COUNT = "speed_count"

# Option defaults
DEFAULT_SPEED_LAST_USED = "last_used"
DEFAULT_SPEED_LOW = "low"
DEFAULT_SPEED_MEDIUM = "medium"
DEFAULT_SPEED_HIGH = "high"
DEFAULT_BRIGHTNESS_LAST_USED = 0
DEFAULT_NOTIFY_ON_DISCONNECT = True
DEFAULT_UNAVAILABLE_THRESHOLD = 12
MAX_UNAVAILABLE_THRESHOLD = 2016  # ~1 week at 300s polling


def speed_for_preset(preset: str, count: int) -> int | None:
    """Map a low/medium/high preset to a concrete speed for a fan with N speeds.

    For N=3 returns the original (1, 2, 3). For larger N, scales proportionally:
    e.g. N=32 → low=11, medium=21, high=32. Returns None for unrecognized presets
    (e.g. "last_used"), letting the caller fall back to last-known behaviour.
    """
    if preset == DEFAULT_SPEED_LOW:
        return max(1, round(count / 3))
    if preset == DEFAULT_SPEED_MEDIUM:
        return max(1, round(2 * count / 3))
    if preset == DEFAULT_SPEED_HIGH:
        return count
    return None
