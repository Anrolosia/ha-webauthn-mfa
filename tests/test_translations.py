"""Tests guarding the translation files against drift.

Issue #3 was caused by a string that changed shape in one file but kept its
old call site in the JavaScript, and issue #6 added a key that has to land in
six frontend files at once. Both classes of mistake are cheap to catch here.
"""

from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any

import pytest

COMPONENT = Path(__file__).parent.parent / "custom_components" / "webauthn_mfa"
BACKEND_TRANSLATIONS = COMPONENT / "translations"
FRONTEND_TRANSLATIONS = COMPONENT / "www" / "translations"
STRINGS = COMPONENT / "strings.json"

PLACEHOLDER = re.compile(r"\{(\w+)\}")


def _load(path: Path) -> dict[str, Any]:
    """Return the parsed JSON content of *path*."""
    return json.loads(path.read_text(encoding="utf-8"))


def _leaves(data: Any, prefix: str = "") -> dict[str, Any]:
    """Return every leaf of a nested mapping, keyed by its dotted path."""
    if not isinstance(data, dict):
        return {prefix: data}
    leaves: dict[str, Any] = {}
    for key, value in data.items():
        leaves |= _leaves(value, f"{prefix}.{key}" if prefix else key)
    return leaves


def _placeholders(data: Any) -> dict[str, set[str]]:
    """Return the placeholder names used by every leaf string."""
    return {
        path: set(PLACEHOLDER.findall(value))
        for path, value in _leaves(data).items()
        if isinstance(value, str)
    }


def _frontend_files() -> list[Path]:
    """Return every frontend translation file."""
    return sorted(FRONTEND_TRANSLATIONS.glob("*.json"))


def _backend_files() -> list[Path]:
    """Return every backend translation file."""
    return sorted(BACKEND_TRANSLATIONS.glob("*.json"))


# ── Frontend strings (www/translations) ──────────────────────────────────────


def test_frontend_english_reference_exists() -> None:
    """The English file is the reference every other file is compared to."""
    assert (FRONTEND_TRANSLATIONS / "en.json").is_file()


def test_frontend_files_share_the_top_level_key() -> None:
    """Every file must nest its sections under webauthn_mfa."""
    for path in _frontend_files():
        assert set(_load(path)) == {"webauthn_mfa"}, path.name


@pytest.mark.parametrize("path", _frontend_files(), ids=lambda p: p.name)
def test_frontend_files_have_the_same_keys_as_english(path: Path) -> None:
    """A missing key renders as undefined in the panel or the login page."""
    reference = set(_leaves(_load(FRONTEND_TRANSLATIONS / "en.json")["webauthn_mfa"]))
    actual = set(_leaves(_load(path)["webauthn_mfa"]))

    assert actual == reference, (
        f"{path.name} differs from en.json, "
        f"missing {sorted(reference - actual)}, extra {sorted(actual - reference)}"
    )


@pytest.mark.parametrize("path", _frontend_files(), ids=lambda p: p.name)
def test_frontend_placeholders_match_english(path: Path) -> None:
    """A translated string that drops {name} silently loses information."""
    reference = _placeholders(_load(FRONTEND_TRANSLATIONS / "en.json")["webauthn_mfa"])
    actual = _placeholders(_load(path)["webauthn_mfa"])

    for key, names in reference.items():
        assert actual[key] == names, f"{path.name} placeholder mismatch on {key}"


@pytest.mark.parametrize("path", _frontend_files(), ids=lambda p: p.name)
def test_frontend_strings_are_never_callable_shapes(path: Path) -> None:
    """Every leaf must be a plain string, substituted through _format."""
    panel = _load(path)["webauthn_mfa"]["panel"]
    for key, value in panel.items():
        assert isinstance(value, str), f"{path.name} panel.{key} is not a string"


def test_registered_ok_uses_the_name_placeholder() -> None:
    """Regression guard for issue #3, where it was called as a function."""
    for path in _frontend_files():
        value = _load(path)["webauthn_mfa"]["panel"]["registered_ok"]
        assert "{name}" in value, path.name


def test_already_registered_is_present_everywhere() -> None:
    """Regression guard for issue #6, the key must land in all languages."""
    for path in _frontend_files():
        assert _load(path)["webauthn_mfa"]["panel"]["alreadyRegistered"]


# ── Backend strings (strings.json and translations) ──────────────────────────


@pytest.mark.parametrize("path", _backend_files(), ids=lambda p: p.name)
def test_backend_files_have_the_same_keys_as_strings_json(path: Path) -> None:
    """hassfest compares the config flow translations against strings.json."""
    reference = set(_leaves(_load(STRINGS)))
    actual = set(_leaves(_load(path)))

    assert actual == reference, (
        f"{path.name} differs from strings.json, "
        f"missing {sorted(reference - actual)}, extra {sorted(actual - reference)}"
    )


@pytest.mark.parametrize("path", _backend_files(), ids=lambda p: p.name)
def test_backend_data_descriptions_hold_no_url(path: Path) -> None:
    """The hassfest translations validator rejects URLs in data_description."""
    for key, value in _leaves(_load(path)).items():
        if "data_description" not in key:
            continue
        assert "://" not in value, f"{path.name} has a URL in {key}"