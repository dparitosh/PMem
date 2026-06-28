from __future__ import annotations

from pathlib import Path
from typing import Any

from ontology_agentic.api_clients.depo_client import DepoApiClient
from ontology_agentic.config import settings


def _client(base_url: str | None = None, timeout_seconds: float | None = None, auth_token: str | None = None) -> DepoApiClient:
    return DepoApiClient(
        base_url=base_url or settings.depo_api_base_url,
        timeout_seconds=timeout_seconds or settings.depo_api_timeout_seconds,
        auth_token=auth_token if auth_token is not None else settings.depo_api_token,
    )


def depo_healthcheck(base_url: str | None = None) -> dict[str, Any]:
    return _client(base_url=base_url).health()


def depo_list_registered_ontologies(base_url: str | None = None) -> dict[str, Any]:
    return _client(base_url=base_url).list_registered_ontologies()


def depo_execute_semantic_workflow(workflow_id: str, payload: dict[str, Any] | None = None, base_url: str | None = None) -> dict[str, Any]:
    return _client(base_url=base_url).execute_workflow(workflow_id=workflow_id, payload=payload or {})


def depo_merge_ontologies(from_ontology_id: str, to_ontology_id: str, dry_run: bool = False, base_url: str | None = None) -> dict[str, Any]:
    return _client(base_url=base_url).merge_ontologies(
        from_ontology_id=from_ontology_id,
        to_ontology_id=to_ontology_id,
        dry_run=dry_run,
    )


def depo_export_import_owl(task_id: str, export_format: str = "ttl", output_dir: str | Path | None = None, base_url: str | None = None) -> dict[str, Any]:
    destination = Path(output_dir).resolve() if output_dir else settings.output_dir / "depo_exports"
    return _client(base_url=base_url).download_import_owl_export(
        task_id=task_id,
        output_dir=destination,
        export_format=export_format,
    )
