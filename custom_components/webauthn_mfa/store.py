"""Persistent storage for WebAuthn credentials."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import STORAGE_KEY, STORAGE_VERSION

_LOGGER = logging.getLogger(__name__)


class WebAuthnStore:
    """Manage persistence of WebAuthn credentials indexed by HA user ID.

    Each user's credentials are stored as a list of dicts with the following fields:
    - ``credential_id``: hex-encoded credential ID
    - ``public_key``: hex-encoded COSE public key
    - ``sign_count``: replay-attack counter
    - ``name``: human-readable label chosen by the user
    - ``aaguid``: authenticator AAGUID (informational)
    """

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialise the store (does not load data yet)."""
        self._store: Store = Store(hass, STORAGE_VERSION, STORAGE_KEY, private=True)
        self._data: dict[str, list[dict[str, Any]]] = {}

    async def async_load(self) -> None:
        """Load persisted data from HA storage."""
        raw = await self._store.async_load()
        self._data = raw.get("credentials", {}) if raw else {}

    async def async_save(self) -> None:
        """Persist the current state to HA storage."""
        await self._store.async_save({"credentials": self._data})

    # ── Read ──────────────────────────────────────────────────────────────────

    def get_credentials(self, user_id: str) -> list[dict[str, Any]]:
        """Return all stored credentials for *user_id* (empty list if none)."""
        return self._data.get(user_id, [])

    def has_credentials(self, user_id: str) -> bool:
        """Return ``True`` if *user_id* has at least one registered passkey."""
        return bool(self.get_credentials(user_id))

    def get_credential_by_id(
        self, user_id: str, credential_id_hex: str
    ) -> dict[str, Any] | None:
        """Return the credential matching *credential_id_hex*, or ``None``."""
        for cred in self.get_credentials(user_id):
            if cred.get("credential_id") == credential_id_hex:
                return cred
        return None

    def find_user_by_credential_id(
        self, credential_id_hex: str
    ) -> tuple[str, dict[str, Any]] | None:
        """Search all users for a credential matching *credential_id_hex*.

        Returns ``(user_id, credential)`` or ``None`` if not found.
        """
        for user_id, creds in self._data.items():
            for cred in creds:
                if cred.get("credential_id") == credential_id_hex:
                    return user_id, cred
        return None

    # ── Write ─────────────────────────────────────────────────────────────────

    async def async_add_credential(
        self, user_id: str, credential: dict[str, Any]
    ) -> None:
        """Add a new passkey credential for *user_id* and persist immediately."""
        self._data.setdefault(user_id, []).append(credential)
        await self.async_save()

    async def async_remove_credential(
        self, user_id: str, credential_id_hex: str
    ) -> bool:
        """Remove a single credential by its hex ID.

        Returns ``True`` if the credential was found and removed, ``False`` otherwise.
        """
        creds = self._data.get(user_id, [])
        new_creds = [c for c in creds if c.get("credential_id") != credential_id_hex]
        if len(new_creds) == len(creds):
            return False
        self._data[user_id] = new_creds
        await self.async_save()
        return True

    async def async_update_sign_count(
        self, user_id: str, credential_id_bytes: bytes, new_sign_count: int
    ) -> None:
        """Update the sign counter for a credential (replay-attack protection)."""
        credential_id_hex = credential_id_bytes.hex()
        for cred in self._data.get(user_id, []):
            if cred.get("credential_id") == credential_id_hex:
                cred["sign_count"] = new_sign_count
                await self.async_save()
                return
