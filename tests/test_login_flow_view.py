"""Tests for the replaced /auth/login_flow index view."""

from __future__ import annotations

from http import HTTPStatus
from inspect import signature
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.webauthn_mfa import WebAuthnLoginFlowIndexView
from homeassistant.components.auth import indieauth
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
    request.scheme = "https"
    request.host = "ha.example.com:8123"
    request.json = AsyncMock(return_value=body)
    return request


def _body(handler, **extra):
    return {
        "client_id": CLIENT_ID,
        "handler": handler,
        "redirect_uri": "https://claude.ai/api/mcp/auth_callback",
        **extra,
    }


@pytest.mark.parametrize("valid_client_id", [True, False])
async def test_webauthn_passes_request_origin_to_client_id_validator(valid_client_id):
    """Core 2026.11 requires the actual request origin to validate client IDs."""

    def verify_client_id(client_id, *, request_scheme, request_netloc):
        return valid_client_id

    view = _view()
    request = _request(_body(["webauthn", None]))
    with (
        patch(
            "custom_components.webauthn_mfa._CLIENT_ID_REQUIRES_REQUEST_ORIGIN", True
        ),
        patch(
            "custom_components.webauthn_mfa.indieauth.verify_client_id",
            autospec=verify_client_id,
            return_value=valid_client_id,
        ) as verify,
    ):
        result = await view.post(request)

    verify.assert_called_once_with(
        CLIENT_ID, request_scheme="https", request_netloc="ha.example.com:8123"
    )
    if valid_client_id:
        assert result == "ok"
        view._flow_mgr.async_init.assert_awaited_once()  # noqa: SLF001
    else:
        assert result.status == HTTPStatus.BAD_REQUEST
        assert json.loads(result.body)["message"] == "Invalid client id"
        view._flow_mgr.async_init.assert_not_awaited()  # noqa: SLF001


async def test_webauthn_supports_legacy_client_id_validator():
    """Older supported cores accept only the client ID argument."""

    def verify_client_id(client_id):
        return True

    view = _view()
    with (
        patch(
            "custom_components.webauthn_mfa._CLIENT_ID_REQUIRES_REQUEST_ORIGIN", False
        ),
        patch(
            "custom_components.webauthn_mfa.indieauth.verify_client_id",
            autospec=verify_client_id,
            return_value=True,
        ) as verify,
    ):
        result = await view.post(_request(_body(["webauthn", None])))

    assert result == "ok"
    verify.assert_called_once_with(CLIENT_ID)


@pytest.mark.parametrize(
    ("client_id", "expected_valid"),
    [
        (CLIENT_ID, True),
        ("not-a-url", False),
        ("https://user:pass@example.com/", False),
    ],
)
async def test_webauthn_uses_core_client_id_validation(client_id, expected_valid):
    """Use the real validator so permissive mocks cannot hide API changes."""
    view = _view()
    result = await view.post(_request(_body(["webauthn", None], client_id=client_id)))

    if expected_valid:
        assert result == "ok"
        view._flow_mgr.async_init.assert_awaited_once()  # noqa: SLF001
    else:
        assert result.status == HTTPStatus.BAD_REQUEST
        view._flow_mgr.async_init.assert_not_awaited()  # noqa: SLF001


@pytest.mark.skipif(
    "request_scheme" not in signature(indieauth.verify_client_id).parameters,
    reason="Request-origin validation requires Core 2026.11+",
)
@pytest.mark.parametrize(
    ("scheme", "host", "expected_valid"),
    [
        ("https", "8.8.8.8:8123", True),
        ("http", "8.8.8.8:8123", False),
        ("https", "8.8.4.4:8123", False),
        ("https", "8.8.8.8:443", False),
    ],
)
async def test_webauthn_public_ip_client_id_matches_request(
    scheme, host, expected_valid
):
    """Public IP client IDs are allowed only when they match the request origin."""
    view = _view()
    request = _request(_body(["webauthn", None], client_id="https://8.8.8.8:8123/"))
    request.scheme = scheme
    request.host = host

    result = await view.post(request)

    if expected_valid:
        assert result == "ok"
        view._flow_mgr.async_init.assert_awaited_once()  # noqa: SLF001
    else:
        assert result.status == HTTPStatus.BAD_REQUEST
        view._flow_mgr.async_init.assert_not_awaited()  # noqa: SLF001


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
