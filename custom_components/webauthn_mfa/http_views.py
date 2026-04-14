"""HTTP views for WebAuthn / Passkey Authentication."""

from __future__ import annotations

import base64
import logging
import os
import secrets
from typing import Any

from aiohttp.web import Request, Response
from aiohttp.web import Response as AiohttpResponse
import webauthn
from webauthn.helpers import options_to_json
from webauthn.helpers.base64url_to_bytes import base64url_to_bytes
from webauthn.helpers.exceptions import (
    InvalidAuthenticationResponse,
    InvalidRegistrationResponse,
)
from webauthn.helpers.structs import (
    AuthenticationCredential,
    AuthenticatorAssertionResponse,
    AuthenticatorAttestationResponse,
    AuthenticatorSelectionCriteria,
    PublicKeyCredentialDescriptor,
    RegistrationCredential,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

from homeassistant.components.http import HomeAssistantView
from homeassistant.core import HomeAssistant

from .const import PROVIDER_TYPE
from .store import WebAuthnStore

_LOGGER = logging.getLogger(__name__)

# In-memory challenge store: key → {challenge, ...}
# Keys: ``flow_id`` (authentication) or ``reg_<user_id>`` (registration).
_PENDING_CHALLENGES: dict[str, dict[str, Any]] = {}


class WebAuthnAuthenticateView(HomeAssistantView):
    """Serve the passkey authentication HTML page.

    ``GET /api/webauthn_mfa/authenticate?flow_id=<id>&return_url=<url>``

    This page is opened automatically by the injected login script when the
    user selects *Passkey / Security Key* on the HA login form.
    """

    url = "/api/webauthn_mfa/authenticate"
    name = "api:webauthn_mfa:authenticate"
    requires_auth = False

    def __init__(self, rp_id: str) -> None:
        """Initialise view."""
        self._rp_id = rp_id
        self._html_path = os.path.join(
            os.path.dirname(__file__), "www", "authenticate.html"
        )

    async def get(self, request: Request) -> Response:
        """Return the HTML authentication page with flow context injected."""
        flow_id = request.rel_url.query.get("flow_id", "")
        return_url = request.rel_url.query.get("return_url", "")

        hass: HomeAssistant = request.app["hass"]

        def _read_html(path: str) -> str:
            with open(path, encoding="utf-8") as f:
                return f.read()

        html: str = await hass.async_add_executor_job(_read_html, self._html_path)
        html = html.replace("{{FLOW_ID}}", flow_id)
        html = html.replace("{{RETURN_URL}}", return_url)

        return AiohttpResponse(text=html, content_type="text/html")


class WebAuthnChallengeView(HomeAssistantView):
    """Generate a WebAuthn authentication challenge.

    ``POST /api/webauthn_mfa/challenge``
    Body: ``{"flow_id": "<id>"}``

    Uses *discoverable credentials* (resident keys) so all registered passkeys
    across all non-system users are offered to the authenticator.
    """

    url = "/api/webauthn_mfa/challenge"
    name = "api:webauthn_mfa:challenge"
    requires_auth = False

    def __init__(self, store: WebAuthnStore, rp_id: str) -> None:
        """Initialise view."""
        self._store = store
        self._rp_id = rp_id

    async def post(self, request: Request) -> Response:
        """Return a fresh authentication options JSON for the browser."""
        body = await request.json()
        flow_id: str = body.get("flow_id", "").strip()

        if not flow_id:
            return self.json({"error": "flow_id required"}, status_code=400)

        hass: HomeAssistant = request.app["hass"]

        # Collect all credentials from all non-system users so the browser can
        # perform a discoverable credential lookup.
        users = await hass.auth.async_get_users()
        allow_credentials: list[PublicKeyCredentialDescriptor] = [
            PublicKeyCredentialDescriptor(id=bytes.fromhex(cred["credential_id"]))
            for user in users
            if not user.system_generated
            for cred in self._store.get_credentials(user.id)
        ]

        if not allow_credentials:
            return self.json(
                {
                    "error": "no_credentials",
                    "message": "No passkey registered for this instance",
                },
                status_code=404,
            )

        challenge = secrets.token_bytes(32)
        _PENDING_CHALLENGES[flow_id] = {"challenge": challenge}

        options = webauthn.generate_authentication_options(
            rp_id=self._rp_id,
            challenge=challenge,
            allow_credentials=allow_credentials,
        )

        return Response(text=options_to_json(options), content_type="application/json")


class WebAuthnVerifyView(HomeAssistantView):
    """Verify a WebAuthn authentication assertion.

    ``POST /api/webauthn_mfa/verify``
    Body: ``{"flow_id": "...", "response": {<WebAuthn assertion>}}``

    On success stores a short-lived token in ``hass.data`` so that
    ``WebAuthnLoginFlow.async_step_init`` can complete the HA login flow.
    """

    url = "/api/webauthn_mfa/verify"
    name = "api:webauthn_mfa:verify"
    requires_auth = False

    def __init__(
        self,
        hass: HomeAssistant,
        store: WebAuthnStore,
        rp_id: str,
        expected_origin: str,
    ) -> None:
        """Initialise view."""
        self._hass = hass
        self._store = store
        self._rp_id = rp_id
        self._expected_origin = expected_origin

    async def post(self, request: Request) -> Response:  # noqa: PLR0911
        """Verify the assertion and issue a short-lived login token."""
        body = await request.json()
        flow_id: str = body.get("flow_id", "").strip()
        assertion: dict[str, Any] | None = body.get("response")

        if not flow_id or not assertion:
            return self.json(
                {"error": "flow_id and response required"}, status_code=400
            )

        pending = _PENDING_CHALLENGES.pop(flow_id, None)
        if not pending:
            return self.json({"error": "challenge_expired"}, status_code=400)

        # Locate the stored credential from its hex ID.
        raw_id_b64: str = assertion.get("id", "")
        try:
            credential_id_bytes = base64.urlsafe_b64decode(
                raw_id_b64 + "=" * (-len(raw_id_b64) % 4)
            )
        except Exception:  # noqa: BLE001
            return self.json({"error": "invalid_credential_id"}, status_code=400)

        credential_id_hex = credential_id_bytes.hex()
        match = self._store.find_user_by_credential_id(credential_id_hex)
        if match is None:
            return self.json({"error": "credential_not_found"}, status_code=404)

        user_id, stored_credential = match

        # Cryptographic verification.
        try:
            resp = assertion.get("response", {})
            auth_credential = AuthenticationCredential(
                id=assertion["id"],
                raw_id=base64url_to_bytes(assertion["rawId"]),
                response=AuthenticatorAssertionResponse(
                    client_data_json=base64url_to_bytes(resp["clientDataJSON"]),
                    authenticator_data=base64url_to_bytes(resp["authenticatorData"]),
                    signature=base64url_to_bytes(resp["signature"]),
                    user_handle=(
                        base64url_to_bytes(resp["userHandle"])
                        if resp.get("userHandle")
                        else None
                    ),
                ),
                type=assertion.get("type", "public-key"),
            )

            verification = webauthn.verify_authentication_response(
                credential=auth_credential,
                expected_rp_id=self._rp_id,
                expected_challenge=pending["challenge"],
                expected_origin=self._expected_origin,
                credential_public_key=bytes.fromhex(stored_credential["public_key"]),
                credential_current_sign_count=stored_credential.get("sign_count", 0),
                require_user_verification=True,
            )

        except InvalidAuthenticationResponse as err:
            _LOGGER.warning("WebAuthn: authentication verification failed: %s", err)
            return self.json(
                {"error": "verification_failed", "message": str(err)}, status_code=401
            )
        except Exception as err:
            _LOGGER.exception("WebAuthn: unexpected error during verification")
            return self.json({"error": str(err)}, status_code=500)

        # Update the sign counter.
        await self._store.async_update_sign_count(
            user_id, credential_id_bytes, verification.new_sign_count
        )

        # Resolve a human-readable username for the flow.
        user = await self._hass.auth.async_get_user(user_id)
        username = user.name if user else user_id

        # Issue a short-lived token consumed by WebAuthnLoginFlow.
        token = secrets.token_urlsafe(16)
        self._hass.data[f"webauthn_mfa_result_{token}"] = {
            "success": True,
            "username": username,
            "user_id": user_id,
        }

        _LOGGER.info(
            "WebAuthn: authentication OK for user_id=%s (%s)", user_id, username
        )
        return self.json({"success": True, "token": token})


class WebAuthnRegisterChallengeView(HomeAssistantView):
    """Generate a WebAuthn registration challenge for the authenticated user.

    ``POST /api/webauthn_mfa/register/challenge``
    Requires a valid HA session (``requires_auth = True``).
    """

    url = "/api/webauthn_mfa/register/challenge"
    name = "api:webauthn_mfa:register_challenge"
    requires_auth = True

    def __init__(self, store: WebAuthnStore, rp_id: str, rp_name: str) -> None:
        """Initialise view."""
        self._store = store
        self._rp_id = rp_id
        self._rp_name = rp_name

    async def post(self, request: Request) -> Response:
        """Return registration options for the authenticated user."""
        user = request["hass_user"]
        user_id: str = user.id
        username: str = user.name

        # Exclude credentials already registered for this user.
        exclude_credentials = [
            PublicKeyCredentialDescriptor(id=bytes.fromhex(c["credential_id"]))
            for c in self._store.get_credentials(user_id)
        ]

        challenge = secrets.token_bytes(32)
        _PENDING_CHALLENGES[f"reg_{user_id}"] = {"challenge": challenge}

        options = webauthn.generate_registration_options(
            rp_id=self._rp_id,
            rp_name=self._rp_name,
            user_id=user_id.encode(),
            user_name=username,
            challenge=challenge,
            exclude_credentials=exclude_credentials,
            authenticator_selection=AuthenticatorSelectionCriteria(
                user_verification=UserVerificationRequirement.REQUIRED,
                resident_key=ResidentKeyRequirement.PREFERRED,
            ),
        )

        return Response(text=options_to_json(options), content_type="application/json")


class WebAuthnRegisterVerifyView(HomeAssistantView):
    """Verify a WebAuthn registration response and persist the new credential.

    ``POST /api/webauthn_mfa/register/verify``
    Requires a valid HA session (``requires_auth = True``).

    After saving the WebAuthn credential this view also creates and links an
    HA auth credential so that subsequent logins map to the correct user
    without creating a new one.
    """

    url = "/api/webauthn_mfa/register/verify"
    name = "api:webauthn_mfa:register_verify"
    requires_auth = True

    def __init__(
        self,
        hass: HomeAssistant,
        store: WebAuthnStore,
        rp_id: str,
        expected_origin: str,
    ) -> None:
        """Initialise view."""
        self._hass = hass
        self._store = store
        self._rp_id = rp_id
        self._expected_origin = expected_origin

    async def post(self, request: Request) -> Response:
        """Verify the registration response and persist the credential."""
        user = request["hass_user"]
        user_id: str = user.id

        body = await request.json()
        credential_data: dict[str, Any] | None = body.get("response")
        name: str = body.get("name", "My Passkey")

        if not credential_data:
            return self.json({"error": "response required"}, status_code=400)

        pending = _PENDING_CHALLENGES.pop(f"reg_{user_id}", None)
        if not pending:
            return self.json({"error": "challenge_expired"}, status_code=400)

        # Cryptographic verification.
        try:
            resp = credential_data.get("response", {})
            reg_credential = RegistrationCredential(
                id=credential_data["id"],
                raw_id=base64url_to_bytes(credential_data["rawId"]),
                response=AuthenticatorAttestationResponse(
                    client_data_json=base64url_to_bytes(resp["clientDataJSON"]),
                    attestation_object=base64url_to_bytes(resp["attestationObject"]),
                ),
                type=credential_data.get("type", "public-key"),
            )

            verification = webauthn.verify_registration_response(
                credential=reg_credential,
                expected_rp_id=self._rp_id,
                expected_challenge=pending["challenge"],
                expected_origin=self._expected_origin,
                require_user_verification=True,
            )

        except InvalidRegistrationResponse as err:
            _LOGGER.warning("WebAuthn: registration verification failed: %s", err)
            return self.json(
                {"error": "verification_failed", "message": str(err)}, status_code=400
            )
        except Exception as err:
            _LOGGER.exception("WebAuthn: unexpected error during registration")
            return self.json({"error": str(err)}, status_code=500)

        # Persist the WebAuthn credential.
        credential = {
            "credential_id": verification.credential_id.hex(),
            "public_key": verification.credential_public_key.hex(),
            "sign_count": verification.sign_count,
            "name": name,
            "aaguid": str(verification.aaguid),
        }
        await self._store.async_add_credential(user_id, credential)
        _LOGGER.info(
            "WebAuthn: registered new passkey '%s' for user_id=%s", name, user_id
        )

        # Pre-create and link an HA auth credential to the correct user so
        # that ``async_get_or_create_user`` (called during login) returns the
        # existing user rather than creating a new one.
        await self._link_ha_credential(user_id, user.name)

        return self.json(
            {"success": True, "credential_id": credential["credential_id"]}
        )

    async def _link_ha_credential(self, user_id: str, username: str) -> None:
        """Create and link an HA auth credential for *user_id*.

        No-op if a credential is already linked.
        """
        hass = self._hass

        user = await hass.auth.async_get_user(user_id)
        if user is None:
            _LOGGER.error(
                "WebAuthn: user %s not found, cannot link credential", user_id
            )
            return

        # Check whether a webauthn HA credential already exists for this user.
        for ha_cred in user.credentials:
            if ha_cred.auth_provider_type == PROVIDER_TYPE:
                return

        provider = hass.auth._providers.get((PROVIDER_TYPE, None))  # noqa: SLF001
        if provider is None:
            _LOGGER.error("WebAuthn: provider not found, cannot link credential")
            return

        try:
            ha_cred = provider.async_create_credentials(
                {"username": username, "user_id": user_id}
            )
            await hass.auth.async_link_user(user, ha_cred)
            _LOGGER.info(
                "WebAuthn: HA credential linked to user %s (%s)", user_id, username
            )
        except Exception:
            _LOGGER.exception(
                "WebAuthn: failed to link HA credential for user_id=%s", user_id
            )


class WebAuthnListView(HomeAssistantView):
    """List passkeys registered for the authenticated user.

    ``GET /api/webauthn_mfa/list``
    """

    url = "/api/webauthn_mfa/list"
    name = "api:webauthn_mfa:list"
    requires_auth = True

    def __init__(self, store: WebAuthnStore) -> None:
        """Initialise view."""
        self._store = store

    async def get(self, request: Request) -> Response:
        """Return a list of passkey summaries."""
        user = request["hass_user"]
        return self.json(
            [
                {
                    "credential_id": c["credential_id"][:16] + "...",
                    "name": c.get("name", "Passkey"),
                    "aaguid": c.get("aaguid", ""),
                }
                for c in self._store.get_credentials(user.id)
            ]
        )


class WebAuthnDeleteView(HomeAssistantView):
    """Delete a passkey registered by the authenticated user.

    ``DELETE /api/webauthn_mfa/delete/{credential_id}``
    """

    url = "/api/webauthn_mfa/delete/{credential_id}"
    name = "api:webauthn_mfa:delete"
    requires_auth = True

    def __init__(self, store: WebAuthnStore) -> None:
        """Initialise view."""
        self._store = store

    async def delete(self, request: Request, credential_id: str) -> Response:
        """Remove the passkey identified by *credential_id*."""
        user = request["hass_user"]
        # The panel sends the truncated id ("abc..."); resolve the full hex id.
        prefix = credential_id.replace("...", "")
        credentials = self._store.get_credentials(user.id)
        full_id = next(
            (
                c["credential_id"]
                for c in credentials
                if c["credential_id"].startswith(prefix)
            ),
            None,
        )
        if full_id is None:
            return self.json({"error": "not_found"}, status_code=404)

        await self._store.async_remove_credential(user.id, full_id)
        return self.json({"success": True})
