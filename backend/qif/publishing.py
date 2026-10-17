"""OpenAPI publishing port for QIF workflow."""
from __future__ import annotations

import os
from backend.depo_platform.service_urls import service_url
from pathlib import Path
from typing import Any, Protocol

import httpx

from backend.depo_platform.network import service_bearer_headers


class QifPublisher(Protocol):
    def register(self, *, artifact: Path, ontology_name: str, prefix: str, description: str) -> dict[str, Any]: ...
    def sync_graph(self, *, ontology_id: str, artifact: Path) -> dict[str, Any]: ...
    def verify_graph(self, *, ontology_id: str, artifact: Path) -> dict[str, Any]: ...


class ServicePublisher:
    """OpenAPI client for the new dedicated ontology and graph services."""

    def __init__(self) -> None:
        self.ontology_url = service_url("ONTOLOGY_SERVICE_URL", "http://127.0.0.1:8011/api/v1")
        self.graph_url = service_url("GRAPH_SERVICE_URL", "http://127.0.0.1:8013/api/v1")
        from backend.depo_platform.network import service_request_timeout_seconds
        self.timeout = service_request_timeout_seconds()

    def register(self, *, artifact: Path, ontology_name: str, prefix: str, description: str) -> dict[str, Any]:
        with artifact.open("rb") as content, httpx.Client(timeout=self.timeout) as client:
            response = client.post(
                f"{self.ontology_url}/ontologies/register",
                data={"ontology_name": ontology_name, "prefix": prefix, "description": description, "source": "qif"},
                files={"artifact": (artifact.name, content, "text/turtle")},
                headers=service_bearer_headers('ONTOLOGY_APPROVAL_TOKEN', service_name='the ontology registration API', endpoint=self.ontology_url),
            )
        response.raise_for_status()
        payload = response.json()
        return {"status": "success", "ontology_id": payload["ontology_id"], "storage_path": payload["artifact_path"], "metadata": payload}

    def sync_graph(self, *, ontology_id: str, artifact: Path) -> dict[str, Any]:
        from backend.core.sync_async import call_async
        from backend.depo_platform.graph_publication_transport import publish_graph
        return call_async(lambda: publish_graph(self.graph_url, content=artifact.read_bytes(),
                          ontology_id=ontology_id, prefix=ontology_id.split('_', 1)[0]))

    def verify_graph(self, *, ontology_id: str, artifact: Path) -> dict[str, Any]:
        import hashlib
        from backend.core.sync_async import call_async
        from backend.depo_platform.graph_publication_transport import verify_publication
        identity = hashlib.sha256(artifact.read_bytes()).hexdigest()
        return call_async(lambda: verify_publication(self.graph_url, ontology_id, identity))


def get_publisher() -> QifPublisher:
    return ServicePublisher()
