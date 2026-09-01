"""Service-to-service workflow for engineering schema and exchange conversion."""
from __future__ import annotations

import os
from typing import Any

import httpx

from .schema_conversion import EngineeringSchemaConverter


class EngineeringWorkflow:
    """Convert an engineering file and register the resulting Turtle by API.

    The ingestion service owns format parsing. The ontology service owns
    artifact registration.  Publication is opt-in and is gated by the ontology
    service's policy and quality APIs before the graph service is contacted.
    """

    def __init__(self, converter: EngineeringSchemaConverter | None = None) -> None:
        self.converter = converter or EngineeringSchemaConverter()
        self.ontology_url = os.getenv("ONTOLOGY_SERVICE_URL", "http://127.0.0.1:8011/api/v1").rstrip("/")
        self.graph_url = os.getenv("GRAPH_SERVICE_URL", "http://127.0.0.1:8013/api/v1").rstrip("/")
        self.timeout = float(os.getenv("SERVICE_REQUEST_TIMEOUT_SECONDS", "30"))

    async def run(
        self, *, filename: str, content: bytes, ontology_name: str = "", prefix: str = "",
        description: str = "", register: bool = True, publish: bool = False,
        enforce_quality: bool = True, policy_exception_ids: list[str] | None = None,
        request_id: str | None = None,
    ) -> dict[str, Any]:
        conversion = self.converter.convert(filename=filename, content=content)
        if publish and not register:
            raise ValueError("Graph publication requires ontology registration")
        if not register:
            return {"status": "converted", "conversion": conversion}
        ontology = conversion["ontology"]
        headers = {"X-Request-ID": request_id} if request_id else {}
        data = {
            "ontology_name": ontology_name or ontology["name"],
            "prefix": prefix or ontology["prefix"],
            "description": description,
            "source": f"engineering-conversion:{conversion['format'].lower()}",
        }
        async with httpx.AsyncClient(timeout=self.timeout, headers=headers) as client:
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
                json={"entities": self._governance_entities(ontology["turtle"]), "deduplicate": True},
            )
            quality_response.raise_for_status()
            quality = quality_response.json()
            if publish and enforce_quality and not quality.get("publish_recommended", False):
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
            published = await client.post(
                f"{self.graph_url}/graph/ontologies/publish",
                data={"ontology_id": registration["ontology_id"], "prefix": data["prefix"]},
                files={"artifact": (f"{PathName.safe_stem(filename)}.ttl", ontology["turtle"].encode("utf-8"), "text/turtle")},
            )
            published.raise_for_status()
            result["status"] = "published"
            result["graph_publication"] = published.json()
            return result

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
