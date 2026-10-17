"""Tests for the flow-scoped authentication challenge views."""

from __future__ import annotations

import asyncio
from http import HTTPStatus
import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.webauthn_mfa.const import PROVIDER_TYPE
from custom_components.webauthn_mfa.http_views import (
    WebAuthnChallengeView,
    WebAuthnVerifyView,
)
from custom_components.webauthn_mfa.provider import (
    WebAuthnAuthProvider,
    WebAuthnLoginFlow,
)


def run(coro):
    """Run a coroutine synchronously."""
    return asyncio.new_event_loop().run_until_complete(coro)


def _request(hass, body):
    request = MagicMock()
    request.json = AsyncMock(return_value=body)
    request.app = {"hass": hass}
    return request


@pytest.fixture
def hass():
    """Return a minimal hass stand-in with one user owning one passkey."""
    fake = MagicMock()
    user = MagicMock(id="abc123", system_generated=False)
    fake.auth.async_get_users = AsyncMock(return_value=[user])
    return fake


@pytest.fixture
def provider(hass, mock_webauthn_store, sample_credential):
    """Return a provider whose store holds the sample credential."""
    mock_webauthn_store.get_credentials.return_value = [sample_credential]
    config = {"type": PROVIDER_TYPE, "rp_id": "homeassistant.local"}
    return WebAuthnAuthProvider(hass, MagicMock(), mock_webauthn_store, config)


@pytest.fixture
def flow(hass, provider):
    """Return a WebAuthn login flow registered with the provider."""
    flow = WebAuthnLoginFlow(provider)
    flow.hass = hass
    flow.flow_id = "flow-1"
    run(flow.async_step_init(None))
    return flow


def test_challenge_rejects_unknown_flow(hass, provider, mock_webauthn_store):
    """No challenge is created, or stored, for a flow that does not exist."""
    view = WebAuthnChallengeView(provider, mock_webauthn_store, "homeassistant.local")

    response = run(view.post(_request(hass, {"flow_id": "made-up"})))

    assert response.status == HTTPStatus.BAD_REQUEST
    assert json.loads(response.text) == {"error": "unknown_flow"}


def test_challenge_stored_on_flow(hass, provider, flow, mock_webauthn_store):
    """The challenge is kept on the flow it was issued for."""
    view = WebAuthnChallengeView(provider, mock_webauthn_store, "homeassistant.local")

    response = run(view.post(_request(hass, {"flow_id": "flow-1"})))

    assert response.status == HTTPStatus.OK
    assert isinstance(flow.challenge, bytes)
    assert len(flow.challenge) == 32  # noqa: PLR2004


def test_verify_consumes_challenge(hass, provider, flow, mock_webauthn_store):
    """A verification attempt uses up the challenge, even when it fails."""
    flow.challenge = b"x" * 32
    view = WebAuthnVerifyView(
        hass,
        provider,
        mock_webauthn_store,
        "homeassistant.local",
        ["https://homeassistant.local"],
    )
    body = {"flow_id": "flow-1", "response": {"id": "AAAA"}}

    first = run(view.post(_request(hass, body)))
    second = run(view.post(_request(hass, body)))

    assert first.status == HTTPStatus.NOT_FOUND  # credential_not_found
    assert flow.challenge is None
    assert second.status == HTTPStatus.BAD_REQUEST
    assert json.loads(second.text) == {"error": "challenge_expired"}
