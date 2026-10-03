"""Gateway and token-based approval identity with loopback-only demo bypass."""
from __future__ import annotations

import base64
import hmac
import json
import os
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException, Request


def require_active_token(token_env: str) -> None:
    """Optional server-controlled expiration, shared or per credential."""
    expiry = os.getenv(token_env + '_EXPIRES_AT') or os.getenv('DEPO_TOKEN_EXPIRES_AT', '')
    if not expiry:
        return
    try:
        deadline = datetime.fromisoformat(expiry.replace('Z', '+00:00'))
        if deadline.tzinfo is None:
            raise ValueError('timezone required')
    except ValueError:
        raise HTTPException(503, 'API key expiration configuration is invalid') from None
    if datetime.now(timezone.utc) >= deadline:
        raise HTTPException(401, 'API key has expired; contact the deployment administrator')


def token_actor(token_env: str, fallback: str) -> str:
    actor = os.getenv(token_env + '_ACTOR', '').strip()
    if not actor and os.getenv('DEPO_REQUIRE_TOKEN_ACTOR', '').lower() == 'true':
        raise HTTPException(503, 'Server-assigned API key actor is not configured')
    return actor or fallback


def _request_api_key(request: Request) -> str:
    authorization = request.headers.get('authorization', '')
    if authorization.lower().startswith('bearer '):
        return authorization[7:]
    return request.headers.get('x-api-key', '')


def _require_trusted_gateway(request: Request) -> None:
    """Make header-based Entra identity safe only behind a known gateway hop.

    APIM validates the JWT; services receive its normalized principal header.
    Accepting that header from an arbitrary network client would permit identity
    spoofing, so production must explicitly allow-list the gateway addresses.
    """
    configured = {
        item.strip() for item in os.getenv("DEPO_TRUSTED_GATEWAY_IPS", "").split(",")
        if item.strip()
    }
    client_host = request.client.host if request.client else ""
    if not configured:
        raise HTTPException(503, "Entra gateway trust is not configured")
    if client_host not in configured:
        raise HTTPException(403, "Request did not originate from a trusted API gateway")


def service_write_identity(request: Request, *, token_env: str, default_actor: str) -> str:
    """Authorize service-to-service write calls using a bearer token.

    Multipart endpoints cannot carry the JSON approval fields used by
    :func:`approval_identity`, so publication boundaries use this explicit
    header contract instead.
    """
    mode = os.getenv("AUTH_MODE", "token").lower()
    if mode == "disabled":
        client_host = request.client.host if request.client else ""
        if os.getenv("DEPO_ALLOW_INSECURE_LOCAL_AUTH", "").lower() != "true" or client_host not in {"127.0.0.1", "::1"}:
            raise HTTPException(403, "Disabled authentication is allowed only for an explicitly enabled loopback-only process")
        return default_actor
    if mode == "entra":
        # Gateway identity is still required in enterprise mode.
        _require_trusted_gateway(request)
        return approval_identity(request, {}, token_env=token_env)
    require_active_token(token_env)
    expected = os.getenv(token_env, "").strip()
    supplied = _request_api_key(request)
    if not expected or not supplied or not hmac.compare_digest(supplied.encode("utf-8"), expected.encode("utf-8")):
        raise HTTPException(403, "A valid service write token is required")
    return token_actor(token_env, default_actor)


def approval_identity(request: Request, payload: dict[str, Any], *, token_env: str) -> str:
    mode = os.getenv("AUTH_MODE", "token").lower()
    if mode == "disabled":
        client_host = request.client.host if request.client else ""
        if os.getenv("DEPO_ALLOW_INSECURE_LOCAL_AUTH", "").lower() != "true" or client_host not in {"127.0.0.1", "::1"}:
            raise HTTPException(403, "Disabled authentication is allowed only for an explicitly enabled loopback-only process")
        return str(payload.get("approved_by") or "local-development")
    if mode != "entra":
        require_active_token(token_env)
        expected = os.getenv(token_env, "")
        supplied = payload.get('approval_token') or _request_api_key(request)
        if expected and payload.get("approved_by") and isinstance(supplied, str) and hmac.compare_digest(supplied.encode("utf-8"), expected.encode("utf-8")):
            return token_actor(token_env, str(payload['approved_by']))
        raise HTTPException(403, "A valid approval token and approver are required")
    _require_trusted_gateway(request)
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
    # Internal service-to-service reads use the same narrowly scoped graph
    # token in every authentication profile. Gateway identity remains required
    # for browser requests in Entra mode, while backend GraphQL aggregation can
    # call the data-pipeline and data-product services without spoofing a user.
    expected = os.getenv("GRAPH_READ_TOKEN", "").strip()
    supplied = _request_api_key(request)
    if expected and supplied and hmac.compare_digest(supplied.encode("utf-8"), expected.encode("utf-8")):
        require_active_token('GRAPH_READ_TOKEN')
        return token_actor('GRAPH_READ_TOKEN', 'service-token-reader')
    if mode == "disabled":
        client_host = request.client.host if request.client else ""
        if os.getenv("DEPO_ALLOW_INSECURE_LOCAL_AUTH", "").lower() != "true" or client_host not in {"127.0.0.1", "::1"}:
            raise HTTPException(403, "Disabled authentication is allowed only for an explicitly enabled loopback-only process")
        return "local-development"
    if mode != "entra":
        if not expected:
            raise HTTPException(503, "GRAPH_READ_TOKEN is not configured in the running service; configure the deployment environment and restart services")
        if not supplied:
            raise HTTPException(403, "Graph read Authorization header is missing; check browser credential selection and gateway forwarding")
        raise HTTPException(403, "Graph read key does not match the running service GRAPH_READ_TOKEN; check the environment file used at startup and restart services after changes")
    _require_trusted_gateway(request)
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
