"""Explicit HTTP orchestration for profile-driven semantic ingestion."""
from __future__ import annotations
from backend.depo_platform.ontology_maintenance import ontology_writer

import os
import asyncio
import hashlib
import json
from backend.depo_platform.service_urls import service_url
from typing import Any

import httpx
from backend.depo_platform.network import service_bearer_headers


class SemanticIngestionWorkflow:
    """Connect ingestion to an independently deployable ontology service."""

    def __init__(self) -> None:
        self.ontology_url = service_url("ONTOLOGY_SERVICE_URL", "http://127.0.0.1:8011/api/v1")
        from backend.depo_platform.network import service_request_timeout_seconds
        self.timeout = service_request_timeout_seconds()

    @ontology_writer
    async def run(
        self, *, normalized: dict[str, Any], name: str, prefix: str, base_uri: str, publish: bool,
        enforce_quality: bool = True, policy_exception_ids: list[str] | None = None,
        request_id: str | None = None,
    ) -> dict[str, Any]:
        if not normalized.get("entities"):
            raise ValueError("The source profile produced no entities; revise records_path or mapping")
        headers = service_bearer_headers('ONTOLOGY_APPROVAL_TOKEN', service_name='the ontology workflow API', endpoint=self.ontology_url)
        if request_id:
            headers['X-Request-ID'] = request_id
        generation_payload = {
            "name": name, "base_uri": base_uri,
            "data": {"entities": normalized["entities"], "relationships": normalized["relationships"]},
        }
        from backend.depo_platform.network import engineering_workflow_timeout_seconds
        async with asyncio.timeout(engineering_workflow_timeout_seconds()), httpx.AsyncClient(timeout=self.timeout, headers=headers, trust_env=False) as client:
            from backend.depo_platform.decision_policy import decision, policy_blocks
            from backend.depo_platform.bridge_contract import digest
            policy_response = await client.post(
                f"{self.ontology_url}/ontologies/policies/evaluate",
                json={"decision": decision(operation="ontology_import", decision_maker="ingestion-service", source_digest=digest(normalized), reasoning="Normalized import evidence; lifecycle approval remains required."), "exception_policy_ids": policy_exception_ids or []},
            )
            policy_response.raise_for_status()
            policy = policy_response.json()
            if publish and policy_blocks(policy):
                return {"status": "policy_blocked", "normalization": normalized["provenance"], "records_processed": normalized["records_processed"], "policy": policy, "message": "Publication was blocked by Semantica policy checks."}
            quality_response = await client.post(
                f"{self.ontology_url}/ontologies/quality-gate",
                json={"entities": normalized["entities"], "deduplicate": True},
            )
            quality_response.raise_for_status()
            quality = quality_response.json()
            if publish and not quality.get("publish_recommended", False):
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
                data={"ontology_name": name, "prefix": prefix, "source": "source-profile-workflow:" + hashlib.sha256(json.dumps(
                    [normalized, name, prefix, base_uri], sort_keys=True, ensure_ascii=False, separators=(",", ":")
                ).encode("utf-8")).hexdigest()},
                files={"artifact": (f"{prefix}.ttl", turtle.encode("utf-8"), "text/turtle")},
            )
            registered.raise_for_status()
            # Registration produces a draft. Graph publication is a separate
            # approval operation and is never implied by an import request.
            result["status"] = "awaiting_approval"
            result["registered_ontology"] = registered.json()
            result["message"] = "Draft registered. Review and approval are required before graph publication."
            return result


workflow = SemanticIngestionWorkflow()
