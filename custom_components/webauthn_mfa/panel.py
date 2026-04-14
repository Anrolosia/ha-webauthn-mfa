"""Register the WebAuthn sidebar panel."""

from __future__ import annotations

import logging
import os
from pathlib import Path

from homeassistant.components import frontend
from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant

from .const import DOMAIN, PANEL_ICON, PANEL_TITLE, PANEL_URL, PANEL_WEBCOMPONENT

_LOGGER = logging.getLogger(__name__)

_STATIC_URL = f"/{DOMAIN}/webauthn-panel.js"


async def async_setup(hass: HomeAssistant) -> None:
    """Register the static panel JS and the sidebar entry."""
    panel_path = Path(__file__).parent / "www" / "webauthn-panel.js"

    if not panel_path.is_file():
        _LOGGER.error("WebAuthn panel JS not found at %s", panel_path)
        return

    # Use the file's mtime as a cache-buster so browsers always load the
    # latest version after a component update.
    mtime = await hass.async_add_executor_job(lambda: int(os.path.getmtime(panel_path)))

    await hass.http.async_register_static_paths(
        [StaticPathConfig(_STATIC_URL, str(panel_path), cache_headers=False)]
    )

    if PANEL_URL in hass.data.get("frontend_panels", {}):
        return

    frontend.async_register_built_in_panel(
        hass,
        component_name="custom",
        sidebar_title=PANEL_TITLE,
        sidebar_icon=PANEL_ICON,
        frontend_url_path=PANEL_URL,
        config={
            "_panel_custom": {
                "name": PANEL_WEBCOMPONENT,
                "js_url": f"{_STATIC_URL}?v={mtime}",
                "embed_iframe": False,
                "trust_external": False,
            }
        },
    )
