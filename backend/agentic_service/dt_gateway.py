"""Bounded gateway transport for the inspected DT current-plan API."""
import os
from urllib.parse import urlsplit

import httpx


async def execute_current_plan(query: str, email: str, correlation_id: str) -> object:
    base = os.getenv("DT_AGENT_GATEWAY_URL", "").strip().rstrip("/")
    url = urlsplit(base)
    if (url.scheme != "https" or not url.hostname or url.username or url.password
            or url.query or url.fragment):
        raise ValueError("DT_AGENT_GATEWAY_URL must be a configured HTTPS gateway base URL")
    token = os.getenv("DT_AGENT_GATEWAY_TOKEN", "").strip()
    if not token:
        raise ValueError("DT_AGENT_GATEWAY_TOKEN is required")
    if not query.strip() or len(query) > 100000 or not email.strip() or len(email) > 320:
        raise ValueError("A bounded query and DT session email are required")
    async with httpx.AsyncClient(timeout=60, follow_redirects=False, trust_env=False) as client:
        response = await client.post(
            base + "/workflow/run/",
            headers={"Authorization": "Bearer " + token, "X-Correlation-ID": correlation_id},
            json={"query": query, "email": email},
        )
        response.raise_for_status()
        result = response.json()
        if isinstance(result, dict) and any(key in result for key in ("error", "errors")):
            raise ValueError("DT returned an application error")
        return result
