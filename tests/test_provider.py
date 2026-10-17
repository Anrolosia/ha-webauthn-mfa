"""Tests for WebAuthnAuthProvider and WebAuthnLoginFlow — fully synchronous."""

from __future__ import annotations

import asyncio
import gc
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.webauthn_mfa.const import PROVIDER_TYPE
from custom_components.webauthn_mfa.provider import (
    WebAuthnAuthProvider,
    WebAuthnLoginFlow,
)


def run(coro):
    """Run a coroutine synchronously, bypassing pytest-asyncio entirely."""
    return asyncio.new_event_loop().run_until_complete(coro)


class _FakeHass:
    """Minimal HomeAssistant stand-in — no sockets, no event loop overhead."""

    def __init__(self) -> None:
        self.data: dict = {}
        self.auth = MagicMock()


@pytest.fixture
def fake_hass():
    """Return a lightweight fake hass object."""
    return _FakeHass()


@pytest.fixture
def provider(fake_hass, mock_webauthn_store):
    """Return a WebAuthnAuthProvider instance."""
    auth_store = MagicMock()
    config = {"type": PROVIDER_TYPE, "rp_id": "homeassistant.local"}
    return WebAuthnAuthProvider(fake_hass, auth_store, mock_webauthn_store, config)


def test_provider_type(provider):
    """Provider type must be 'webauthn'."""
    assert provider.type == PROVIDER_TYPE


def test_provider_id_is_none(provider):
    """Provider id must be None (single instance)."""
    assert provider.id is None


def test_provider_name_default(provider):
    """Default provider name is shown on the login page."""
    assert provider.name == "Passkey / Security Key"


def test_provider_support_mfa_false(provider):
    """WebAuthn is a primary authenticator, not an MFA module."""
    assert provider.support_mfa is False


def test_login_flow_returns_form_on_init(fake_hass, provider):
    """async_step_init with no input returns the webauthn_token form."""
    flow = WebAuthnLoginFlow(provider)
    flow.hass = fake_hass
    flow.flow_id = "test-flow-id"

    result = run(flow.async_step_init(None))

    assert result["type"] == "form"
    assert result["step_id"] == "init"
    assert "webauthn_token" in result["data_schema"].schema


def test_login_flow_invalid_token(fake_hass, provider):
    """Submitting an unknown token returns an error form."""
    flow = WebAuthnLoginFlow(provider)
    flow.hass = fake_hass
    flow.flow_id = "test-flow-id"

    result = run(flow.async_step_init({"webauthn_token": "bad_token"}))

    assert result["type"] == "form"
    assert result["errors"] == {"base": "invalid_auth"}


def test_login_flow_valid_token(fake_hass, provider):
    """Submitting the token issued by a verified assertion completes the flow."""
    flow = WebAuthnLoginFlow(provider)
    flow.hass = fake_hass
    flow.flow_id = "test-flow-id"
    token = flow.async_set_verified("abc123", "testuser")

    with patch.object(
        flow,
        "async_finish",
        new=AsyncMock(return_value={"type": "create_entry"}),
    ) as mock_finish:
        run(flow.async_step_init({"webauthn_token": token}))

    mock_finish.assert_called_once_with({"username": "testuser", "user_id": "abc123"})

    # The token is single use.
    result = run(flow.async_step_init({"webauthn_token": token}))
    assert result["errors"] == {"base": "invalid_auth"}


def test_login_flow_redeems_token_from_another_flow(fake_hass, provider):
    """The frontend redeems the token from a fresh flow after redirecting back."""
    verifying_flow = WebAuthnLoginFlow(provider)
    verifying_flow.hass = fake_hass
    verifying_flow.flow_id = "flow-a"
    replay_flow = WebAuthnLoginFlow(provider)
    replay_flow.hass = fake_hass
    replay_flow.flow_id = "flow-b"

    token = verifying_flow.async_set_verified("abc123", "testuser")
    with patch.object(
        replay_flow,
        "async_finish",
        new=AsyncMock(return_value={"type": "create_entry"}),
    ) as mock_finish:
        run(replay_flow.async_step_init({"webauthn_token": token}))

    mock_finish.assert_called_once_with({"username": "testuser", "user_id": "abc123"})
    assert verifying_flow.async_pop_verified_user() is None


def test_verified_token_dropped_with_its_flow(fake_hass, provider):
    """A token can't outlive the flow holding its verified result."""
    flow = WebAuthnLoginFlow(provider)
    flow.hass = fake_hass
    flow.flow_id = "flow-a"
    token = flow.async_set_verified("abc123", "testuser")

    del flow
    gc.collect()

    assert provider.async_redeem_verified_token(token) is None


def test_login_flow_registered_with_provider(fake_hass, provider):
    """Flows are reachable by flow_id while alive and dropped with the flow."""
    flow = WebAuthnLoginFlow(provider)
    flow.hass = fake_hass
    flow.flow_id = "test-flow-id"
    run(flow.async_step_init(None))

    assert provider.async_get_login_flow("test-flow-id") is flow

    del flow
    gc.collect()

    assert provider.async_get_login_flow("test-flow-id") is None


def test_login_flow_empty_token(fake_hass, provider):
    """Submitting an empty token returns an error form."""
    flow = WebAuthnLoginFlow(provider)
    flow.hass = fake_hass
    flow.flow_id = "test-flow-id"

    result = run(flow.async_step_init({"webauthn_token": "  "}))

    assert result["type"] == "form"
    assert result["errors"] == {"base": "invalid_auth"}


def test_get_or_create_credentials_existing(provider):
    """Returns an existing credential matched by user_id."""
    mock_cred = MagicMock()
    mock_cred.data = {"user_id": "abc123", "username": "testuser"}

    with patch.object(
        provider, "async_credentials", new=AsyncMock(return_value=[mock_cred])
    ):
        result = run(
            provider.async_get_or_create_credentials(
                {"user_id": "abc123", "username": "testuser"}
            )
        )

    assert result is mock_cred


def test_get_or_create_credentials_new(provider):
    """Creates a new credential when no match is found."""
    with (
        patch.object(provider, "async_credentials", new=AsyncMock(return_value=[])),
        patch.object(
            provider, "async_create_credentials", return_value=MagicMock()
        ) as mock_create,
    ):
        run(
            provider.async_get_or_create_credentials(
                {"user_id": "new_user", "username": "newuser"}
            )
        )

    mock_create.assert_called_once_with({"username": "newuser", "user_id": "new_user"})
