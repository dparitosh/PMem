"""Gateway-verified approval identity.

In production APIM/Entra mode, the gateway injects the signed-principal header
after validating the bearer token.  Development mode deliberately retains the
token mechanism so local service tests do not need an identity provider.
"""
from __future__ import annotations

import base64
import json
import os
from typing import Any

from fastapi import HTTPException, Request


def approval_identity(request: Request, payload: dict[str, Any], *, token_env: str) -> str:
    if os.getenv("AUTH_MODE", "development").lower() != "entra":
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
