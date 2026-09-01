"""Config flow for the WebAuthn / Passkey Authentication integration."""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlparse

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback

from .const import (
    CONF_EXPECTED_ORIGIN,
    CONF_RP_ID,
    CONF_RP_NAME,
    DEFAULT_RP_NAME,
    DOMAIN,
)
from .origins import normalize_origin

_LOGGER = logging.getLogger(__name__)


def _schema(defaults: dict[str, Any] | None = None) -> vol.Schema:
    """Return the setup schema, pre-filled with *defaults* when reconfiguring."""
    defaults = defaults or {}
    return vol.Schema(
        {
            vol.Required(CONF_RP_ID, default=defaults.get(CONF_RP_ID, "")): str,
            vol.Required(
                CONF_RP_NAME, default=defaults.get(CONF_RP_NAME, DEFAULT_RP_NAME)
            ): str,
            vol.Required(
                CONF_EXPECTED_ORIGIN, default=defaults.get(CONF_EXPECTED_ORIGIN, "")
            ): str,
        }
    )


def _clean(user_input: dict[str, Any]) -> dict[str, Any]:
    """Return the normalised settings ready to be stored."""
    return {
        CONF_RP_ID: user_input[CONF_RP_ID].strip().lower(),
        CONF_RP_NAME: user_input[CONF_RP_NAME].strip(),
        CONF_EXPECTED_ORIGIN: normalize_origin(user_input[CONF_EXPECTED_ORIGIN]),
    }


def _validate(user_input: dict[str, Any]) -> dict[str, str]:
    """Return a mapping of field to error key, empty when the input is valid."""
    errors: dict[str, str] = {}

    rp_id = user_input[CONF_RP_ID].strip().lower()
    origin = normalize_origin(user_input[CONF_EXPECTED_ORIGIN])

    if not rp_id or "://" in rp_id or "/" in rp_id or ":" in rp_id:
        errors[CONF_RP_ID] = "invalid_rp_id"

    parsed = urlparse(origin)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        errors[CONF_EXPECTED_ORIGIN] = "invalid_origin"
        return errors

    # WebAuthn requires rp_id to be the origin host itself, or one of its
    # registrable parent domains. Anything else fails the ceremony silently.
    host = parsed.hostname.lower()
    if CONF_RP_ID not in errors and host != rp_id and not host.endswith(f".{rp_id}"):
        errors[CONF_EXPECTED_ORIGIN] = "origin_mismatch"

    return errors


class WebAuthnConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the UI setup of the WebAuthn / Passkey Authentication integration."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial setup step."""
        if self._async_current_entries():
            return self.async_abort(reason="already_configured")

        errors: dict[str, str] = {}

        if user_input is not None:
            errors = _validate(user_input)
            if not errors:
                data = _clean(user_input)
                return self.async_create_entry(title=data[CONF_RP_NAME], data=data)

        return self.async_show_form(
            step_id="user", data_schema=_schema(user_input), errors=errors
        )

    async def async_step_import(self, import_data: dict[str, Any]) -> ConfigFlowResult:
        """Import the legacy configuration.yaml block."""
        if self._async_current_entries():
            return self.async_abort(reason="already_configured")

        errors = _validate(import_data)
        if errors:
            _LOGGER.error(
                "WebAuthn: cannot import configuration.yaml, invalid settings: %s",
                errors,
            )
            return self.async_abort(reason="invalid_yaml")

        data = _clean(import_data)
        _LOGGER.info("WebAuthn: imported YAML configuration into a config entry")
        return self.async_create_entry(title=data[CONF_RP_NAME], data=data)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Return the options flow handler."""
        return WebAuthnOptionsFlow()


class WebAuthnOptionsFlow(OptionsFlow):
    """Allow the domain settings to be changed after setup.

    Changes are written back to the entry data, but the auth provider and the
    HTTP views capture their settings at setup time, so a Home Assistant
    restart is required for the new values to take effect.
    """

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Edit the stored settings."""
        errors: dict[str, str] = {}

        if user_input is not None:
            errors = _validate(user_input)
            if not errors:
                data = _clean(user_input)
                self.hass.config_entries.async_update_entry(
                    self.config_entry, data=data, title=data[CONF_RP_NAME]
                )
                return self.async_create_entry(title="", data={})

        return self.async_show_form(
            step_id="init",
            data_schema=_schema(user_input or dict(self.config_entry.data)),
            errors=errors,
        )
