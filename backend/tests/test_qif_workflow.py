from pathlib import Path

from fastapi.testclient import TestClient
from rdflib import Graph
from rdflib.namespace import RDFS

from backend.qif.app import app
from backend.qif.ontology_builder import build_ontology_turtle, inspect_schema_set
from backend.qif.task_service import QifTaskService


XSD_HEADER = '<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema" xmlns:tns="urn:test:qif" targetNamespace="urn:test:qif">'


def test_qif_service_exposes_health_and_catalog():
    client = TestClient(app)
    assert client.get("/api/v1/qif/health").json()["status"] == "ok"
    catalog = client.get("/api/v1/qif/catalog").json()
    assert catalog["standard"] == "QIF 3.0"
    assert catalog["file_count"] >= 1


def test_qif_api_rejects_invalid_task_identifiers_and_non_xsd_uploads():
    client = TestClient(app)
    missing = client.get("/api/v1/qif/tasks/not-a-task")
    assert missing.status_code == 404

    response = client.post(
        "/api/v1/qif/tasks/upload",
        files=[("files", ("not-schema.txt", b"not an xsd", "text/plain"))],
        data={"ontology_name": "Invalid upload", "prefix": "invalid", "description": "test"},
    )
    assert response.status_code == 422
    assert "not an XSD" in response.json()["detail"]


def test_qif_task_prepares_a_valid_multi_xsd_preview(tmp_path: Path):
    shared = tmp_path / "Shared.xsd"
    shared.write_text(XSD_HEADER + '<xs:complexType name="SharedType"/></xs:schema>', encoding="utf-8")
    document = tmp_path / "Document.xsd"
    document.write_text(
        XSD_HEADER + '<xs:include schemaLocation="Shared.xsd"/>'
        '<xs:complexType name="DocumentType"><xs:sequence><xs:element name="shared" type="tns:SharedType" minOccurs="0" maxOccurs="unbounded"/></xs:sequence></xs:complexType></xs:schema>',
        encoding="utf-8",
    )
    service = QifTaskService(tmp_path / "workflow_store")
    task = service.create(source_paths=[shared, document], ontology_name="Test QIF", prefix="testqif", description="test", source="test")
    service.prepare(task["task_id"])
    preview = service.preview(task["task_id"])
    assert preview["status"] == "awaiting_approval"
    assert preview["validation"]["valid"] is True
    assert preview["validation"]["resolved_references"][0]["resolved_to"] == "Shared.xsd"
    assert preview["summary"]["classes_created"] >= 2
    assert {artifact["kind"] for artifact in preview["artifacts"]} == {"ontology", "validation"}


def test_qif_publish_and_graph_retry_are_queued_once_without_double_submission(tmp_path: Path, monkeypatch):
    source = tmp_path / "Minimal.xsd"
    source.write_text(XSD_HEADER + '<xs:complexType name="MinimalType"/></xs:schema>', encoding="utf-8")
    service = QifTaskService(tmp_path / "workflow_store")
    task = service.create(source_paths=[source], ontology_name="Queued QIF", prefix="queuedqif", description="test", source="test")

    service._update(task["task_id"], status="awaiting_approval", stage="review", progress=80)
    monkeypatch.setattr(service, "submit_commit", lambda task_id: True)
    queued = service.queue_commit(task["task_id"])
    assert queued["status"] == "commit_queued"
    assert service.get(task["task_id"])["stage"] == "register_queued"

    service._update(task["task_id"], status="completed_with_warnings", stage="completed", ontology_id="ontology-1", graph_sync={"status": "failed", "attempts": 1})
    monkeypatch.setattr(service, "submit_graph_retry", lambda task_id: True)
    retry = service.queue_graph_retry(task["task_id"])
    assert retry["status"] == "graph_retry_queued"
    assert service.get(task["task_id"])["stage"] == "graph_sync_queued"


def test_qif_generator_keeps_owner_scoped_properties_and_declared_element_types(tmp_path: Path):
    schema = tmp_path / "Identity.xsd"
    schema.write_text(
        XSD_HEADER +
        '<xs:complexType name="SharedType"/>'
        '<xs:complexType name="OwnerA"><xs:sequence><xs:element name="status" type="xs:string"/></xs:sequence></xs:complexType>'
        '<xs:complexType name="OwnerB"><xs:sequence><xs:element name="status" type="xs:string"/></xs:sequence></xs:complexType>'
        '<xs:element name="Root" type="tns:SharedType"/>'
        '</xs:schema>',
        encoding="utf-8",
    )
    inspection = inspect_schema_set([schema])
    turtle, summary = build_ontology_turtle(inspection, "identity")
    graph = Graph().parse(data=turtle, format="turtle")

    root = next(subject for subject in graph.subjects(RDFS.label, None) if str(next(graph.objects(subject, RDFS.label))) == "Root")
    shared = next(subject for subject in graph.subjects(RDFS.label, None) if str(next(graph.objects(subject, RDFS.label))) == "SharedType")
    assert (root, RDFS.subClassOf, shared) in graph

    status_properties = [subject for subject in graph.subjects(RDFS.label, None) if str(next(graph.objects(subject, RDFS.label))) == "status"]
    assert len(status_properties) == 2
    assert all(any(graph.triples((property_uri, None, None))) for property_uri in status_properties)
    domains = {str(next(graph.objects(property_uri, RDFS.domain))) for property_uri in status_properties}
    assert len(domains) == 2
    assert summary["properties_created"] == 2
