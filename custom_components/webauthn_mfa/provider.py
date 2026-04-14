"""WebAuthn authentication provider for Home Assistant."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.auth.models import Credentials, UserMeta
from homeassistant.auth.providers import AuthProvider, LoginFlow
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult

from .const import PROVIDER_TYPE
from .store import WebAuthnStore

_LOGGER = logging.getLogger(__name__)


class WebAuthnAuthProvider(AuthProvider):
    """Auth provider that authenticates users via WebAuthn / FIDO2 passkeys.

    This provider is injected at runtime into ``hass.auth._providers`` by
    ``async_setup``.  It surfaces as the *Passkey / Security Key* button on
    the native HA login page.

    The login flow is a single ``init`` step:
    1.  HA displays a text field (``webauthn_token``).
    2.  Our JS layer silently fills the field and clicks *Submit*.
    3.  ``async_step_init`` validates the short-lived token stored in
        ``hass.data`` by ``WebAuthnVerifyView`` and completes the flow.
    """

    DEFAULT_TITLE = "Passkey / Security Key"

    def __init__(
        self,
        hass: HomeAssistant,
        store: Any,
        webauthn_store: WebAuthnStore,
        config: dict[str, Any],
    ) -> None:
        """Initialise the provider."""
        super().__init__(hass, store, config)
        self.webauthn_store = webauthn_store

    # ── AuthProvider interface ────────────────────────────────────────────────

    @property
    def type(self) -> str:
        """Return the provider type identifier."""
        return PROVIDER_TYPE

    @property
    def id(self) -> str | None:
        """Return ``None`` — only one WebAuthn provider is supported."""
        return None

    @property
    def name(self) -> str:
        """Return the label shown on the HA login page."""
        return self.config.get("name", self.DEFAULT_TITLE)

    @property
    def support_mfa(self) -> bool:
        """WebAuthn is a primary authenticator, not a second factor."""
        return False

    async def async_login_flow(self, context: dict[str, Any] | None) -> LoginFlow:
        """Create and return a new login flow instance."""
        return WebAuthnLoginFlow(self)

    async def async_get_or_create_credentials(
        self, flow_result: dict[str, Any]
    ) -> Credentials:
        """Return the existing HA credential pre-linked during passkey registration.

        The credential is created and linked to the correct HA user by
        ``WebAuthnRegisterVerifyView.async_post`` at registration time, so at
        login we simply look it up by ``user_id``.
        """
        user_id: str = flow_result.get("user_id", "")
        username: str = flow_result.get("username", "")

        for credential in await self.async_credentials():
            if credential.data.get("user_id") == user_id:
                return credential

        # Fallback — should not happen if registration completed successfully.
        _LOGGER.warning(
            "WebAuthn: no pre-linked credential found for user_id=%s; "
            "a new (unlinked) credential will be created",
            user_id,
        )
        return self.async_create_credentials({"username": username, "user_id": user_id})

    async def async_user_meta_for_credentials(
        self, credentials: Credentials
    ) -> UserMeta:
        """Return metadata used to create a new HA user (fallback only)."""
        return UserMeta(
            name=credentials.data.get("username", "WebAuthn User"),
            is_active=True,
        )


class WebAuthnLoginFlow(LoginFlow):
    """Single-step login flow for WebAuthn passkey authentication."""

    def __init__(self, auth_provider: WebAuthnAuthProvider) -> None:
        """Initialise the flow."""
        super().__init__(auth_provider)
        self._auth_provider = auth_provider

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the (only) login step.

        The step exposes a ``webauthn_token`` field.  The token is a random
        string stored in ``hass.data`` by ``WebAuthnVerifyView`` after a
        successful cryptographic verification.  Our injected JS fills the
        field automatically so the user never has to type it manually.
        """
        schema = vol.Schema({vol.Required("webauthn_token"): str})
        placeholders = {
            "auth_url": f"/api/webauthn_mfa/authenticate?flow_id={self.flow_id}"
        }

        if user_input is not None:
            token = (user_input.get("webauthn_token") or "").strip()

            if not token:
                return self.async_show_form(
                    step_id="init",
                    data_schema=schema,
                    errors={"base": "invalid_auth"},
                    description_placeholders=placeholders,
                )

            result_key = f"webauthn_mfa_result_{token}"
            result: dict[str, Any] | None = self._auth_provider.hass.data.pop(
                result_key, None
            )

            if not result or not result.get("success"):
                return self.async_show_form(
                    step_id="init",
                    data_schema=schema,
                    errors={"base": "invalid_auth"},
                    description_placeholders=placeholders,
                )

            user_id: str = result.get("user_id", "")
            username: str = result.get("username", "")

            if not user_id and not username:
                return self.async_abort(reason="invalid_auth")

            _LOGGER.info(
                "WebAuthn: authentication successful for user_id=%s (%s)",
                user_id,
                username,
            )
            return await self.async_finish({"username": username, "user_id": user_id})

        return self.async_show_form(
            step_id="init",
            data_schema=schema,
            description_placeholders=placeholders,
        )
