"""Constants for the WebAuthn / Passkey Authentication integration."""

from __future__ import annotations

DOMAIN = "webauthn_mfa"

# Auth provider
PROVIDER_TYPE = "webauthn"

# Panel
PANEL_TITLE = "Passkeys"
PANEL_ICON = "mdi:key"
PANEL_URL = "webauthn-mfa"
PANEL_WEBCOMPONENT = "webauthn-panel"

# Storage
STORAGE_VERSION = 1
STORAGE_KEY = "auth_module.webauthn"

# Configuration keys
CONF_RP_ID = "rp_id"
CONF_RP_NAME = "rp_name"
CONF_EXPECTED_ORIGIN = "expected_origin"

# Defaults
DEFAULT_RP_NAME = "Home Assistant"

# Token expiry (seconds) — short-lived token passed from authenticate page to login flow
WEBAUTHN_TOKEN_EXPIRY = 300

# Pending challenges dict key prefix
CHALLENGE_KEY_PREFIX = "reg_"
