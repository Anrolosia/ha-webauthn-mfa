"""WebAuthn / Passkey Authentication — Home Assistant custom component.

This integration injects a WebAuthn auth provider into HA at startup.
Users can register FIDO2 passkeys (hardware keys, biometrics, password
managers such as Bitwarden / 1Password) and use them instead of a password
to sign in to Home Assistant.

Architecture
------------
* ``provider.py``   — HA auth provider + login flow (token-based step).
* ``store.py``      — Credential persistence via HA storage.
* ``http_views.py`` — REST API for challenge/verify (auth) and
                      challenge/verify (registration) + list/delete.
* ``panel.py``      — Sidebar panel for passkey management.
* ``www/``          — Static assets (HTML page, injected JS, panel JS).

Login flow
----------
1. User visits ``/auth/authorize``.
2. Our injected script adds a *Passkey / Security Key* option.
3. Clicking it triggers ``WebAuthnLoginFlow`` → our ``authenticate.html``
   page opens and calls ``navigator.credentials.get()``.
4. ``WebAuthnVerifyView`` verifies the cryptographic assertion and stores
   a short-lived token in ``hass.data``.
5. The JS layer fills the HA form and submits it; ``async_step_init``
   validates the token and completes the OAuth2 flow natively so that
   the Service Worker persists the session tokens correctly.

Configuration (``configuration.yaml``)
---------------------------------------
.. code-block:: yaml

    webauthn_mfa:
      rp_id: "homeassistant.local"
      rp_name: "Home Assistant"
      expected_origin: "https://homeassistant.local"
"""

from __future__ import annotations

from collections import OrderedDict
from http import HTTPStatus
from ipaddress import ip_address as _parse_ip
import logging
import os
from typing import Any

from aiohttp.web import Response as AiohttpResponse
import voluptuous as vol

from homeassistant import data_entry_flow
from homeassistant.components.auth import DOMAIN as AUTH_DOMAIN
from homeassistant.components.auth import indieauth
from homeassistant.components.auth.login_flow import LoginFlowIndexView
from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.components.http.data_validator import RequestDataValidator
from homeassistant.core import HomeAssistant
import homeassistant.helpers.config_validation as cv

from . import panel as panel_module
from .const import (
    CONF_EXPECTED_ORIGIN,
    CONF_RP_ID,
    CONF_RP_NAME,
    DEFAULT_RP_NAME,
    DOMAIN,
)
from .http_views import (
    WebAuthnAuthenticateView,
    WebAuthnChallengeView,
    WebAuthnDeleteView,
    WebAuthnListView,
    WebAuthnRegisterChallengeView,
    WebAuthnRegisterVerifyView,
    WebAuthnVerifyView,
)
from .provider import WebAuthnAuthProvider
from .store import WebAuthnStore

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            {
                vol.Required(CONF_RP_ID): cv.string,
                vol.Optional(CONF_RP_NAME, default=DEFAULT_RP_NAME): cv.string,
                vol.Required(CONF_EXPECTED_ORIGIN): cv.string,
            }
        )
    },
    extra=vol.ALLOW_EXTRA,
)


# ---------------------------------------------------------------------------
# Custom LoginFlowIndexView
# ---------------------------------------------------------------------------


class WebAuthnLoginFlowIndexView(LoginFlowIndexView):
    """Extend the default ``LoginFlowIndexView`` to intercept WebAuthn flows.

    All non-WebAuthn handlers are forwarded to the original implementation so
    existing login methods continue to work unchanged.
    """

    @RequestDataValidator(
        vol.Schema(
            {
                vol.Required("client_id"): str,
                vol.Required("handler"): vol.Any(str, list),
                vol.Required("redirect_uri"): str,
                vol.Optional("type", default="authorize"): str,
            }
        )
    )
    async def post(self, request: Any, data: dict[str, Any]) -> Any:
        """Create a new login flow, routing WebAuthn flows through our logic."""
        handler = data.get("handler")
        handler_type = handler[0] if isinstance(handler, list) else handler

        if handler_type != "webauthn":
            # Delegate non-webauthn handlers to the HA default implementation.
            return await super().post(request)

        client_id: str = data.get("client_id", "")
        redirect_uri: str = data.get("redirect_uri", "")

        if not indieauth.verify_client_id(client_id):
            return self.json_message("Invalid client id", HTTPStatus.BAD_REQUEST)

        try:
            ip_addr = _parse_ip(request.remote)
        except ValueError:
            ip_addr = None

        try:
            result = await self._flow_mgr.async_init(
                ("webauthn", None),
                context={
                    "request": request,
                    "credential_only": data.get("type") == "link_user",
                    "redirect_uri": redirect_uri,
                    "ip_address": ip_addr,
                },
            )
        except data_entry_flow.UnknownHandler:
            return self.json_message("Invalid handler", HTTPStatus.NOT_FOUND)

        return await self._async_flow_result_to_response(request, client_id, result)


# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------


async def async_setup(hass: HomeAssistant, config: dict[str, Any]) -> bool:
    """Set up the WebAuthn / Passkey Authentication integration."""
    cfg: dict[str, Any] = config[DOMAIN]
    rp_id: str = cfg[CONF_RP_ID]
    rp_name: str = cfg[CONF_RP_NAME]
    expected_origin: str = cfg[CONF_EXPECTED_ORIGIN]

    # 1. Persistent credential store.
    store = WebAuthnStore(hass)
    await store.async_load()
    hass.data[DOMAIN] = {"store": store}

    # 2. Inject the WebAuthn auth provider (appended so native login stays first).
    provider = WebAuthnAuthProvider(
        hass,
        hass.auth._store,  # noqa: SLF001
        store,
        {"type": "webauthn", CONF_RP_ID: rp_id},
    )
    providers: OrderedDict = OrderedDict(hass.auth._providers)  # noqa: SLF001
    providers[(provider.type, provider.id)] = provider
    hass.auth._providers = providers  # noqa: SLF001
    _LOGGER.info("WebAuthn: provider registered (rp_id=%s)", rp_id)

    # 3. Replace the default LoginFlowIndexView so we can intercept WebAuthn
    #    flow creation without breaking other auth providers.
    _replace_login_flow_view(hass)

    # 4. Register HTTP API views.
    hass.http.register_view(WebAuthnAuthenticateView(rp_id))
    hass.http.register_view(WebAuthnChallengeView(store, rp_id))
    hass.http.register_view(WebAuthnVerifyView(hass, store, rp_id, expected_origin))
    hass.http.register_view(WebAuthnRegisterChallengeView(store, rp_id, rp_name))
    hass.http.register_view(
        WebAuthnRegisterVerifyView(hass, store, rp_id, expected_origin)
    )
    hass.http.register_view(WebAuthnListView(store))
    hass.http.register_view(WebAuthnDeleteView(store))

    # 5. Inject the login helper script into /auth/authorize.
    www_path = os.path.join(os.path.dirname(__file__), "www")
    await _inject_login_script(hass, www_path)

    # 6. Register the post-login JS (loaded on every HA page after login).
    webauthn_js = os.path.join(www_path, "webauthn.js")
    await hass.http.async_register_static_paths(
        [StaticPathConfig("/webauthn_mfa/webauthn.js", webauthn_js, cache_headers=True)]
    )
    add_extra_js_url(hass, "/webauthn_mfa/webauthn.js")

    # 7. Sidebar panel.
    await panel_module.async_setup(hass)

    _LOGGER.info("WebAuthn: setup complete")
    return True


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _replace_login_flow_view(hass: HomeAssistant) -> None:
    """Swap the default ``LoginFlowIndexView`` for our extended version."""
    store_result = hass.data.get(AUTH_DOMAIN)

    router = hass.http.app.router
    target_url = LoginFlowIndexView.url

    # Remove the existing route.
    for resource in list(router._resources):  # noqa: SLF001
        if getattr(resource, "canonical", None) == target_url:
            router._resources.remove(resource)  # noqa: SLF001
            break

    if hasattr(router, "_resource_index"):
        for route in list(router._resource_index.get(target_url, [])):  # noqa: SLF001
            if getattr(route, "canonical", None) == target_url:
                router._resource_index[target_url].remove(route)  # noqa: SLF001

    if store_result is not None:
        hass.http.register_view(
            WebAuthnLoginFlowIndexView(hass.auth.login_flow, store_result)
        )
    else:
        _LOGGER.warning(
            "WebAuthn: auth store_result unavailable — "
            "LoginFlowIndexView not replaced; text-token fallback will be used"
        )


async def _inject_login_script(hass: HomeAssistant, www_path: str) -> None:
    """Patch the ``/auth/authorize`` handler to inline the login helper script."""
    js_path = os.path.join(www_path, "webauthn-login.js")

    def _read_file(path: str) -> str:
        with open(path, encoding="utf-8") as f:
            return f.read()

    js_content: str = await hass.async_add_executor_job(_read_file, js_path)
    script_tag = f'<script type="module">{js_content}</script>'

    for resource in hass.http.app.router._resources:  # noqa: SLF001
        if getattr(resource, "canonical", None) != "/auth/authorize":
            continue
        for route in resource:
            if route.method not in ("GET", "*"):
                continue
            original = route._handler  # noqa: SLF001

            async def _patched(request: Any, _orig=original, _tag=script_tag) -> Any:
                response = await _orig(request)
                try:
                    if hasattr(response, "_path"):

                        def _read_bytes(path: str) -> bytes:
                            with open(path, "rb") as f:
                                return f.read()

                        body: bytes = await request.app["hass"].async_add_executor_job(
                            _read_bytes,
                            str(response._path),  # noqa: SLF001
                        )
                        html = body.decode("utf-8")
                    elif getattr(response, "body", None):
                        html = response.body.decode("utf-8")
                    else:
                        return response

                    if "</body>" in html:
                        html = html.replace("</body>", _tag + "\n</body>")
                        headers = {
                            k: v
                            for k, v in response.headers.items()
                            if k.lower() not in ("content-length", "transfer-encoding")
                        }
                        return AiohttpResponse(
                            text=html, content_type="text/html", headers=headers
                        )
                except Exception:  # noqa: BLE001
                    _LOGGER.warning(
                        "WebAuthn: failed to inject script into /auth/authorize",
                        exc_info=True,
                    )
                return response

            route._handler = _patched  # noqa: SLF001
            return

    _LOGGER.warning("WebAuthn: /auth/authorize route not found — script not injected")
