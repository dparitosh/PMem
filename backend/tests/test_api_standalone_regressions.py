from __future__ import annotations

from collections import Counter
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.data_ingestion import (
    create_node_import_query,
    create_relationship_import_query,
)
from backend.main import ONTOLOGY_DIR, app
from data_product_package.builder import DataProductBuilder
from data_product_package.models import ArtifactSpec, DataProductSpec
from ontology_agentic.api_clients.depo_client import (
    DepoApiClient,
    DepoApiError,
    DepoBinaryResponse,
)
from app.main import app as standalone_app


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


def test_standalone_http_adapter_contract() -> None:
    client = TestClient(standalone_app)

    health = client.get("/health")
    tools = client.get("/api/v1/tools")
    invalid_import = client.post("/api/v1/openapi/import", json={"document": []})

    assert health.status_code == 200
    assert health.json()["service"] == "ontology-agentic-service"
    assert tools.status_code == 200
    assert isinstance(tools.json()["tools"], list)
    assert invalid_import.status_code == 400


def test_ingestion_merge_query_is_valid_and_identifiers_are_restricted() -> None:
    query = create_node_import_query("Part", ["part_id", "name"], ["part_id"])

    assert "MERGE (n:`Part` {`part_id`: row.`part_id`})" in query
    assert "n.`part_id` = row.`part_id`" in query
    with pytest.raises(ValueError, match="Invalid node label"):
        create_node_import_query("Part`) DETACH DELETE n //", ["name"], [])
    with pytest.raises(ValueError, match="Invalid relationship type"):
        create_relationship_import_query("LINKS]->() //", "Part", "Part", "id", "id")


def test_depo_client_encodes_path_segments_and_validates_configuration(monkeypatch) -> None:
    client = DepoApiClient("https://depo.example.test", timeout_seconds=5)
    captured = {}

    def fake_request(method, path, data=None):
        captured["path"] = path
        return {}

    monkeypatch.setattr(client, "_request_json", fake_request)
    client.oslc_resource("requirement/a b")

    assert captured["path"].startswith("/oslc/resources/requirement%2Fa%20b?")
    with pytest.raises(DepoApiError, match="absolute HTTP"):
        DepoApiClient("file:///tmp/socket")
    with pytest.raises(DepoApiError, match="greater than zero"):
        DepoApiClient("https://depo.example.test", timeout_seconds=0)


def test_depo_download_cannot_escape_output_directory(tmp_path, monkeypatch) -> None:
    client = DepoApiClient("https://depo.example.test")
    monkeypatch.setattr(
        client,
        "export_import_owl",
        lambda *_args, **_kwargs: DepoBinaryResponse(
            filename="../../outside.ttl",
            media_type="text/turtle",
            body=b"ontology",
            download_url="https://depo.example.test/export",
        ),
    )

    result = client.download_import_owl_export("task-1", tmp_path / "downloads")

    assert Path(result["saved_to"]) == (tmp_path / "downloads" / "outside.ttl").resolve()
    assert not (tmp_path / "outside.ttl").exists()


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
