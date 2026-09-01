"""Origin normalisation helpers for WebAuthn verification.

The WebAuthn ceremony compares the configured origin with the one the browser
puts in ``clientDataJSON``, byte for byte. Browsers omit the port whenever it
is the default one for the scheme, so a configured origin that spells the port
out never matches, and the ceremony fails without any server side error.

Home Assistant 2026.8 changed the default port of new installs from 8123 to 80,
which makes this mismatch far more common, so both spellings are accepted.
"""

from __future__ import annotations

from urllib.parse import urlparse

DEFAULT_PORTS = {"http": 80, "https": 443}


def normalize_origin(origin: str) -> str:
    """Return *origin* reduced to ``scheme://host[:port]``.

    Trailing slashes, paths and an explicitly written default port are dropped,
    so "https://ha.example.com:443/" and "https://ha.example.com" collapse to
    the same value. Input that cannot be parsed is returned trimmed, and the
    config flow reports it as invalid.
    """
    cleaned = origin.strip().rstrip("/")
    parsed = urlparse(cleaned)

    try:
        port = parsed.port
    except ValueError:
        return cleaned

    if not parsed.scheme or not parsed.hostname:
        return cleaned

    scheme = parsed.scheme.lower()
    host = parsed.hostname.lower()

    if port is None or port == DEFAULT_PORTS.get(scheme):
        return f"{scheme}://{host}"
    return f"{scheme}://{host}:{port}"


def expected_origins(origin: str) -> list[str]:
    """Return every origin string a browser may legitimately send.

    A browser omits a default port, but a reverse proxy setup documented with
    the port spelled out is just as valid, so both are accepted.
    """
    normalized = normalize_origin(origin)
    parsed = urlparse(normalized)

    try:
        port = parsed.port
    except ValueError:
        return [normalized]

    default_port = DEFAULT_PORTS.get(parsed.scheme.lower())
    if default_port is None or port is not None or not parsed.hostname:
        return [normalized]

    return [normalized, f"{normalized}:{default_port}"]
