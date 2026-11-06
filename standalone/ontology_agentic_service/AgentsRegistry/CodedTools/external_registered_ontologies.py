"""Self-contained external API tool: external_registered_ontologies."""

import json
import os
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen
from llama_index.core.tools import FunctionTool


def run_external_registered_ontologies():
    """Read registered ontologies from the configured external HTTP API."""
    if os.getenv("ONTOLOGY_EXTERNAL_API_ENABLED", "false").strip().lower() not in {"1", "true", "yes", "on"}:
        raise RuntimeError("External ontology API is disabled; set ONTOLOGY_EXTERNAL_API_ENABLED=true")
    base_url = os.getenv("ONTOLOGY_EXTERNAL_API_BASE_URL", "http://127.0.0.1:8000").strip()
    parsed = urlparse(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("ONTOLOGY_EXTERNAL_API_BASE_URL must be an HTTP(S) URL without credentials, query, or fragment")
    path = os.getenv("ONTOLOGY_EXTERNAL_REGISTERED_PATH", "/api/v1/ontology/registered").strip()
    if not path.startswith("/"):
        raise ValueError("ONTOLOGY_EXTERNAL_REGISTERED_PATH must start with /")
    try:
        timeout = float(os.getenv("ONTOLOGY_EXTERNAL_API_TIMEOUT_SECONDS", "30"))
    except ValueError as exc:
        raise ValueError("ONTOLOGY_EXTERNAL_API_TIMEOUT_SECONDS must be numeric") from exc
    if timeout <= 0 or timeout > 300:
        raise ValueError("ONTOLOGY_EXTERNAL_API_TIMEOUT_SECONDS must be between 0 and 300")
    headers = {"Accept": "application/json"}
    token = os.getenv("ONTOLOGY_EXTERNAL_API_TOKEN", "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        with urlopen(Request(urljoin(base_url.rstrip("/") + "/", path), headers=headers, method="GET"), timeout=timeout) as response:
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


external_registered_ontologies = FunctionTool.from_defaults(name="external_registered_ontologies", fn=run_external_registered_ontologies)
__all__ = ["external_registered_ontologies"]
