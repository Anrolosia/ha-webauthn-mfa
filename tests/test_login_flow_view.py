"""Tests for the replaced /auth/login_flow index view."""

from __future__ import annotations

from http import HTTPStatus
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.webauthn_mfa import WebAuthnLoginFlowIndexView
from homeassistant.components.auth.login_flow import LoginFlowIndexView

CLIENT_ID = "https://claude.ai/oauth/mcp-oauth-client-metadata"
CHALLENGE = "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"


def _view():
    view = WebAuthnLoginFlowIndexView(MagicMock(), MagicMock())
    view._flow_mgr.async_init = AsyncMock(return_value={})  # noqa: SLF001
    view._async_flow_result_to_response = AsyncMock(return_value="ok")  # noqa: SLF001
    return view


def _request(body: dict):
    request = MagicMock()
    request.remote = "127.0.0.1"
    request.json = AsyncMock(return_value=body)
    return request


def _body(handler, **extra):
    return {
        "client_id": CLIENT_ID,
        "handler": handler,
        "redirect_uri": "https://claude.ai/api/mcp/auth_callback",
        **extra,
    }


async def test_pkce_params_reach_core_for_other_handlers():
    """PKCE fields must not be rejected before core's own view sees them."""
    view = _view()
    with patch.object(
        LoginFlowIndexView, "post", AsyncMock(return_value="core")
    ) as core_post:
        result = await view.post(
            _request(
                _body(
                    ["homeassistant", None],
                    code_challenge=CHALLENGE,
                    code_challenge_method="S256",
                )
            )
        )
    assert result == "core"
    core_post.assert_awaited_once()


async def test_pkce_challenge_kept_in_webauthn_flow_context():
    """The challenge must be in the flow context so core stores it with the code."""
    view = _view()
    with patch(
        "custom_components.webauthn_mfa.indieauth.verify_client_id", return_value=True
    ):
        result = await view.post(
            _request(
                _body(
                    ["webauthn", None],
                    code_challenge=CHALLENGE,
                    code_challenge_method="S256",
                )
            )
        )
    assert result == "ok"
    context = view._flow_mgr.async_init.await_args.kwargs["context"]  # noqa: SLF001
    assert context["code_challenge"] == CHALLENGE
    assert context["code_challenge_method"] == "S256"


async def test_webauthn_flow_without_pkce_has_no_challenge():
    view = _view()
    with patch(
        "custom_components.webauthn_mfa.indieauth.verify_client_id", return_value=True
    ):
        await view.post(_request(_body(["webauthn", None])))
    context = view._flow_mgr.async_init.await_args.kwargs["context"]  # noqa: SLF001
    assert "code_challenge" not in context


@pytest.mark.parametrize(
    ("challenge", "method"),
    [(CHALLENGE, "plain"), (CHALLENGE, None), ("short", "S256"), (None, "S256")],
)
async def test_invalid_pkce_rejected_on_webauthn_flow(challenge, method):
    view = _view()
    extra = {
        k: v
        for k, v in {
            "code_challenge": challenge,
            "code_challenge_method": method,
        }.items()
        if v is not None
    }
    with patch(
        "custom_components.webauthn_mfa.indieauth.verify_client_id", return_value=True
    ):
        result = await view.post(_request(_body(["webauthn", None], **extra)))
    assert result.status == HTTPStatus.BAD_REQUEST
    assert "message" in json.loads(result.body)
    view._flow_mgr.async_init.assert_not_awaited()  # noqa: SLF001
