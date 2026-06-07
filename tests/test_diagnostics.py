"""Tests for the Fanimation BLE diagnostics dump.

Diagnostics imports ``homeassistant.components.diagnostics``, so this module
needs Home Assistant available and runs on Linux CI only (the maintainer's
pure-logic suites run on Windows; this one is skipped there).
"""

from __future__ import annotations

import sys

import pytest

# Skip on Windows — pulls in the HA diagnostics component.
pytestmark = pytest.mark.skipif(
    sys.platform == "win32",
    reason="Diagnostics requires Home Assistant (Linux CI only)",
)

from unittest.mock import MagicMock

from homeassistant.const import CONF_MAC, CONF_NAME

from custom_components.fanimation.const import CONF_SPEED_COUNT
from custom_components.fanimation.device import FanimationState

from .conftest import TEST_MAC, TEST_NAME


def _make_entry(state: FanimationState | None, *, failures: int = 0):
    """Build a config entry whose runtime_data is a mocked coordinator."""
    coordinator = MagicMock()
    coordinator.data = state
    coordinator.last_update_success = state is not None
    coordinator.update_interval = None
    coordinator.connection_failures = failures

    entry = MagicMock()
    entry.title = TEST_NAME
    entry.runtime_data = coordinator
    entry.data = {CONF_MAC: TEST_MAC, CONF_NAME: TEST_NAME, CONF_SPEED_COUNT: 3}
    entry.options = {}
    return entry


async def test_diagnostics_redacts_mac_and_includes_state() -> None:
    from custom_components.fanimation.diagnostics import async_get_config_entry_diagnostics

    entry = _make_entry(FanimationState(speed=2, direction=1, downlight=50, timer_minutes=30, fan_type=7))

    result = await async_get_config_entry_diagnostics(MagicMock(), entry)

    # MAC redacted, other fields preserved.
    assert result["entry"]["data"][CONF_MAC] == "**REDACTED**"
    assert result["entry"]["data"][CONF_NAME] == TEST_NAME
    assert result["entry"]["data"][CONF_SPEED_COUNT] == 3
    # Protocol state surfaced verbatim (direction/fan_type are the #4 debug keys).
    assert result["state"]["direction"] == 1
    assert result["state"]["fan_type"] == 7
    assert result["coordinator"]["connection_failures"] == 0


async def test_diagnostics_handles_no_state() -> None:
    from custom_components.fanimation.diagnostics import async_get_config_entry_diagnostics

    entry = _make_entry(None, failures=3)

    result = await async_get_config_entry_diagnostics(MagicMock(), entry)

    assert result["state"] is None
    assert result["coordinator"]["connection_failures"] == 3
