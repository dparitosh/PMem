from __future__ import annotations

from collections import Counter
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.ingestion_service.tabular import node_query, relationship_query
from backend.main import ONTOLOGY_DIR, app
from data_product_package.builder import DataProductBuilder
from data_product_package.models import ArtifactSpec, DataProductSpec
from backend.ontology_service.app import app as standalone_app
from backend.oslc_service.client import OSLCClient


def test_backend_package_import_exposes_unique_openapi_operations() -> None:
    schema = app.openapi()
    operation_ids = [
        operation["operationId"]
        for path_item in schema["paths"].values()
        for operation in path_item.values()
        if isinstance(operation, dict) and "operationId" in operation
    ]

    assert schema["paths"]["/api/v1/metadata-registry/assets"]
    assert not [value for value, count in Counter(operation_ids).items() if count > 1]
    assert ONTOLOGY_DIR == Path(__file__).resolve().parents[2] / "frontend" / "public" / "Ontology"


def test_standalone_ontology_service_contract() -> None:
    client = TestClient(standalone_app)

    health = client.get("/api/v1/ontologies/health")
    capabilities = client.get("/api/v1/ontologies/capabilities")
    mcp = client.get("/api/v1/ontologies/mcp")
    legacy_domains = client.get("/api/v1/ontology/pipelines/domains")

    assert health.status_code == 200
    assert health.json()["service"] == "ontology"
    assert capabilities.status_code == 200
    assert capabilities.json()["provider"] == "Semantica"
    assert mcp.json()["transport"] == "stdio"
    assert legacy_domains.status_code == 200


def test_ingestion_merge_query_is_valid_and_identifiers_are_restricted() -> None:
    query = node_query("Part", ["part_id", "name"], ["part_id"])

    assert "MERGE (n:`Part` {`part_id`: row.`part_id`})" in query
    assert "n.`part_id` = row.`part_id`" in query
    with pytest.raises(ValueError, match="Invalid node label"):
        node_query("Part`) DETACH DELETE n //", ["name"], [])
    with pytest.raises(ValueError, match="Invalid relationship type"):
        relationship_query("LINKS]->() //", "Part", "Part", "id", "id")


def test_oslc_client_requires_a_preconfigured_remote_base(monkeypatch) -> None:
    monkeypatch.delenv("OSLC_REMOTE_BASE_URL", raising=False)
    client = OSLCClient()

    with pytest.raises(RuntimeError, match="not configured"):
        client.discover()


def test_data_product_builder_handles_case_insensitive_artifact_collisions(tmp_path) -> None:
    first = tmp_path / "one.ttl"
    second = tmp_path / "two.ttl"
    first.write_text("first", encoding="utf-8")
    second.write_text("second", encoding="utf-8")
    spec = DataProductSpec(
        product_id="case-test",
        name="Case Test",
        artifacts=[
            ArtifactSpec(path=str(first), name="Ontology.ttl"),
            ArtifactSpec(path=str(second), name="ontology.ttl"),
        ],
    )

    result = DataProductBuilder(str(tmp_path / "output")).build(spec)
    names = [item["name"] for item in result["manifest"]["artifacts"]]

    assert names == ["Ontology.ttl", "ontology-2.ttl"]
    assert len(list((Path(result["directory"]) / "artifacts").iterdir())) == 2
