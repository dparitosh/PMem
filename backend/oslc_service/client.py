"""Configured outbound OSLC client; never accepts arbitrary target hosts."""
from __future__ import annotations

import os
import re
from typing import Any
from urllib.parse import urlsplit

import httpx


class OSLCClient:
    def __init__(self) -> None:
        self.base_url = os.getenv("OSLC_REMOTE_BASE_URL", "").strip().rstrip("/")
        self.token = os.getenv("OSLC_REMOTE_TOKEN", "").strip()
        self.timeout = float(os.getenv("OSLC_CLIENT_TIMEOUT_SECONDS", "20"))

    def _request(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        if not self.base_url:
            raise RuntimeError("OSLC_REMOTE_BASE_URL is not configured")
        if os.getenv('OSLC_REMOTE_ENABLED', 'false').lower() != 'true':
            raise RuntimeError('Remote OSLC is disabled')
        from backend.depo_platform.service_urls import service_url
        self.base_url = service_url('OSLC_REMOTE_BASE_URL', self.base_url)
        parsed = urlsplit(self.base_url)
        if (parsed.scheme not in {"http", "https"} or not parsed.hostname or
                parsed.username or parsed.password or parsed.query or parsed.fragment):
            raise RuntimeError("OSLC_REMOTE_BASE_URL must be an HTTP(S) base URL without embedded credentials")
        allowed = {'oslc.where', 'oslc.select', 'oslc.orderBy', 'oslc.searchTerms', 'oslc.paging', 'oslc.pageSize', 'oslc.pageNum'}
        params = {key: value for key, value in (params or {}).items() if key in allowed}
        headers = {"Accept": "application/json"}
        if self.token: headers["Authorization"] = f"Bearer {self.token}"
        from backend.depo_platform.network import gateway_subscription_headers
        endpoint = f"{self.base_url}/{path.lstrip('/')}"
        headers.update(gateway_subscription_headers(endpoint))
        limit = int(os.getenv('OSLC_MAX_RESPONSE_BYTES', str(8 * 1024 * 1024)))
        if limit <= 0: raise RuntimeError('OSLC_MAX_RESPONSE_BYTES must be positive')
        with httpx.Client(timeout=self.timeout, follow_redirects=False, trust_env=False) as client:
            with client.stream('GET', endpoint, params=params, headers=headers) as response:
                response.raise_for_status()
                chunks, total = [], 0
                for chunk in response.iter_bytes():
                    total += len(chunk)
                    if total > limit: raise ValueError('Remote OSLC response exceeds OSLC_MAX_RESPONSE_BYTES')
                    chunks.append(chunk)
        import json
        result = json.loads(b''.join(chunks))
        if not isinstance(result, dict): raise ValueError('Remote OSLC response must be an object')
        return result

    def discover(self) -> dict[str, Any]:
        return self._request("oslc/catalog")

    def query(self, resource_type: str, parameters: dict[str, Any]) -> dict[str, Any]:
        if not re.fullmatch(r"(?:[A-Za-z][A-Za-z0-9_-]*|ontology:[A-Za-z0-9_][A-Za-z0-9_.-]{0,199})", resource_type):
            raise ValueError("resource_type must start with a letter and contain only letters, digits, '_' or '-'")
        return self._request(f"oslc/query/{resource_type}", parameters)


client = OSLCClient()
