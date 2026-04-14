"""Tests for WebAuthnStore — fully synchronous, no pytest-asyncio dependency."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.webauthn_mfa.store import WebAuthnStore


def run(coro):
    """Run a coroutine synchronously, bypassing pytest-asyncio entirely."""
    return asyncio.new_event_loop().run_until_complete(coro)


class _FakeHass:
    """Minimal HomeAssistant stand-in — no sockets, no event loop overhead."""


@pytest.fixture
def store():
    """WebAuthnStore backed by a fully mocked HA Store."""
    with patch("custom_components.webauthn_mfa.store.Store") as mock_cls:
        mock_backend = MagicMock()
        mock_backend.async_load = AsyncMock(return_value=None)
        mock_backend.async_save = AsyncMock()
        mock_cls.return_value = mock_backend
        s = WebAuthnStore(_FakeHass())
        s._mock_backend = mock_backend  # noqa: SLF001
        return s


def test_async_load_empty(store):
    """Loading from an empty store initialises to an empty dict."""
    run(store.async_load())
    assert store._data == {}  # noqa: SLF001


def test_async_load_existing(store):
    """Loading from an existing store restores credentials."""
    store._mock_backend.async_load = AsyncMock(  # noqa: SLF001
        return_value={"credentials": {"user1": [{"credential_id": "abc"}]}}
    )
    run(store.async_load())
    assert store._data == {"user1": [{"credential_id": "abc"}]}  # noqa: SLF001


def test_add_and_get_credential(store, sample_credential):
    """Adding a credential makes it retrievable."""
    run(store.async_load())
    run(store.async_add_credential("user1", sample_credential))
    assert store.get_credentials("user1") == [sample_credential]


def test_get_credentials_unknown_user(store):
    """Getting credentials for an unknown user returns an empty list."""
    run(store.async_load())
    assert store.get_credentials("nobody") == []


def test_has_credentials_true(store, sample_credential):
    """has_credentials returns True when credentials exist."""
    run(store.async_load())
    run(store.async_add_credential("user1", sample_credential))
    assert store.has_credentials("user1") is True


def test_has_credentials_false(store):
    """has_credentials returns False for a user with no credentials."""
    run(store.async_load())
    assert store.has_credentials("user1") is False


def test_find_user_by_credential_id(store, sample_credential):
    """find_user_by_credential_id returns the correct user and credential."""
    run(store.async_load())
    run(store.async_add_credential("user1", sample_credential))
    result = store.find_user_by_credential_id(sample_credential["credential_id"])
    assert result is not None
    user_id, cred = result
    assert user_id == "user1"
    assert cred == sample_credential


def test_find_user_by_credential_id_not_found(store):
    """find_user_by_credential_id returns None for an unknown credential."""
    run(store.async_load())
    assert store.find_user_by_credential_id("nonexistent") is None


def test_remove_credential(store, sample_credential):
    """Removing a credential returns True and the credential is gone."""
    run(store.async_load())
    run(store.async_add_credential("user1", sample_credential))
    cred_id = sample_credential["credential_id"]
    removed = run(store.async_remove_credential("user1", cred_id))
    assert removed is True
    assert store.get_credentials("user1") == []


def test_remove_credential_not_found(store):
    """Removing a nonexistent credential returns False."""
    run(store.async_load())
    removed = run(store.async_remove_credential("user1", "nonexistent"))
    assert removed is False


def test_update_sign_count(store, sample_credential):
    """Updating the sign count persists the new value."""
    new_count = 42
    run(store.async_load())
    run(store.async_add_credential("user1", sample_credential))
    cred_bytes = bytes.fromhex(sample_credential["credential_id"])
    run(store.async_update_sign_count("user1", cred_bytes, new_count))
    assert store.get_credentials("user1")[0]["sign_count"] == new_count
