"""Shared test fixtures for Fanimation BLE integration.

The device protocol tests are pure-logic unit tests that should run on ANY
platform (including Windows).  The heavy Home Assistant + Bluetooth import
chain only resolves on Linux, so we pre-seed ``sys.modules`` with lightweight
stubs **before** importing any integration code.  This lets ``_build_packet``,
``_parse_response``, and ``FanimationState`` load without pulling in the full
HA bluetooth stack.

Config-flow tests require the full ``pytest-homeassistant-custom-component``
harness (Linux CI only) and are skipped automatically on Windows.
"""

from __future__ import annotations

import sys
from unittest.mock import MagicMock

# ---------------------------------------------------------------------------
# Stub heavy HA / BLE modules so our integration code can be imported
# without pulling in the full BLE or USB hardware stacks.
#
# homeassistant.components.usb needs ``aiousbwatcher`` (not installed in any
# test env), so it is stubbed on ALL platforms.
#
# On Windows ONLY we also stub bluetooth and bleak_retry_connector because
# those packages have Linux-specific extensions.  On Linux CI the real
# packages are available (installed by pytest-homeassistant-custom-component)
# and the config-flow tests need the genuine BluetoothServiceInfoBleak.
# ---------------------------------------------------------------------------

# Always stub USB — aiousbwatcher is not in test requirements on any OS.
sys.modules.setdefault("homeassistant.components.usb", MagicMock())

if sys.platform == "win32":
    # Windows: also stub BLE modules (no bleak / habluetooth support)
    for _mod in ("homeassistant.components.bluetooth", "bleak_retry_connector"):
        sys.modules.setdefault(_mod, MagicMock())

# homeassistant.const has pure constants — ensure a real copy is used if
# it already loaded, but it usually resolves fine.
# homeassistant.core / homeassistant.config_entries are also lightweight.

# ---------------------------------------------------------------------------
# Now safe to import our integration modules
# ---------------------------------------------------------------------------

from typing import Any
from unittest.mock import AsyncMock

import pytest

from custom_components.fanimation.const import (
    CMD_STATUS_RESPONSE,
    START_BYTE,
)
from custom_components.fanimation.coordinator import FanimationCoordinator
from custom_components.fanimation.device import FanimationState

TEST_MAC = "50:8C:B1:4A:16:A0"
TEST_NAME = "Test Fan"


def make_mock_coordinator(
    data: FanimationState | None = None,
    *,
    mac: str = "AA:BB:CC:DD:EE:FF",
    name: str = "Test Fan",
    options: dict[str, Any] | None = None,
    entry_id: str = "test_entry",
) -> MagicMock:
    """Build the one canonical mock coordinator shared by the entity test files.

    ``spec=FanimationCoordinator`` makes an entity that calls a renamed or
    removed coordinator attribute FAIL the test instead of silently
    auto-mocking it — the mock cannot drift from the real interface beyond the
    members set explicitly here. (The entity suites stay mock-based because the
    real coordinator drags in the HA event loop; the spec is the drift guard.)

    ``device.async_set_state`` is a bare AsyncMock; per-file wrappers install
    their own hardware-emulating side effects.
    """
    coordinator = MagicMock(spec=FanimationCoordinator)
    coordinator.device = MagicMock()
    coordinator.device.mac = mac
    coordinator.device.name = name
    coordinator.device.async_set_state = AsyncMock()
    coordinator.async_start_fast_poll = AsyncMock()
    coordinator.data = data
    coordinator.connection_failures = 0
    coordinator.first_failure_at = None
    coordinator.config_entry = MagicMock()
    coordinator.config_entry.options = dict(options) if options else {}
    coordinator.config_entry.entry_id = entry_id
    return coordinator


def build_response(
    speed: int = 0,
    direction: int = 0,
    uplight: int = 0,
    downlight: int = 0,
    timer_minutes: int = 0,
    fan_type: int = 0,
) -> bytearray:
    """Build a valid 10-byte status response with correct checksum."""
    timer_hi = (timer_minutes >> 8) & 0xFF
    timer_lo = timer_minutes & 0xFF
    data = bytearray(
        [
            START_BYTE,
            CMD_STATUS_RESPONSE,
            speed,
            direction,
            uplight,
            downlight,
            timer_hi,
            timer_lo,
            fan_type,
            0,
        ]
    )
    data[9] = sum(data[:9]) & 0xFF
    return data


@pytest.fixture
def mock_state() -> FanimationState:
    """Return a default FanimationState for testing."""
    return FanimationState(
        speed=1,
        direction=0,
        uplight=0,
        downlight=50,
        timer_minutes=120,
        fan_type=0,
    )
