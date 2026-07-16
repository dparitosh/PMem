"""Self-contained external API tool: external_context_graph_search."""

import json
import os
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen
from llama_index.core.tools import FunctionTool


def run_external_context_graph_search(search: str, ontology_prefix: str = ""):
    """Search the configured external context-graph HTTP API."""
    search = search.strip()
    if not search:
        raise ValueError("search must not be empty")
    if os.getenv("ONTOLOGY_EXTERNAL_API_ENABLED", "false").strip().lower() not in {"1", "true", "yes", "on"}:
        raise RuntimeError("External ontology API is disabled; set ONTOLOGY_EXTERNAL_API_ENABLED=true")
    base_url = os.getenv("ONTOLOGY_EXTERNAL_API_BASE_URL", "http://127.0.0.1:8000").strip()
    parsed = urlparse(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("ONTOLOGY_EXTERNAL_API_BASE_URL must be an HTTP(S) URL without credentials, query, or fragment")
    path = os.getenv("ONTOLOGY_EXTERNAL_CONTEXT_SEARCH_PATH", "/graphfilter").strip()
    if not path.startswith("/"):
        raise ValueError("ONTOLOGY_EXTERNAL_CONTEXT_SEARCH_PATH must start with /")
    try:
        timeout = float(os.getenv("ONTOLOGY_EXTERNAL_API_TIMEOUT_SECONDS", "30"))
    except ValueError as exc:
        raise ValueError("ONTOLOGY_EXTERNAL_API_TIMEOUT_SECONDS must be numeric") from exc
    if timeout <= 0 or timeout > 300:
        raise ValueError("ONTOLOGY_EXTERNAL_API_TIMEOUT_SECONDS must be between 0 and 300")
    headers = {"Accept": "application/json", "Content-Type": "application/json"}
    token = os.getenv("ONTOLOGY_EXTERNAL_API_TOKEN", "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    body = {"search": search}
    if ontology_prefix.strip():
        body["ontology_prefix"] = ontology_prefix.strip()
    try:
        request = Request(urljoin(base_url.rstrip("/") + "/", path), data=json.dumps(body).encode("utf-8"), headers=headers, method="POST")
        with urlopen(request, timeout=timeout) as response:
            raw = response.read(5 * 1024 * 1024 + 1)
    except HTTPError as exc:
        raise RuntimeError(f"External ontology API returned HTTP {exc.code}") from exc
    except URLError as exc:
        raise RuntimeError(f"External ontology API is unavailable: {exc.reason}") from exc
    if len(raw) > 5 * 1024 * 1024:
        raise RuntimeError("External ontology API response exceeded 5 MiB")
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("External ontology API returned invalid JSON") from exc


external_context_graph_search = FunctionTool.from_defaults(name="external_context_graph_search", fn=run_external_context_graph_search)
__all__ = ["external_context_graph_search"]
