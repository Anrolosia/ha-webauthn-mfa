"""Frontend translation loading for the custom WebAuthn surfaces.

The strings shown by the passkey ceremony page, the login overlay and the
sidebar panel cannot go through the Home Assistant translation system: two of
those three surfaces run *before* the user is authenticated, with no ``hass``
object and no websocket connection available on the client.

They live in ``www/translations/<lang>.json`` instead, keyed by domain, and are
read here then pushed into each surface by the code that serves it.

Every language is overlaid on top of English, so a partial translation falls
back key by key instead of failing as a whole.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.util.json import load_json_object

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

TRANSLATIONS_PATH = os.path.join(os.path.dirname(__file__), "www", "translations")
DEFAULT_LANGUAGE = "en"

_CACHE: dict[str, dict[str, Any]] = {}
_AVAILABLE: set[str] | None = None


def normalise_language(language: str | None) -> str:
    """Return a bare lowercase language code, `fr-CA` becomes `fr`."""
    if not language:
        return DEFAULT_LANGUAGE
    return language.split("-")[0].strip().lower() or DEFAULT_LANGUAGE


def js_literal(value: Any) -> str:
    """Return *value* as a JS literal safe to inline inside a script tag."""
    return json.dumps(value).replace("</", "<\\/")


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Return *base* with *override* applied recursively."""
    merged = dict(base)
    for key, value in override.items():
        current = merged.get(key)
        if isinstance(current, dict) and isinstance(value, dict):
            merged[key] = _deep_merge(current, value)
        else:
            merged[key] = value
    return merged


def _read(language: str) -> dict[str, Any]:
    """Read one translation file, returning an empty dict when unavailable."""
    path = os.path.join(TRANSLATIONS_PATH, f"{language}.json")
    if not os.path.exists(path):
        return {}
    try:
        return load_json_object(path).get(DOMAIN, {})
    except Exception:  # noqa: BLE001
        _LOGGER.warning(
            "WebAuthn: could not read the %s frontend translations",
            language,
            exc_info=True,
        )
        return {}


def _load(language: str) -> dict[str, Any]:
    """Return the English strings overlaid with *language*."""
    if (cached := _CACHE.get(language)) is not None:
        return cached

    english = _read(DEFAULT_LANGUAGE)
    if not english:
        _LOGGER.error(
            "WebAuthn: %s frontend translations are missing, "
            "the passkey page will render without strings",
            DEFAULT_LANGUAGE,
        )

    if language == DEFAULT_LANGUAGE:
        merged = english
    else:
        merged = _deep_merge(english, _read(language))

    _CACHE[language] = merged
    return merged


def _scan() -> set[str]:
    """Return the language codes that have a translation file on disk."""
    global _AVAILABLE  # noqa: PLW0603
    if _AVAILABLE is None:
        try:
            _AVAILABLE = {
                name.removesuffix(".json")
                for name in os.listdir(TRANSLATIONS_PATH)
                if name.endswith(".json")
            }
        except OSError:
            _LOGGER.exception("WebAuthn: cannot list %s", TRANSLATIONS_PATH)
            _AVAILABLE = set()
    return _AVAILABLE


async def async_resolve_language(hass: HomeAssistant, requested: str | None) -> str:
    """Return the language that will actually be served for *requested*."""
    code = normalise_language(requested)
    available = await hass.async_add_executor_job(_scan)
    return code if code in available else DEFAULT_LANGUAGE


async def async_get_strings(
    hass: HomeAssistant, language: str, section: str
) -> dict[str, Any]:
    """Return one section of the frontend strings for *language*."""
    strings = await hass.async_add_executor_job(_load, normalise_language(language))
    return strings.get(section, {})


def _load_all() -> dict[str, dict[str, Any]]:
    """Return the merged strings for every language present on disk."""
    return {language: _load(language) for language in sorted(_scan())}


async def async_get_all_strings(
    hass: HomeAssistant, section: str
) -> dict[str, dict[str, Any]]:
    """Return one section of the frontend strings, keyed by language."""
    everything = await hass.async_add_executor_job(_load_all)
    return {
        language: strings[section]
        for language, strings in everything.items()
        if strings.get(section)
    }
