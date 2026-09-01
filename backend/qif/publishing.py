"""Publishing ports for QIF workflow.

QIF no longer imports the legacy ontology manager directly.  Existing installs
can use the compatibility adapter during migration; new deployments set
`QIF_PUBLISH_MODE=services` and target the OpenAPI ontology/graph services.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Protocol

import httpx


class QifPublisher(Protocol):
    def register(self, *, artifact: Path, ontology_name: str, prefix: str, description: str) -> dict[str, Any]: ...
    def sync_graph(self, *, ontology_id: str, artifact: Path) -> dict[str, Any]: ...


class LegacyPublisher:
    """Temporary compatibility adapter; the only location that touches legacy code."""

    def register(self, *, artifact: Path, ontology_name: str, prefix: str, description: str) -> dict[str, Any]:
        try:
            from ..Services.ontology_upload_manager import OntologyUploadManager
        except ImportError:  # pragma: no cover - script mode
            from Services.ontology_upload_manager import OntologyUploadManager
        return OntologyUploadManager.save_ontology_file(
            file_content=artifact.read_bytes(), filename=artifact.name, ontology_name=ontology_name,
            prefix=prefix, file_type="ontology", generation_type="as_is", description=description,
            schema_type="schema",
        )

    def sync_graph(self, *, ontology_id: str, artifact: Path) -> dict[str, Any]:
        try:
            from ..Services.ontology_upload_manager import OntologyUploadManager
            from ..core.graph import graph
        except ImportError:  # pragma: no cover - script mode
            from Services.ontology_upload_manager import OntologyUploadManager
            from core.graph import graph
        return OntologyUploadManager.push_to_neo4j(ontology_id, graph)


class ServicePublisher:
    """OpenAPI client for the new dedicated ontology and graph services."""

    def __init__(self) -> None:
        self.ontology_url = os.getenv("ONTOLOGY_SERVICE_URL", "http://127.0.0.1:8011/api/v1")
        self.graph_url = os.getenv("GRAPH_SERVICE_URL", "http://127.0.0.1:8013/api/v1")
        self.timeout = float(os.getenv("SERVICE_REQUEST_TIMEOUT_SECONDS", "30"))

    def register(self, *, artifact: Path, ontology_name: str, prefix: str, description: str) -> dict[str, Any]:
        with artifact.open("rb") as content, httpx.Client(timeout=self.timeout) as client:
            response = client.post(
                f"{self.ontology_url}/ontologies/register",
                data={"ontology_name": ontology_name, "prefix": prefix, "description": description, "source": "qif"},
                files={"artifact": (artifact.name, content, "text/turtle")},
            )
        response.raise_for_status()
        payload = response.json()
        return {"status": "success", "ontology_id": payload["ontology_id"], "storage_path": payload["artifact_path"], "metadata": payload}

    def sync_graph(self, *, ontology_id: str, artifact: Path) -> dict[str, Any]:
        with artifact.open("rb") as content, httpx.Client(timeout=self.timeout) as client:
            response = client.post(
                f"{self.graph_url}/graph/ontologies/publish",
                data={"ontology_id": ontology_id, "prefix": ontology_id.split("_", 1)[0]},
                files={"artifact": (artifact.name, content, "text/turtle")},
            )
        response.raise_for_status()
        return response.json()


def get_publisher() -> QifPublisher:
    mode = os.getenv("QIF_PUBLISH_MODE", "legacy").strip().lower()
    if mode == "services":
        return ServicePublisher()
    return LegacyPublisher()
