"""Gateway and token-based approval identity with loopback-only demo bypass."""
from __future__ import annotations

import base64
import hmac
import json
import os
from typing import Any

from fastapi import HTTPException, Request


def approval_identity(request: Request, payload: dict[str, Any], *, token_env: str) -> str:
    mode = os.getenv("AUTH_MODE", "token").lower()
    if mode == "disabled":
        client_host = request.client.host if request.client else ""
        if os.getenv("DEPO_ALLOW_INSECURE_LOCAL_AUTH", "").lower() != "true" or client_host not in {"127.0.0.1", "::1"}:
            raise HTTPException(403, "Disabled authentication is allowed only for an explicitly enabled loopback-only process")
        return str(payload.get("approved_by") or "local-development")
    if mode != "entra":
        expected = os.getenv(token_env, "")
        if expected and payload.get("approved_by") and payload.get("approval_token") == expected:
            return str(payload["approved_by"])
        raise HTTPException(403, "A valid approval token and approver are required")
    encoded = request.headers.get("x-ms-client-principal", "")
    principal: dict[str, Any] = {}
    if encoded:
        try:
            principal = json.loads(base64.b64decode(encoded).decode("utf-8"))
        except Exception as exc:
            raise HTTPException(401, "Gateway-verified Entra principal is invalid") from exc
    identity = str(principal.get("userDetails") or principal.get("name") or request.headers.get("x-depo-principal-id") or "")
    roles = {str(role) for role in principal.get("userRoles", [])}
    roles.update(role.strip() for role in request.headers.get("x-depo-roles", "").split(",") if role.strip())
    required = os.getenv("REQUIRED_APPROVER_ROLE", "DataProduct.Approver")
    if not identity or required not in roles:
        raise HTTPException(403, "Authenticated principal lacks the required approver role")
    return identity


def graph_read_identity(request: Request) -> str:
    """Authorize graph reads for local, bootstrap-token, or gateway-Entra profiles."""
    mode = os.getenv("AUTH_MODE", "token").lower()
    if mode == "disabled":
        client_host = request.client.host if request.client else ""
        if os.getenv("DEPO_ALLOW_INSECURE_LOCAL_AUTH", "").lower() != "true" or client_host not in {"127.0.0.1", "::1"}:
            raise HTTPException(403, "Disabled authentication is allowed only for an explicitly enabled loopback-only process")
        return "local-development"
    if mode != "entra":
        expected = os.getenv("GRAPH_READ_TOKEN", "")
        authorization = request.headers.get("authorization", "")
        supplied = authorization[7:] if authorization.lower().startswith("bearer ") else ""
        if expected and hmac.compare_digest(supplied, expected):
            return request.headers.get("x-depo-principal-id", "token-reader")
        raise HTTPException(403, "A valid graph read token is required")
    encoded = request.headers.get("x-ms-client-principal", "")
    try:
        principal = json.loads(base64.b64decode(encoded).decode("utf-8")) if encoded else {}
    except Exception as exc:
        raise HTTPException(401, "Gateway-verified Entra principal is invalid") from exc
    identity = str(principal.get("userDetails") or principal.get("name") or request.headers.get("x-depo-principal-id") or "")
    roles = {str(role) for role in principal.get("userRoles", [])}
    roles.update(role.strip() for role in request.headers.get("x-depo-roles", "").split(",") if role.strip())
    required = os.getenv("GRAPH_READER_ROLE", "Graph.Reader")
    if not identity or required not in roles:
        raise HTTPException(403, "Authenticated principal lacks the required graph reader role")
    return identity
