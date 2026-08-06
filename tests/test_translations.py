"""Translation-completeness tests — pure data, no Home Assistant harness needed.

Guards the class of bug behind the Issue #5 follow-up (an error message rendering
as a raw key in the UI). For a custom component, Home Assistant serves
``translations/en.json`` to the frontend at runtime — ``strings.json`` is only the
developer source — so any key present in one file but missing from the other
renders untranslated. These tests parse the JSON and ``config_flow.py`` directly
(no integration import), so they run on every platform, including the Windows
unit-test runs that skip the HA-harness config-flow tests.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any

_COMPONENT = Path(__file__).resolve().parent.parent / "custom_components" / "fanimation"
_STRINGS = _COMPONENT / "strings.json"
_TRANSLATIONS = _COMPONENT / "translations" / "en.json"
_CONFIG_FLOW = _COMPONENT / "config_flow.py"


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _leaf_paths(obj: Any, prefix: str = "") -> list[str]:
    """Return dotted paths to every leaf (non-dict) value in a nested dict."""
    if isinstance(obj, dict):
        paths: list[str] = []
        for key, value in obj.items():
            child = f"{prefix}.{key}" if prefix else key
            paths.extend(_leaf_paths(value, child))
        return paths
    return [prefix]


def test_translations_en_is_exact_copy_of_strings() -> None:
    """``translations/en.json`` must be byte-identical to ``strings.json``.

    ``strings.json`` is the developer source; HA serves ``translations/en.json``
    for custom components. They are kept identical by hand — no build step, by
    design (the parity is trivial to restore and this gate makes drift
    unmergeable). If this fails: copy strings.json over translations/en.json.
    """
    assert _STRINGS.read_text(encoding="utf-8") == _TRANSLATIONS.read_text(encoding="utf-8"), (
        "translations/en.json has drifted from strings.json — copy strings.json over it"
    )


def test_strings_and_translations_have_identical_keys() -> None:
    """``strings.json`` (dev source) and ``translations/en.json`` (runtime) must match.

    HA serves ``translations/en.json`` to the frontend for custom components, so a
    key that exists only in ``strings.json`` renders as a raw key in the UI. This
    parity check covers the whole tree, so config-flow, options, selector, and
    entity keys (including ones added by later features) are all guarded for free.
    """
    s_keys = set(_leaf_paths(_load(_STRINGS)))
    t_keys = set(_leaf_paths(_load(_TRANSLATIONS)))
    assert s_keys == t_keys, (
        "strings.json and translations/en.json keys differ: "
        f"only in strings={sorted(s_keys - t_keys)}; only in translations={sorted(t_keys - s_keys)}"
    )


def _config_flow_error_and_abort_keys() -> tuple[set[str], set[str]]:
    """Extract (error_keys, abort_keys) referenced as string literals in config_flow.py.

    Catches ``errors[...] = "key"`` assignments and ``async_abort(reason="key")``
    calls. HA-core-emitted aborts (e.g. ``already_configured`` from
    ``_abort_if_unique_id_configured``, ``already_in_progress`` from the flow
    manager) are not literals here and are covered by the parity test instead.
    """
    tree = ast.parse(_CONFIG_FLOW.read_text(encoding="utf-8"))
    error_keys: set[str] = set()
    abort_keys: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if (
                    isinstance(target, ast.Subscript)
                    and isinstance(target.value, ast.Name)
                    and target.value.id == "errors"
                    and isinstance(node.value, ast.Constant)
                    and isinstance(node.value.value, str)
                ):
                    error_keys.add(node.value.value)
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "async_abort":
            for keyword in node.keywords:
                if keyword.arg == "reason" and isinstance(keyword.value, ast.Constant):
                    abort_keys.add(keyword.value.value)
    return error_keys, abort_keys


def test_config_flow_error_and_abort_keys_are_translated() -> None:
    """Every error/abort key set in config_flow.py exists under config.error/abort in both files."""
    error_keys, abort_keys = _config_flow_error_and_abort_keys()
    assert error_keys, "expected at least one errors[...] assignment in config_flow.py"

    for name, data in (("strings.json", _load(_STRINGS)), ("translations/en.json", _load(_TRANSLATIONS))):
        config = data.get("config", {})
        missing_errors = error_keys - set(config.get("error", {}))
        missing_aborts = abort_keys - set(config.get("abort", {}))
        assert not missing_errors, f"{name}: config.error is missing {sorted(missing_errors)}"
        assert not missing_aborts, f"{name}: config.abort is missing {sorted(missing_aborts)}"


def _raised_translation_keys() -> set[str]:
    """Collect ``translation_key`` values from ``raise <Error>(..., translation_key="x")``.

    Walks every module in the component so any HomeAssistantError raised with a
    ``translation_key`` is covered, not just today's sleep-timer one. A key present
    here but absent from ``exceptions`` in the JSON renders as a raw key in the UI.
    """
    keys: set[str] = set()
    for path in sorted(_COMPONENT.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Raise) and isinstance(node.exc, ast.Call):
                for keyword in node.exc.keywords:
                    if keyword.arg == "translation_key" and isinstance(keyword.value, ast.Constant):
                        keys.add(keyword.value.value)
    return keys


def test_raised_exception_keys_are_translated() -> None:
    """Every ``raise ...(translation_key=...)`` key exists under ``exceptions`` in both files."""
    keys = _raised_translation_keys()
    assert keys, "expected at least one raise(..., translation_key=...) in the component"

    for name, data in (("strings.json", _load(_STRINGS)), ("translations/en.json", _load(_TRANSLATIONS))):
        missing = keys - set(data.get("exceptions", {}))
        assert not missing, f"{name}: exceptions is missing {sorted(missing)}"
