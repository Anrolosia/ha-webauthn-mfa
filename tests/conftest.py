"""Shared fixtures for WebAuthn MFA tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.webauthn_mfa.store import WebAuthnStore


@pytest.fixture
def mock_webauthn_store():
    """Return a mocked WebAuthnStore."""
    store = MagicMock(spec=WebAuthnStore)
    store.async_load = AsyncMock()
    store.async_save = AsyncMock()
    store.async_add_credential = AsyncMock()
    store.async_remove_credential = AsyncMock(return_value=True)
    store.async_update_sign_count = AsyncMock()
    store.get_credentials = MagicMock(return_value=[])
    store.has_credentials = MagicMock(return_value=False)
    store.find_user_by_credential_id = MagicMock(return_value=None)
    return store


@pytest.fixture
def sample_credential():
    """Return a sample stored WebAuthn credential."""
    return {
        "credential_id": "deadbeef" * 8,
        "public_key": "cafebabe" * 8,
        "sign_count": 0,
        "name": "Test Passkey",
        "aaguid": "00000000-0000-0000-0000-000000000000",
    }
