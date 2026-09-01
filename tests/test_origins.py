"""Tests for origin normalisation helpers."""

from __future__ import annotations

import pytest

from custom_components.webauthn_mfa.origins import expected_origins, normalize_origin


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        # Already canonical.
        ("https://ha.test", "https://ha.test"),
        # Default ports are dropped, the browser never sends them.
        ("https://ha.test:443", "https://ha.test"),
        ("http://ha.test:80", "http://ha.test"),
        # Trailing slashes and paths are not part of an origin.
        ("https://ha.test/", "https://ha.test"),
        ("https://ha.test:443/", "https://ha.test"),
        # Case is insignificant in a host name, but not in a comparison.
        ("https://HA.Test", "https://ha.test"),
        ("HTTPS://ha.test", "https://ha.test"),
        # Surrounding whitespace from a copy paste.
        ("  https://ha.test  ", "https://ha.test"),
        # Non default ports must survive untouched.
        ("https://ha.test:8123", "https://ha.test:8123"),
        ("http://ha.test:8123", "http://ha.test:8123"),
        # A default port of the other scheme is not a default port here.
        ("https://ha.test:80", "https://ha.test:80"),
        ("http://ha.test:443", "http://ha.test:443"),
    ],
)
def test_normalize_origin(raw: str, expected: str) -> None:
    """Default ports, slashes and case collapse, custom ports survive."""
    assert normalize_origin(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "ha.test",
        "not an origin",
        "https://ha.test:notaport",
    ],
)
def test_normalize_origin_passes_through_unparseable(raw: str) -> None:
    """Input the config flow rejects is returned trimmed, never raising."""
    assert normalize_origin(raw) == raw.strip().rstrip("/")


def test_expected_origins_accepts_both_spellings_for_https() -> None:
    """A browser omits :443, a user documenting a proxy often writes it."""
    assert expected_origins("https://ha.test") == [
        "https://ha.test",
        "https://ha.test:443",
    ]


def test_expected_origins_accepts_both_spellings_for_http() -> None:
    """Home Assistant 2026.8 made port 80 the default for new installs."""
    assert expected_origins("http://ha.test") == [
        "http://ha.test",
        "http://ha.test:80",
    ]


def test_expected_origins_is_stable_when_the_port_is_written_out() -> None:
    """A configured :443 yields the same pair as a configured bare host."""
    assert expected_origins("https://ha.test:443") == expected_origins(
        "https://ha.test"
    )


def test_expected_origins_keeps_a_custom_port_alone() -> None:
    """A non default port has no alternative spelling to accept."""
    assert expected_origins("https://ha.test:8123") == ["https://ha.test:8123"]


def test_expected_origins_never_returns_duplicates() -> None:
    """Duplicate entries would make the py_webauthn error message confusing."""
    for raw in ("https://ha.test", "https://ha.test:443", "https://ha.test:8123"):
        origins = expected_origins(raw)
        assert len(origins) == len(set(origins))