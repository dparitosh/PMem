from __future__ import annotations

from fastapi import HTTPException
from starlette.requests import Request

from backend.platform.authorization import approval_identity, graph_read_identity


def _request(host: str) -> Request:
    return Request({"type": "http", "method": "POST", "path": "/", "headers": [], "client": (host, 1)})


def test_disabled_authentication_is_limited_to_explicit_loopback(monkeypatch) -> None:
    monkeypatch.setenv("AUTH_MODE", "disabled")
    monkeypatch.setenv("DEPO_ALLOW_INSECURE_LOCAL_AUTH", "true")

    assert approval_identity(_request("127.0.0.1"), {}, token_env="TOKEN") == "local-development"

    try:
        approval_identity(_request("10.0.0.2"), {}, token_env="TOKEN")
    except HTTPException as error:
        assert error.status_code == 403
    else:
        raise AssertionError("Non-loopback disabled authentication must be rejected")


def test_token_mode_requires_the_configured_approval_token(monkeypatch) -> None:
    monkeypatch.setenv("AUTH_MODE", "token")
    monkeypatch.setenv("DATA_PRODUCT_APPROVAL_TOKEN", "test-token")

    assert approval_identity(
        _request("10.0.0.2"),
        {"approved_by": "bootstrap-user", "approval_token": "test-token"},
        token_env="DATA_PRODUCT_APPROVAL_TOKEN",
    ) == "bootstrap-user"


def test_graph_read_token_uses_bearer_header(monkeypatch) -> None:
    monkeypatch.setenv("AUTH_MODE", "token")
    monkeypatch.setenv("GRAPH_READ_TOKEN", "read-token")
    request = Request({"type": "http", "method": "POST", "path": "/", "headers": [(b"authorization", b"Bearer read-token")], "client": ("10.0.0.2", 1)})
    assert graph_read_identity(request) == "token-reader"
