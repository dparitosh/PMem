from __future__ import annotations

import base64
import json

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from backend.depo_platform.authorization import approval_identity


def _request(host: str = "10.0.0.5") -> Request:
    payload = base64.b64encode(json.dumps({"userDetails": "steward@example.test", "userRoles": ["DataProduct.Approver"]}).encode()).decode()
    return Request({"type": "http", "method": "POST", "path": "/", "headers": [(b"x-ms-client-principal", payload.encode())], "client": (host, 443)})


def test_entra_identity_requires_trusted_gateway(monkeypatch):
    monkeypatch.setenv("AUTH_MODE", "entra")
    monkeypatch.delenv("DEPO_TRUSTED_GATEWAY_IPS", raising=False)
    with pytest.raises(HTTPException, match="trust is not configured"):
        approval_identity(_request(), {}, token_env="UNUSED")


def test_entra_identity_allows_configured_gateway(monkeypatch):
    monkeypatch.setenv("AUTH_MODE", "entra")
    monkeypatch.setenv("DEPO_TRUSTED_GATEWAY_IPS", "10.0.0.5")
    assert approval_identity(_request(), {}, token_env="UNUSED") == "steward@example.test"
