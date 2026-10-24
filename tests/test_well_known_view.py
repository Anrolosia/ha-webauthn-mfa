"""Tests for the /.well-known/webauthn view."""

from __future__ import annotations

from http import HTTPStatus
import json
from unittest.mock import AsyncMock, MagicMock, patch

from custom_components.webauthn_mfa import async_setup_entry
from custom_components.webauthn_mfa.const import (
    CONF_EXPECTED_ORIGIN,
    CONF_RP_ID,
    CONF_RP_NAME,
)
from custom_components.webauthn_mfa.http_views import WebAuthnWellKnownView


async def test_well_known_webauthn_returns_origins():
    """The view returns the configured origins as JSON with proper headers."""
    origins = [
        "https://ha.example.com",
        "https://my-ha.tailscale.ts.net",
        "https://nabu.ui.nabu.casa",
    ]
    view = WebAuthnWellKnownView(origins)
    request = MagicMock()
    response = await view.get(request)

    assert response.status == HTTPStatus.OK
    assert response.content_type == "application/json"
    assert response.headers.get("Access-Control-Allow-Origin") == "*"
    assert response.headers.get("Cache-Control") == "max-age=3600"

    data = json.loads(response.text)
    assert data == {"origins": origins}


async def test_well_known_view_registered_only_with_related_origins():
    """Manifest is registered only when related origins outside rp_id exist."""
    hass = MagicMock()
    hass.auth._providers = {}  # noqa: SLF001
    hass.auth._store = MagicMock()  # noqa: SLF001
    hass.data = {}
    hass.http.register_view = MagicMock()
    hass.http.async_register_static_paths = AsyncMock()

    # Case 1: Same-site origins only -> view not registered
    entry_same_site = MagicMock()
    entry_same_site.data = {
        CONF_RP_ID: "ha.example.com",
        CONF_RP_NAME: "HA",
        CONF_EXPECTED_ORIGIN: "https://ha.example.com\nhttps://ha.example.com:8123",
    }
    with (
        patch("custom_components.webauthn_mfa.WebAuthnStore.async_load", AsyncMock()),
        patch("custom_components.webauthn_mfa._inject_login_script", AsyncMock()),
        patch("custom_components.webauthn_mfa.panel_module.async_setup", AsyncMock()),
        patch("custom_components.webauthn_mfa.add_extra_js_url"),
    ):
        await async_setup_entry(hass, entry_same_site)

    registered_views = [call.args[0] for call in hass.http.register_view.call_args_list]
    assert not any(isinstance(v, WebAuthnWellKnownView) for v in registered_views)

    # Case 2: Multi-origin with related origin outside rp_id -> view registered
    hass.http.register_view.reset_mock()
    entry_multi = MagicMock()
    entry_multi.data = {
        CONF_RP_ID: "ha.example.com",
        CONF_RP_NAME: "HA",
        CONF_EXPECTED_ORIGIN: "https://ha.example.com\nhttps://tailscale.ts.net",
    }
    with (
        patch("custom_components.webauthn_mfa.WebAuthnStore.async_load", AsyncMock()),
        patch("custom_components.webauthn_mfa._inject_login_script", AsyncMock()),
        patch("custom_components.webauthn_mfa.panel_module.async_setup", AsyncMock()),
        patch("custom_components.webauthn_mfa.add_extra_js_url"),
    ):
        await async_setup_entry(hass, entry_multi)

    registered_views = [call.args[0] for call in hass.http.register_view.call_args_list]
    well_known_views = [
        v for v in registered_views if isinstance(v, WebAuthnWellKnownView)
    ]
    assert len(well_known_views) == 1
    # Manifest must only publish external related origins, omitting same-site origins
    response = await well_known_views[0].get(MagicMock())
    assert json.loads(response.text) == {"origins": ["https://tailscale.ts.net"]}
