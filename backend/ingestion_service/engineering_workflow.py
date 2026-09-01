"""Service-to-service workflow for engineering schema and exchange conversion."""
from __future__ import annotations

import os
from typing import Any

import httpx

from .schema_conversion import EngineeringSchemaConverter


class EngineeringWorkflow:
    """Convert an engineering file and register the resulting Turtle by API.

    The ingestion service owns format parsing. The ontology service owns
    artifact registration. This intentionally does not publish to the graph:
    publication remains a separate governed action after review.
    """

    def __init__(self, converter: EngineeringSchemaConverter | None = None) -> None:
        self.converter = converter or EngineeringSchemaConverter()
        self.ontology_url = os.getenv("ONTOLOGY_SERVICE_URL", "http://127.0.0.1:8011/api/v1").rstrip("/")
        self.timeout = float(os.getenv("SERVICE_REQUEST_TIMEOUT_SECONDS", "30"))

    async def run(
        self, *, filename: str, content: bytes, ontology_name: str = "", prefix: str = "",
        description: str = "", register: bool = True, request_id: str | None = None,
    ) -> dict[str, Any]:
        conversion = self.converter.convert(filename=filename, content=content)
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
            response = await client.post(
                f"{self.ontology_url}/ontologies/register",
                data=data,
                files={"artifact": (f"{PathName.safe_stem(filename)}.ttl", ontology["turtle"].encode("utf-8"), "text/turtle")},
            )
            response.raise_for_status()
        return {"status": "registered", "conversion": conversion, "ontology_registration": response.json()}


class PathName:
    """Minimal filename normalization for generated service-to-service artifacts."""

    @staticmethod
    def safe_stem(filename: str) -> str:
        from pathlib import Path
        stem = Path(filename).stem or "ontology"
        return "".join(character if character.isalnum() or character in {"-", "_"} else "_" for character in stem)


workflow = EngineeringWorkflow()
