"""Tests for WebAuthnAuthProvider and WebAuthnLoginFlow — fully synchronous."""

from __future__ import annotations

import asyncio
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
    """Submitting a valid token completes the flow."""
    token = "valid_token_123"
    fake_hass.data[f"webauthn_mfa_result_{token}"] = {
        "success": True,
        "username": "testuser",
        "user_id": "abc123",
    }

    flow = WebAuthnLoginFlow(provider)
    flow.hass = fake_hass
    flow.flow_id = "test-flow-id"

    with patch.object(
        flow,
        "async_finish",
        new=AsyncMock(return_value={"type": "create_entry"}),
    ) as mock_finish:
        run(flow.async_step_init({"webauthn_token": token}))

    mock_finish.assert_called_once_with({"username": "testuser", "user_id": "abc123"})
    assert f"webauthn_mfa_result_{token}" not in fake_hass.data


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
