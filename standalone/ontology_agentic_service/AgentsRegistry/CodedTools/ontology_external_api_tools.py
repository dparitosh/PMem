"""External HTTP API tools kept separate from local ontology libraries."""

from __future__ import annotations

import json
import os
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

from llama_index.core.tools import FunctionTool


_MAX_RESPONSE_BYTES = 5 * 1024 * 1024


def _env(name: str, default: str) -> str:
    return os.getenv(name, default).strip()


def _enabled() -> bool:
    return _env("ONTOLOGY_EXTERNAL_API_ENABLED", "false").lower() in {"1", "true", "yes", "on"}


def _endpoint(path_env: str, default_path: str) -> str:
    if not _enabled():
        raise RuntimeError("External ontology API is disabled; set ONTOLOGY_EXTERNAL_API_ENABLED=true to use it")
    base_url = _env("ONTOLOGY_EXTERNAL_API_BASE_URL", "http://127.0.0.1:8000")
    parsed = urlparse(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("ONTOLOGY_EXTERNAL_API_BASE_URL must be an HTTP(S) URL")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("ONTOLOGY_EXTERNAL_API_BASE_URL must not contain credentials, query, or fragment")
    path = _env(path_env, default_path)
    if not path.startswith("/"):
        raise ValueError(f"{path_env} must start with /")
    return urljoin(base_url.rstrip("/") + "/", path)


def _request(method: str, url: str, body: dict[str, Any] | None = None) -> Any:
    headers = {"Accept": "application/json"}
    token = _env("ONTOLOGY_EXTERNAL_API_TOKEN", "")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body).encode("utf-8")
    try:
        timeout = float(_env("ONTOLOGY_EXTERNAL_API_TIMEOUT_SECONDS", "30"))
    except ValueError as exc:
        raise ValueError("ONTOLOGY_EXTERNAL_API_TIMEOUT_SECONDS must be numeric") from exc
    if timeout <= 0 or timeout > 300:
        raise ValueError("ONTOLOGY_EXTERNAL_API_TIMEOUT_SECONDS must be between 0 and 300")
    try:
        with urlopen(Request(url, data=data, headers=headers, method=method), timeout=timeout) as response:
            raw = response.read(_MAX_RESPONSE_BYTES + 1)
    except HTTPError as exc:
        detail = exc.read(2048).decode("utf-8", errors="replace")
        raise RuntimeError(f"External ontology API returned HTTP {exc.code}: {detail}") from exc
    except URLError as exc:
        raise RuntimeError(f"External ontology API is unavailable: {exc.reason}") from exc
    if len(raw) > _MAX_RESPONSE_BYTES:
        raise RuntimeError("External ontology API response exceeded 5 MiB")
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("External ontology API returned invalid JSON") from exc


def external_registered_ontologies() -> Any:
    """Read registered ontologies from the configured external ontology API."""
    return _request("GET", _endpoint("ONTOLOGY_EXTERNAL_REGISTERED_PATH", "/api/v1/ontology/registered"))


def external_context_graph_search(search: str, ontology_prefix: str = "") -> Any:
    """Search an external context-graph API without exposing arbitrary target URLs."""
    search = search.strip()
    if not search:
        raise ValueError("search must not be empty")
    body = {"search": search}
    if ontology_prefix.strip():
        body["ontology_prefix"] = ontology_prefix.strip()
    return _request("POST", _endpoint("ONTOLOGY_EXTERNAL_CONTEXT_SEARCH_PATH", "/graphfilter"), body)


external_registered_ontologies_tool = FunctionTool.from_defaults(
    name="external_registered_ontologies", fn=external_registered_ontologies
)
external_context_graph_search_tool = FunctionTool.from_defaults(
    name="external_context_graph_search", fn=external_context_graph_search
)


__all__ = ["external_registered_ontologies_tool", "external_context_graph_search_tool"]
