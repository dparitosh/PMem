"""Small, dependency-free networking configuration helpers."""
from __future__ import annotations

import os


def gateway_subscription_headers(endpoint: str) -> dict[str, str]:
    """Attach APIM credentials only to the explicitly configured gateway root."""
    from urllib.parse import urlsplit, unquote
    base = os.getenv('DEPO_API_GATEWAY_URL', '').rstrip('/')
    key = os.getenv('DEPO_APIM_SUBSCRIPTION_KEY', '').strip()
    if not base or not key:
        return {}
    try:
        target, configured = urlsplit(endpoint), urlsplit(base)
        def origin(url):
            return url.scheme.lower(), (url.hostname or '').lower(), url.port or (443 if url.scheme.lower() == 'https' else 80)
        if target.scheme not in {'http', 'https'} or target.username or target.password or origin(target) != origin(configured):
            return {}
    except ValueError:
        return {}
    # HTTP clients/proxies normalize dot segments; reject traversal before
    # attaching credentials, including encoded separators and dot segments.
    decoded = unquote(target.path)
    if '\\' in decoded or any(part in {'.', '..'} for part in decoded.split('/')):
        return {}
    if decoded != configured.path and not decoded.startswith(configured.path.rstrip('/') + '/'):
        return {}
    return {'Ocp-Apim-Subscription-Key': key}


def bounded_timeout_seconds(name: str, *, default: float, minimum: float = 1.0, maximum: float = 3600.0) -> float:
    """Read an operator timeout without allowing a malformed value to break a request."""
    try:
        value = float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, value))


def service_bearer_headers(token_env: str, *, service_name: str, endpoint: str = '') -> dict[str, str]:
    """Return the required credential for a private service-to-service call."""
    token = os.getenv(token_env, "").strip()
    from .authorization import require_active_token
    require_active_token(token_env)
    if not token:
        raise RuntimeError(f"{token_env} is required to call {service_name}")
    return {**gateway_subscription_headers(endpoint), "Authorization": f"Bearer {token}"}
