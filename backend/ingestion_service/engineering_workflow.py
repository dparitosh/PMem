"""Service-to-service workflow for engineering schema and exchange conversion."""
from __future__ import annotations

import os
import hashlib
import json
import asyncio
from starlette.concurrency import run_in_threadpool
from backend.depo_platform.service_urls import service_url
from typing import Any

import httpx

from backend.depo_platform.network import service_bearer_headers
from .schema_conversion import EngineeringSchemaConverter


class EngineeringWorkflow:
    """Convert an engineering file and register the resulting Turtle by API.

    The ingestion service owns format parsing. The ontology service owns
    artifact registration.  Publication is opt-in and is gated by the ontology
    service's policy and quality APIs before the graph service is contacted.
    """

    def __init__(self, converter: EngineeringSchemaConverter | None = None) -> None:
        self.converter = converter or EngineeringSchemaConverter()
        self.ontology_url = service_url("ONTOLOGY_SERVICE_URL", "http://127.0.0.1:8011/api/v1")
        self.graph_url = service_url("GRAPH_SERVICE_URL", "http://127.0.0.1:8013/api/v1")
        from backend.depo_platform.network import bounded_timeout_seconds
        self.timeout = bounded_timeout_seconds('SERVICE_REQUEST_TIMEOUT_SECONDS', default=30, maximum=300)

    async def run(
        self, **kwargs,
    ) -> dict[str, Any]:
        from backend.depo_platform.network import bounded_timeout_seconds
        deadline = bounded_timeout_seconds('ENGINEERING_WORKFLOW_TIMEOUT_SECONDS', default=300, maximum=3600)
        async with asyncio.timeout(deadline):
            return await self._run(**kwargs)

    async def _run(
        self, *, filename: str, content: bytes, ontology_name: str = "", prefix: str = "",
        description: str = "", register: bool = True, publish: bool = False,
        enforce_quality: bool = True, policy_exception_ids: list[str] | None = None,
        request_id: str | None = None,
    ) -> dict[str, Any]:
        from pathlib import Path
        if Path(filename).suffix.lower() in {'.ttl', '.rdf', '.owl'}:
            from .rdf_conversion import convert_rdf
            conversion = await run_in_threadpool(convert_rdf, filename=filename, content=content)
        else:
            conversion = await run_in_threadpool(self.converter.convert, filename=filename, content=content)
        if publish and not register:
            raise ValueError("Graph publication requires ontology registration")
        if not register:
            return {"status": "converted", "conversion": conversion}
        ontology = conversion["ontology"]
        headers = service_bearer_headers('ONTOLOGY_APPROVAL_TOKEN', service_name='the ontology workflow API', endpoint=self.ontology_url)
        if request_id:
            headers['X-Request-ID'] = request_id
        data = {
            "ontology_name": ontology_name or ontology["name"],
            "prefix": prefix or ontology["prefix"],
            "description": description,
            "extra_metadata": json.dumps({
                'engineering_artifacts': conversion.get('artifacts') or {},
                'data_product_draft': conversion.get('data_product_draft') or {},
                'source_filename': filename,
            }),
            "source": "engineering-workflow:" + hashlib.sha256(
                json.dumps([filename, ontology_name, prefix, description], ensure_ascii=False).encode("utf-8") + b"\0" + content
            ).hexdigest(),
        }
        async with httpx.AsyncClient(timeout=self.timeout, headers=headers, trust_env=False) as client:
            policy_response = await client.post(
                f"{self.ontology_url}/ontologies/policies/evaluate",
                json={"decision": {"outcome": "approved", "confidence": 1.0,
                      "decision_maker": "engineering-ingestion",
                      "reasoning": f"Publish {filename}"},
                      "exception_policy_ids": policy_exception_ids or []},
            )
            policy_response.raise_for_status()
            policy = policy_response.json()
            if publish and not policy.get("compliant", False):
                return {"status": "policy_blocked", "conversion": conversion, "policy": policy,
                        "message": "Publication was blocked by policy checks."}
            quality_response = await client.post(
                f"{self.ontology_url}/ontologies/quality-gate",
                json={"entities": await run_in_threadpool(self._governance_entities, ontology["turtle"]), "deduplicate": True},
            )
            quality_response.raise_for_status()
            quality = quality_response.json()
            if publish and not quality.get("publish_recommended", False):
                return {"status": "quality_blocked", "conversion": conversion, "policy": policy,
                        "quality": quality, "message": "Publication was blocked by quality checks."}
            response = await client.post(
                f"{self.ontology_url}/ontologies/register",
                data=data,
                files={"artifact": (f"{PathName.safe_stem(filename)}.ttl", ontology["turtle"].encode("utf-8"), "text/turtle")},
            )
            response.raise_for_status()
            registration = response.json()
            result: dict[str, Any] = {"status": "registered", "conversion": conversion,
                                      "policy": policy, "quality": quality,
                                      "ontology_registration": registration}
            if not publish:
                return result
            # Re-read authoritative state: registration may have reused an artifact
            # whose lifecycle was changed after the original request.
            current = await client.get(f"{self.ontology_url}/ontologies/{registration['ontology_id']}")
            current.raise_for_status()
            self._require_publishable(current.json())
            published = await client.post(
                f"{self.graph_url}/graph/ontologies/publish",
                data={"ontology_id": registration["ontology_id"], "prefix": data["prefix"],
                      "publication_id": data["source"].split(":", 1)[1]},
                files={"artifact": (f"{PathName.safe_stem(filename)}.ttl", ontology["turtle"].encode("utf-8"), "text/turtle")},
                headers=service_bearer_headers("GRAPH_PUBLICATION_TOKEN", service_name="the graph publication API", endpoint=self.graph_url),
            )
            published.raise_for_status()
            receipt = published.json()
            if (not isinstance(receipt, dict)
                    or receipt.get("status") != "success"
                    or receipt.get("ontology_id") != registration["ontology_id"]
                    or receipt.get("publication_id") != data["source"].split(":", 1)[1]):
                raise RuntimeError("Graph publication outcome is unverified: receipt identity did not match. Reconcile publication before retrying.")
            result["status"] = "published"
            result["graph_publication"] = receipt
            return result

    @staticmethod
    def _require_publishable(metadata: dict[str, Any]) -> None:
        if (metadata.get("lifecycle_status") not in {"draft", "in_review", "approved"}
                or metadata.get("status") == "superseded"):
            raise ValueError("Ontology publication is blocked by its current lifecycle state")

    @staticmethod
    def _governance_entities(turtle: str) -> list[dict[str, str]]:
        """Supply stable resource identities to Semantica's quality gate."""
        from rdflib import Graph
        graph = Graph()
        graph.parse(data=turtle, format="turtle")
        return [{"id": str(subject), "name": str(subject), "type": "resource"}
                for subject in sorted(set(graph.subjects()), key=str) if str(subject).startswith(("http://", "https://"))]


class PathName:
    """Minimal filename normalization for generated service-to-service artifacts."""

    @staticmethod
    def safe_stem(filename: str) -> str:
        from pathlib import Path
        stem = Path(filename).stem or "ontology"
        return "".join(character if character.isalnum() or character in {"-", "_"} else "_" for character in stem)


workflow = EngineeringWorkflow()
