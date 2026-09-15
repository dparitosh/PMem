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
        enforce_quality: bool = True, policy_exception_ids: list[str] | None = None,
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
            policy_response = await client.post(
                f"{self.ontology_url}/ontologies/policies/evaluate",
                json={"decision": {"outcome": "approved", "confidence": 1.0, "decision_maker": "ingestion-service", "reasoning": f"Publish {name}"}, "exception_policy_ids": policy_exception_ids or []},
            )
            policy_response.raise_for_status()
            policy = policy_response.json()
            if publish and not policy.get("compliant", False):
                return {"status": "policy_blocked", "normalization": normalized["provenance"], "records_processed": normalized["records_processed"], "policy": policy, "message": "Publication was blocked by Semantica policy checks."}
            quality_response = await client.post(
                f"{self.ontology_url}/ontologies/quality-gate",
                json={"entities": normalized["entities"], "deduplicate": True},
            )
            quality_response.raise_for_status()
            quality = quality_response.json()
            if publish and enforce_quality and not quality.get("publish_recommended", False):
                return {
                    "status": "quality_blocked", "normalization": normalized["provenance"],
                    "records_processed": normalized["records_processed"], "quality": quality,
                    "message": "Publication was blocked by Semantica quality checks.",
                }
            generated = await client.post(f"{self.ontology_url}/ontologies/generate", json=generation_payload)
            generated.raise_for_status()
            ontology = generated.json()
            result: dict[str, Any] = {
                "status": "generated", "normalization": normalized["provenance"],
                "records_processed": normalized["records_processed"], "policy": policy, "quality": quality, "ontology": ontology,
            }
            if not publish:
                return result
            turtle = ontology.get("artifacts", {}).get("turtle")
            if not turtle:
                raise RuntimeError("Ontology service did not return a Turtle artifact")
            registered = await client.post(
                f"{self.ontology_url}/ontologies/register",
                data={"ontology_name": name, "prefix": prefix, "source": "source-profile-workflow"},
                files={"artifact": (f"{prefix}.ttl", turtle.encode("utf-8"), "text/turtle")},
            )
            registered.raise_for_status()
            result["status"] = "awaiting_approval"
            result["registered_ontology"] = registered.json()
            result["message"] = "Draft registered. Review and approval are required before graph publication."
            return result


workflow = SemanticIngestionWorkflow()
