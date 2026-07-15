"""External ontology-service API tools for IIF agents.

IIF owns these lightweight FunctionTool wrappers. RDFLib and Owlready2 execute
behind the standalone HTTP API; they are not imported into the IIF process.
"""

from __future__ import annotations

import json
import os
from typing import Any, Literal, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from llama_index.core.tools import FunctionTool


def _enabled(variable: str, default: bool = False) -> bool:
    value = os.getenv(variable)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _ontology_api_url(base_url: Optional[str] = None) -> str:
    configured = (os.getenv("ONTOLOGY_API_BASE_URL") or "http://127.0.0.1:8012").rstrip("/")
    if base_url and _enabled("ONTOLOGY_API_SECURITY_ENABLED") and not _enabled("ONTOLOGY_API_ALLOW_BASE_URL_OVERRIDE"):
        if base_url.rstrip("/") != configured:
            raise ValueError("base_url override is disabled while ontology API security is enabled")
    return (base_url or configured).rstrip("/")


def _post_json(endpoint: str, payload: dict[str, Any], base_url: Optional[str], timeout_seconds: float) -> dict[str, Any]:
    url = _ontology_api_url(base_url) + endpoint
    headers = {"Accept": "application/json", "Content-Type": "application/json"}
    token = os.getenv("ONTOLOGY_API_TOKEN", "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers=headers,
    )
    try:
        with urlopen(request, timeout=max(1.0, min(float(timeout_seconds), 300.0))) as response:
            body = response.read(5_000_001)
            if len(body) > 5_000_000:
                raise RuntimeError("Ontology API response exceeded the 5 MB safety limit")
            return json.loads(body.decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read(100_000).decode("utf-8", errors="replace")
        raise RuntimeError(f"Ontology API returned HTTP {exc.code} for {endpoint}: {detail}") from exc
    except URLError as exc:
        raise RuntimeError(f"Ontology API is unavailable at {_ontology_api_url(base_url)}: {exc.reason}") from exc


def ontology_inspect_api(
    path: str,
    base_url: Optional[str] = None,
    timeout_seconds: float = 120.0,
) -> dict[str, Any]:
    """Call the standalone RDFLib inspection agent API."""
    response = _post_json(
        "/api/v1/agents/ontology_intake_agent/run",
        {"inputs": {"ontology_path": path}},
        base_url,
        timeout_seconds,
    )
    return response.get("result", response)


def ontology_review_api(
    path: str,
    profile: Literal["schema", "schema_and_instances"] = "schema",
    base_url: Optional[str] = None,
    timeout_seconds: float = 120.0,
) -> dict[str, Any]:
    """Call the standalone RDFLib qualification-review agent API."""
    response = _post_json(
        "/api/v1/agents/ontology_review_agent/run",
        {"inputs": {"ontology_path": path, "review_profile": profile}},
        base_url,
        timeout_seconds,
    )
    return response.get("result", response)


def ontology_alignment_api(
    path: str,
    instance_metadata_json: str = "{}",
    base_url: Optional[str] = None,
    timeout_seconds: float = 120.0,
) -> dict[str, Any]:
    """Call the standalone instance-alignment planning agent API."""
    metadata = json.loads(instance_metadata_json or "{}")
    if not isinstance(metadata, dict):
        raise ValueError("instance_metadata_json must decode to an object")
    response = _post_json(
        "/api/v1/agents/ontology_alignment_agent/run",
        {"inputs": {"ontology_path": path, "instance_metadata": metadata}},
        base_url,
        timeout_seconds,
    )
    return response.get("result", response)


def ontology_export_api(
    path: str,
    output_dir: str,
    export_format: Literal["ttl", "rdf", "nt", "jsonld"] = "ttl",
    base_url: Optional[str] = None,
    timeout_seconds: float = 120.0,
) -> dict[str, Any]:
    """Call the standalone RDFLib ontology export agent API."""
    response = _post_json(
        "/api/v1/agents/ontology_export_agent/run",
        {"inputs": {"ontology_path": path, "output_dir": output_dir, "export_formats": [export_format]}},
        base_url,
        timeout_seconds,
    )
    return response.get("result", response)


def owlready2_reasoning_api(
    path: str,
    run_reasoner: bool = False,
    reasoner: Literal["hermit", "pellet"] = "hermit",
    infer_property_values: bool = False,
    base_url: Optional[str] = None,
    timeout_seconds: float = 300.0,
) -> dict[str, Any]:
    """Call the standalone isolated-World Owlready2 API."""
    return _post_json(
        "/api/v1/ontology/owlready2",
        {
            "path": path,
            "run_reasoner": run_reasoner,
            "reasoner": reasoner,
            "infer_property_values": infer_property_values,
        },
        base_url,
        timeout_seconds,
    )


ontology_inspect_api_tool = FunctionTool.from_defaults(name="ontology_inspect_api", fn=ontology_inspect_api)
ontology_review_api_tool = FunctionTool.from_defaults(name="ontology_review_api", fn=ontology_review_api)
ontology_alignment_api_tool = FunctionTool.from_defaults(name="ontology_alignment_api", fn=ontology_alignment_api)
ontology_export_api_tool = FunctionTool.from_defaults(name="ontology_export_api", fn=ontology_export_api)
owlready2_reasoning_api_tool = FunctionTool.from_defaults(name="owlready2_reasoning_api", fn=owlready2_reasoning_api)


__all__ = [
    "ontology_inspect_api_tool",
    "ontology_review_api_tool",
    "ontology_alignment_api_tool",
    "ontology_export_api_tool",
    "owlready2_reasoning_api_tool",
]
