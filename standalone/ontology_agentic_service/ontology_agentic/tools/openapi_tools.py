"""Deterministic OpenAPI document inspection for orchestration tooling."""

from __future__ import annotations

from typing import Any


def inspect_openapi_document(document: dict[str, Any], source_name: str = "") -> dict[str, Any]:
    """Normalize an OpenAPI JSON document into a compact low-code catalog."""
    if not isinstance(document, dict):
        raise ValueError("OpenAPI document must be a JSON object")

    version = str(document.get("openapi") or document.get("swagger") or "").strip()
    if not version:
        raise ValueError("OpenAPI document must contain 'openapi' or 'swagger'")
    if "openapi" in document and not version.startswith("3"):
        raise ValueError(f"Unsupported OpenAPI version: {version}")
    if "swagger" in document and not version.startswith("2"):
        raise ValueError(f"Unsupported Swagger version: {version}")

    methods = {"get", "post", "put", "patch", "delete", "head", "options", "trace"}
    operations: list[dict[str, Any]] = []
    for path, path_item in (document.get("paths") or {}).items():
        if not isinstance(path_item, dict):
            continue
        for method, operation in path_item.items():
            method_lower = str(method).lower()
            if method_lower not in methods or not isinstance(operation, dict):
                continue
            operations.append({
                "path": str(path),
                "method": method_lower.upper(),
                "operation_id": operation.get("operationId") or "",
                "summary": operation.get("summary") or operation.get("description") or "",
                "tags": operation.get("tags") or [],
                "parameters": len(operation.get("parameters") or []),
                "responses": sorted(str(code) for code in (operation.get("responses") or {}).keys()),
            })

    components = document.get("components") or {}
    schemas = components.get("schemas") or {}
    if not schemas and isinstance(document.get("definitions"), dict):
        schemas = document["definitions"]

    return {
        "status": "imported",
        "source_name": source_name,
        "version": version,
        "title": ((document.get("info") or {}).get("title") or source_name or "OpenAPI document"),
        "description": ((document.get("info") or {}).get("description") or ""),
        "servers": [item.get("url", "") for item in (document.get("servers") or []) if isinstance(item, dict)],
        "base_url": document.get("basePath", "") if "swagger" in document else "",
        "operations": operations,
        "schemas": [
            {"name": str(name), "type": value.get("type", "object") if isinstance(value, dict) else "object"}
            for name, value in schemas.items()
        ],
        "summary": {
            "operations": len(operations),
            "paths": len({item["path"] for item in operations}),
            "schemas": len(schemas),
        },
    }
