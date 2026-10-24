"""Tests for WebAuthn config flow validation and normalization."""

from __future__ import annotations

from custom_components.webauthn_mfa import CONFIG_SCHEMA
from custom_components.webauthn_mfa.config_flow import _clean, _validate
from custom_components.webauthn_mfa.const import (
    CONF_EXPECTED_ORIGIN,
    CONF_RP_ID,
    CONF_RP_NAME,
    DOMAIN,
)


def test_validate_single_origin_success():
    """A single origin matching the RP ID is valid."""
    data = {
        CONF_RP_ID: "ha.example.com",
        CONF_RP_NAME: "Home Assistant",
        CONF_EXPECTED_ORIGIN: "https://ha.example.com",
    }
    assert _validate(data) == {}


def test_validate_single_origin_mismatch():
    """An origin not matching the RP ID returns origin_mismatch."""
    data = {
        CONF_RP_ID: "ha.example.com",
        CONF_RP_NAME: "Home Assistant",
        CONF_EXPECTED_ORIGIN: "https://different.example.org",
    }
    assert _validate(data) == {CONF_EXPECTED_ORIGIN: "origin_mismatch"}


def test_validate_multi_origin_success():
    """Multiple HTTPS origins with at least one matching the RP ID are valid."""
    data = {
        CONF_RP_ID: "ha.example.com",
        CONF_RP_NAME: "Home Assistant",
        CONF_EXPECTED_ORIGIN: (
            "https://ha.example.com, https://my-ha.tailscale.ts.net, "
            "https://abc123xyz.ui.nabu.casa"
        ),
    }
    assert _validate(data) == {}


def test_validate_multi_origin_requires_https_for_related_origins():
    """Related origins on distinct domains must use HTTPS."""
    data = {
        CONF_RP_ID: "ha.example.com",
        CONF_RP_NAME: "Home Assistant",
        CONF_EXPECTED_ORIGIN: ("https://ha.example.com, http://my-ha.tailscale.ts.net"),
    }
    assert _validate(data) == {CONF_EXPECTED_ORIGIN: "related_origin_must_be_https"}


def test_validate_multi_origin_limit_five_external_origins():
    """At most 5 external related origins are permitted."""
    external = ", ".join(f"https://ext{i}.other.com" for i in range(6))
    data = {
        CONF_RP_ID: "ha.example.com",
        CONF_RP_NAME: "Home Assistant",
        CONF_EXPECTED_ORIGIN: f"https://ha.example.com, {external}",
    }
    assert _validate(data) == {CONF_EXPECTED_ORIGIN: "too_many_origins"}


def test_validate_multi_origin_exactly_five_external_origins_accepted():
    """Up to 5 external origins outside the RP ID are accepted."""
    external = ", ".join(f"https://ext{i}.other.com" for i in range(5))
    data = {
        CONF_RP_ID: "ha.example.com",
        CONF_RP_NAME: "Home Assistant",
        CONF_EXPECTED_ORIGIN: f"https://ha.example.com, {external}",
    }
    assert _validate(data) == {}


def test_validate_same_site_origins_do_not_count_towards_limit():
    """Same-site origins sharing the RP ID do not count against the 5 limit."""
    subdomains = ", ".join(f"https://sub{i}.ha.example.com" for i in range(8))
    data = {
        CONF_RP_ID: "ha.example.com",
        CONF_RP_NAME: "Home Assistant",
        CONF_EXPECTED_ORIGIN: f"https://ha.example.com, {subdomains}",
    }
    assert _validate(data) == {}


def test_validate_multi_origin_requires_exact_rp_id_match():
    """Multi-origin setup requires at least one origin host to equal rp_id exactly."""
    data = {
        CONF_RP_ID: "example.com",  # parent domain
        CONF_RP_NAME: "Home Assistant",
        CONF_EXPECTED_ORIGIN: (
            "https://ha.example.com\nhttps://my-ha.tailscale.ts.net"
        ),
    }
    assert _validate(data) == {CONF_EXPECTED_ORIGIN: "related_origin_rp_mismatch"}


def test_validate_single_origin_allows_parent_domain():
    """Single origin setup allows rp_id to be a parent domain."""
    data = {
        CONF_RP_ID: "example.com",  # parent domain
        CONF_RP_NAME: "Home Assistant",
        CONF_EXPECTED_ORIGIN: "https://ha.example.com",
    }
    assert _validate(data) == {}


def test_validate_same_site_multi_origin_allows_parent_domain():
    """Multiple same-site origins allow rp_id to be a parent domain."""
    data = {
        CONF_RP_ID: "example.com",  # parent domain
        CONF_RP_NAME: "Home Assistant",
        CONF_EXPECTED_ORIGIN: "https://ha.example.com\nhttps://ha.example.com:8123",
    }
    assert _validate(data) == {}


def test_validate_multi_origin_mismatch_when_no_rp_origin_matches():
    """If no origin matches the RP ID, origin_mismatch is returned."""
    data = {
        CONF_RP_ID: "ha.example.com",
        CONF_RP_NAME: "Home Assistant",
        CONF_EXPECTED_ORIGIN: ("https://tailscale.ts.net, https://abc.ui.nabu.casa"),
    }
    assert _validate(data) == {CONF_EXPECTED_ORIGIN: "origin_mismatch"}


def test_clean_multi_origin():
    """_clean canonicalizes and joins origins with line breaks."""
    data = {
        CONF_RP_ID: "HA.Example.com ",
        CONF_RP_NAME: " Home Assistant ",
        CONF_EXPECTED_ORIGIN: (
            "https://ha.example.com:443/\nhttps://tailscale.ts.net:8443/"
        ),
    }
    cleaned = _clean(data)
    assert cleaned[CONF_RP_ID] == "ha.example.com"
    assert cleaned[CONF_RP_NAME] == "Home Assistant"
    assert (
        cleaned[CONF_EXPECTED_ORIGIN]
        == "https://ha.example.com\nhttps://tailscale.ts.net:8443"
    )


def test_clean_multi_origin_from_yaml_array():
    """_clean handles a YAML list of origins."""
    data = {
        CONF_RP_ID: "ha.example.com",
        CONF_RP_NAME: "Home Assistant",
        CONF_EXPECTED_ORIGIN: [
            "https://ha.example.com:443/",
            "https://tailscale.ts.net:8443/",
        ],
    }
    cleaned = _clean(data)
    assert (
        cleaned[CONF_EXPECTED_ORIGIN]
        == "https://ha.example.com\nhttps://tailscale.ts.net:8443"
    )


def test_config_schema_accepts_yaml_array():
    """CONFIG_SCHEMA validates and accepts an array of origins in YAML."""
    raw = {
        DOMAIN: {
            CONF_RP_ID: "ha.example.com",
            CONF_EXPECTED_ORIGIN: [
                "https://ha.example.com",
                "https://tailscale.ts.net",
            ],
        }
    }
    validated = CONFIG_SCHEMA(raw)
    assert validated[DOMAIN][CONF_EXPECTED_ORIGIN] == [
        "https://ha.example.com",
        "https://tailscale.ts.net",
    ]


def test_config_schema_accepts_yaml_single_string():
    """CONFIG_SCHEMA converts a single string origin in YAML to a list."""
    raw = {
        DOMAIN: {
            CONF_RP_ID: "ha.example.com",
            CONF_EXPECTED_ORIGIN: "https://ha.example.com",
        }
    }
    validated = CONFIG_SCHEMA(raw)
    assert validated[DOMAIN][CONF_EXPECTED_ORIGIN] == ["https://ha.example.com"]
