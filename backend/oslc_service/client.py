"""Configured outbound OSLC client; never accepts arbitrary target hosts."""
from __future__ import annotations

import os
import re
from typing import Any

import httpx


class OSLCClient:
    def __init__(self) -> None:
        self.base_url = os.getenv("OSLC_REMOTE_BASE_URL", "").strip().rstrip("/")
        self.token = os.getenv("OSLC_REMOTE_TOKEN", "").strip()
        self.timeout = float(os.getenv("OSLC_CLIENT_TIMEOUT_SECONDS", "20"))

    def _request(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        if not self.base_url:
            raise RuntimeError("OSLC_REMOTE_BASE_URL is not configured")
        headers = {"Accept": "application/json"}
        if self.token: headers["Authorization"] = f"Bearer {self.token}"
        response = httpx.get(f"{self.base_url}/{path.lstrip('/')}", params=params, headers=headers, timeout=self.timeout)
        response.raise_for_status()
        return response.json()

    def discover(self) -> dict[str, Any]:
        return self._request("oslc/catalog")

    def query(self, resource_type: str, parameters: dict[str, Any]) -> dict[str, Any]:
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]*", resource_type):
            raise ValueError("resource_type must start with a letter and contain only letters, digits, '_' or '-'")
        return self._request(f"oslc/query/{resource_type}", parameters)


client = OSLCClient()
