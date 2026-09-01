"""Explicit HTTP orchestration for profile-driven semantic ingestion."""
from __future__ import annotations

import os
from typing import Any

import httpx


class SemanticIngestionWorkflow:
    """Connect ingestion to independently deployable ontology and graph services."""

    def __init__(self) -> None:
        self.ontology_url = os.getenv("ONTOLOGY_SERVICE_URL", "http://127.0.0.1:8011/api/v1").rstrip("/")
        self.graph_url = os.getenv("GRAPH_SERVICE_URL", "http://127.0.0.1:8013/api/v1").rstrip("/")
        self.timeout = float(os.getenv("SERVICE_REQUEST_TIMEOUT_SECONDS", "30"))

    async def run(
        self, *, normalized: dict[str, Any], name: str, prefix: str, base_uri: str, publish: bool,
        request_id: str | None = None,
    ) -> dict[str, Any]:
        if not normalized.get("entities"):
            raise ValueError("The source profile produced no entities; revise records_path or mapping")
        headers = {"X-Request-ID": request_id} if request_id else {}
        generation_payload = {
            "name": name, "base_uri": base_uri,
            "data": {"entities": normalized["entities"], "relationships": normalized["relationships"]},
        }
        async with httpx.AsyncClient(timeout=self.timeout, headers=headers) as client:
            generated = await client.post(f"{self.ontology_url}/ontologies/generate", json=generation_payload)
            generated.raise_for_status()
            ontology = generated.json()
            result: dict[str, Any] = {
                "status": "generated", "normalization": normalized["provenance"],
                "records_processed": normalized["records_processed"], "ontology": ontology,
            }
            if not publish:
                return result
            turtle = ontology.get("artifacts", {}).get("turtle")
            if not turtle:
                raise RuntimeError("Ontology service did not return a Turtle artifact")
            version_id = str(ontology.get("version_id") or "")
            published = await client.post(
                f"{self.graph_url}/graph/ontologies/publish",
                data={"ontology_id": version_id, "prefix": prefix},
                files={"artifact": (f"{prefix}.ttl", turtle.encode("utf-8"), "text/turtle")},
            )
            published.raise_for_status()
            result["status"] = "published"
            result["graph_publication"] = published.json()
            return result


workflow = SemanticIngestionWorkflow()
