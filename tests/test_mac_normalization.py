"""Tests for MAC-address normalisation (config_flow._normalize_mac).

Pure unit tests — ``config_flow`` imports fine under the conftest stubs, so
unlike the flow's behavioural tests these run on every platform rather than
Linux CI only. That matters here: MAC parsing is the integration's most
user-facing input validation, and getting it wrong locks people out of setup.
"""

from __future__ import annotations

import pytest

from custom_components.fanimation.config_flow import _normalize_mac

CANONICAL = "50:8C:B1:4A:16:A0"


class TestConsistentSeparators:
    """The forms HA's own format_mac() already understood."""

    @pytest.mark.parametrize(
        "raw",
        [
            "50:8C:B1:4A:16:A0",  # colons
            "50-8C-B1-4A-16-A0",  # dashes
            "508C.B14A.16A0",  # dotted (Cisco style)
            "508CB14A16A0",  # bare hex
            "50:8c:b1:4a:16:a0",  # lowercase
            "  50:8C:B1:4A:16:A0  ",  # surrounding whitespace
        ],
    )
    def test_accepted_and_canonicalised(self, raw: str) -> None:
        assert _normalize_mac(raw) == CANONICAL


class TestMixedSeparators:
    """Regression: partially separated input used to be rejected outright.

    ``format_mac`` only recognises fully consistent forms and silently returns
    anything else unchanged, so these fell through to the invalid_mac error even
    though the address is unambiguous.
    """

    @pytest.mark.parametrize(
        "raw",
        [
            "50:8C:B1:4A16:A0",  # a colon dropped mid-address
            "50:8CB14A16A0",  # only the first separator typed
            "508CB14A16:A0",  # only the last separator typed
            "50-8C:B1-4A:16-A0",  # dashes and colons mixed
            "50 8C B1 4A 16 A0",  # spaces
            "50:8C-B1.4A 16A0",  # every separator at once
        ],
    )
    def test_accepted_and_canonicalised(self, raw: str) -> None:
        assert _normalize_mac(raw) == CANONICAL


class TestRejected:
    """Stripping separators must not turn genuinely bad input into a valid MAC."""

    @pytest.mark.parametrize(
        "raw",
        [
            "",
            "   ",
            "not-a-mac",
            "not-a-mac-address",
            "50:8C:B1:4A:16",  # 10 hex digits — too short
            "50:8C:B1:4A:16:A0:FF",  # 14 hex digits — too long
            "50:8C:B1:4A:16:AG",  # G is not hex
            "50:8C:B1:4A:16:A",  # 11 hex digits
            "CeilingFan",
        ],
    )
    def test_returns_none(self, raw: str) -> None:
        assert _normalize_mac(raw) is None


def test_output_is_stable_under_reapplication() -> None:
    """Canonical output must itself normalise to the same value.

    The reconfigure flow compares the result against the stored unique_id, so a
    non-idempotent normaliser would make an unchanged MAC look like a change.
    """
    once = _normalize_mac("50:8C:B1:4A16:A0")
    assert once is not None
    assert _normalize_mac(once) == once
