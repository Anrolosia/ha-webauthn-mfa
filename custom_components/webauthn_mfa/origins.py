"""Origin normalisation helpers for WebAuthn verification.

The WebAuthn ceremony compares the configured origin with the one the browser
puts in ``clientDataJSON``, byte for byte. Browsers omit the port whenever it
is the default one for the scheme, so a configured origin that spells the port
out never matches, and the ceremony fails without any server side error.

Home Assistant 2026.8 changed the default port of new installs from 8123 to 80,
which makes this mismatch far more common, so both spellings are accepted.

Multiple origins are supported for WebAuthn Level 3 Related Origin Requests (ROR),
allowing Home Assistant instances accessed via multiple URLs (e.g. Tailscale,
Nabu Casa, external domain) to share passkeys.
"""

from __future__ import annotations

import re
from urllib.parse import urlparse

DEFAULT_PORTS = {"http": 80, "https": 443}


def parse_origins(raw: str | list[str]) -> list[str]:
    """Split line-break or comma separated origins into a list of strings."""
    if isinstance(raw, list):
        items: list[str] = []
        for r in raw:
            items.extend(re.split(r"[\n,]+", str(r)))
    else:
        items = re.split(r"[\n,]+", raw or "")

    result: list[str] = []
    seen: set[str] = set()
    for item in items:
        cleaned = item.strip()
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            result.append(cleaned)
    return result


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


def canonical_origins(raw: str | list[str]) -> list[str]:
    """Return unique, normalized origins (scheme://host[:port])."""
    seen: set[str] = set()
    result: list[str] = []
    for item in parse_origins(raw):
        norm = normalize_origin(item)
        if norm and norm not in seen:
            seen.add(norm)
            result.append(norm)
    return result


def expected_origins(raw: str | list[str]) -> list[str]:
    """Return every origin string a browser may legitimately send.

    A browser omits a default port, but a reverse proxy setup documented with
    the port spelled out is just as valid, so both are accepted.
    Accepts a single origin string, a comma/newline separated list,
    or a list of strings.
    """
    origins_to_process = parse_origins(raw)
    if not origins_to_process:
        return []

    result: list[str] = []
    seen: set[str] = set()

    for origin in origins_to_process:
        normalized = normalize_origin(origin)
        parsed = urlparse(normalized)

        try:
            port = parsed.port
        except ValueError:
            if normalized not in seen:
                seen.add(normalized)
                result.append(normalized)
            continue

        default_port = DEFAULT_PORTS.get(parsed.scheme.lower())
        candidates = [normalized]
        if default_port is not None and port is None and parsed.hostname:
            candidates.append(f"{normalized}:{default_port}")

        for cand in candidates:
            if cand not in seen:
                seen.add(cand)
                result.append(cand)

    return result


def related_origins(raw: str | list[str], rp_id: str) -> list[str]:
    """Return canonical origins that do not match rp_id (external related origins).

    Same-site origins sharing the rp_id domain do not require Related Origin
    Requests and are excluded. Only origins outside rp_id need to be published
    in the well-known manifest and count against the manifest origin limit.
    """
    rp = rp_id.lower().strip()
    external: list[str] = []
    for origin in canonical_origins(raw):
        parsed = urlparse(origin)
        host = (parsed.hostname or "").lower()
        if host and host != rp and not host.endswith(f".{rp}"):
            external.append(origin)
    return external
