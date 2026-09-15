from fastapi.testclient import TestClient
import pytest

from backend.data_pipeline_service.app import app
from backend.data_pipeline_service.runner import SparkJobRunner
from backend.data_pipeline_service.scheduler import ScheduledJobSupervisor
from backend.mesh_store import InMemoryRegistry


@pytest.fixture(autouse=True)
def isolated_artifact_store(monkeypatch, tmp_path):
    monkeypatch.setenv("ARTIFACT_STORAGE", str(tmp_path / "artifacts"))
    monkeypatch.setattr("backend.data_pipeline_service.router.approval_identity", lambda *args, **kwargs: "test-operator")
    monkeypatch.setattr("backend.data_pipeline_service.speed_router.approval_identity", lambda *args, **kwargs: "test-operator")


def test_data_pipeline_service_exposes_ui_ready_transform_contract(monkeypatch):
    def transform(payload, *, correlation_id):
        return {"job_id": "run-1", "status": "completed", "correlation_id": correlation_id, "quality": {"input_records": 2, "rejected_records": 0}, "series": [], "echarts": {"x_axis": [], "series": []}}

    monkeypatch.setattr("backend.data_pipeline_service.router.runner.transform_quality_summary", transform)
    response = TestClient(app).post("/api/v1/pipeline/jobs/transform", json={"records": [{"source_standard": "ReqIF", "canonical_concept": "Requirement"}]})

    assert response.status_code == 200
    assert response.json()["status"] == "completed"
    assert "echarts" in response.json()


def test_data_pipeline_service_rejects_invalid_payload_before_spark():
    response = TestClient(app).post("/api/v1/pipeline/jobs/transform", json={"records": []})

    assert response.status_code == 422


def test_data_pipeline_telemetry_is_available_without_initializing_spark(monkeypatch):
    monkeypatch.setattr("backend.data_pipeline_service.router.runner.telemetry", lambda: {"service": "data-pipeline", "spark": {"spark_initialized": False}, "totals": {"runs": 0}, "recent_runs": []})
    monkeypatch.setattr("backend.data_pipeline_service.router.run_records.telemetry_summary", lambda: {"runs": 0, "records_accepted": 0, "records_rejected": 0, "recent_runs": []})

    response = TestClient(app).get("/api/v1/pipeline/telemetry")

    assert response.status_code == 200
    assert response.json()["spark"]["spark_initialized"] is False
    assert response.json()["durable_job_telemetry"]["runs"] == 0


def test_input_quality_gate_rejects_explicitly_invalid_records_without_spark():
    accepted, rejected = SparkJobRunner._validate_records([
        {"source_standard": "AP242", "canonical_concept": "Part", "validation_status": "valid"},
        {"source_standard": "QIF", "canonical_concept": "Characteristic", "validation_status": "invalid"},
    ])

    assert accepted == [{"source_standard": "AP242", "canonical_concept": "Part", "validation_status": "valid"}]
    assert rejected[0]["rule"] == "validation_status.not_invalid"


def test_data_quality_job_emits_governed_evidence_for_each_quality_dimension(monkeypatch):
    class FakeRow:
        def __init__(self, value): self.value = value
        def asDict(self): return self.value
    class FakeFrame:
        def groupBy(self, *_): return self
        def count(self): return self
        def orderBy(self, *_): return self
        def collect(self): return [FakeRow({"source_standard": "AP242", "canonical_concept": "Part", "validation_status": "valid", "count": 1})]
    class FakeSpark:
        def createDataFrame(self, _): return FakeFrame()
    runner = SparkJobRunner()
    monkeypatch.setattr(runner, "_spark_session", lambda: FakeSpark())

    result = runner.assess_data_quality({"records": [
        {"source_standard": "AP242", "canonical_concept": "Part", "source_id": "part-1", "artifact_id": "sha256:" + "a" * 64},
        {"source_standard": "AP242", "canonical_concept": "Part", "source_id": "part-1", "artifact_id": "sha256:" + "a" * 64},
        {"source_standard": "ReqIF", "canonical_concept": "Requirement", "source_id": "req-1"},
    ]}, correlation_id="quality-test")

    assert result["job_type"] == "data-quality-assessment"
    assert result["output_contract"] == "data-quality-report-v1"
    assert result["quality"]["accepted_records"] == 1
    assert result["quality"]["rejected_records"] == 2
    assert result["quality"]["uniqueness"] < 1
    assert result["quality"]["provenance"] < 1
    assert result["partition_artifacts"]["accepted"]


def test_data_quality_job_definition_is_an_explicit_governed_job(monkeypatch):
    monkeypatch.setattr("backend.data_pipeline_service.job_definitions.store", InMemoryRegistry())
    response = TestClient(app).post("/api/v1/pipeline/jobs/definitions", json={
        "job_id": "engineering-data-quality",
        "name": "Engineering data quality",
        "version": "1.0.0",
        "owner": "data-governance",
        "job_type": "data-quality-assessment",
        "quality_profile": "data-quality-core-v1",
    })
    assert response.status_code == 201
    assert response.json()["output_contract"] == "data-quality-report-v1"


def test_schema_analytics_is_a_retained_spark_data_job(monkeypatch):
    class FakeRow:
        def __init__(self, value): self.value = value
        def asDict(self): return self.value
    class FakeFrame:
        def orderBy(self, *_): return self
        def collect(self): return [FakeRow({"metric": "classes", "value": 4})]
    class FakeSpark:
        def createDataFrame(self, _): return FakeFrame()
    source = __import__("backend.artifact_store", fromlist=["ArtifactStore"]).ArtifactStore().ingest_bytes(
        b'<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"/>', filename="model.xsd", kind="engineering-schema-source", media_type="application/xml"
    )
    monkeypatch.setattr("backend.ingestion_service.schema_conversion.converter.convert", lambda **_: {
        "format": "XSD", "source_kind": "schema", "statistics": {"classes": 4},
        "schema_validation": {"errors": []},
        "artifacts": {"source": source["artifact_id"], "serialization": "sha256:" + "b" * 64, "analytics_profile": "sha256:" + "c" * 64},
        "data_product_draft": {"contract": "schema-analytics-data-product-v1", "artifacts": [source["artifact_id"], "sha256:" + "b" * 64, "sha256:" + "c" * 64], "quality_status": "validated"},
    })
    runner = SparkJobRunner()
    monkeypatch.setattr(runner, "_spark_session", lambda: FakeSpark())

    result = runner.build_schema_analytics_product({"artifact_id": source["artifact_id"]}, correlation_id="schema-product")

    assert result["job_type"] == "schema-analytics-product"
    assert result["output_contract"] == "schema-analytics-data-product-draft-v1"
    assert result["data_product_draft"]["contract"] == "schema-analytics-data-product-v1"
    assert result["counts"]["retained_artifacts"] == 3


def test_schema_analytics_rejects_non_schema_artifacts(monkeypatch):
    source = __import__("backend.artifact_store", fromlist=["ArtifactStore"]).ArtifactStore().ingest_bytes(
        b"not a schema", filename="notes.txt", kind="unstructured-document", media_type="text/plain"
    )
    with pytest.raises(ValueError, match="engineering-schema-source"):
        SparkJobRunner().build_schema_analytics_product({"artifact_id": source["artifact_id"]}, correlation_id="bad-schema")


def test_neo4j_connector_rejects_an_unsupported_spark_runtime(tmp_path, monkeypatch):
    (tmp_path / "RELEASE").write_text("Spark 4.2.0 built for Hadoop", encoding="utf-8")
    monkeypatch.setenv("DEPO_SPARK_NEO4J_PACKAGE", "org.neo4j.connectors:spark:6.0.0-s_2.13")
    monkeypatch.setenv("NEO4J_URI", "neo4j://localhost:7687")
    monkeypatch.setenv("NEO4J_USER", "test")
    monkeypatch.setenv("NEO4J_PASS", "test")

    with pytest.raises(Exception, match="supports Spark 4.0"):
        SparkJobRunner()._neo4j_connector_configuration(tmp_path)


def test_versioned_data_job_definition_requires_approval_before_execution(monkeypatch):
    registry = InMemoryRegistry()
    monkeypatch.setattr("backend.data_pipeline_service.job_definitions.store", registry)
    monkeypatch.setattr("backend.data_pipeline_service.run_records.store", InMemoryRegistry())
    monkeypatch.setattr("backend.data_pipeline_service.router.approval_identity", lambda *args, **kwargs: "pipeline-steward")
    monkeypatch.setattr(
        "backend.data_pipeline_service.router.runner.transform_quality_summary",
        lambda payload, *, correlation_id: {"job_id": "run-1", "status": "completed", "correlation_id": correlation_id, "quality": {}, "series": [], "echarts": {}},
    )
    client = TestClient(app)
    definition = {
        "job_id": "qif-quality-summary",
        "name": "QIF quality summary",
        "version": "1.0.0",
        "owner": "data-engineering",
        "job_type": "interactive-quality-summary",
        "quality_profile": "semantic-core-v1",
    }

    created = client.post("/api/v1/pipeline/jobs/definitions", json=definition)
    assert created.status_code == 201
    assert created.json()["lifecycle_state"] == "draft"

    blocked = client.post("/api/v1/pipeline/jobs/definitions/qif-quality-summary/1.0.0/run", json={"records": [{"source_standard": "QIF", "canonical_concept": "Part"}]})
    assert blocked.status_code == 409

    approved = client.post("/api/v1/pipeline/jobs/definitions/qif-quality-summary/1.0.0/approve", json={"approved_by": "pipeline-steward"})
    assert approved.status_code == 200
    assert approved.json()["approved_by"] == "pipeline-steward"

    completed = client.post("/api/v1/pipeline/jobs/definitions/qif-quality-summary/1.0.0/run", json={"records": [{"source_standard": "QIF", "canonical_concept": "Part"}]})
    assert completed.status_code == 200
    assert completed.json()["configured_job"]["job_id"] == "qif-quality-summary"


def test_data_job_definition_rejects_unknown_executable_type(monkeypatch):
    monkeypatch.setattr("backend.data_pipeline_service.job_definitions.store", InMemoryRegistry())
    response = TestClient(app).post("/api/v1/pipeline/jobs/definitions", json={
        "job_id": "unsafe-job",
        "name": "Unsafe job",
        "version": "1.0.0",
        "owner": "data-engineering",
        "job_type": "arbitrary-python",
        "quality_profile": "semantic-core-v1",
    })

    assert response.status_code == 422
    assert "job_type" in response.json()["detail"]


def test_configured_ceim_job_enforces_standard_allowlist_and_dispatches(monkeypatch):
    monkeypatch.setattr("backend.data_pipeline_service.job_definitions.store", InMemoryRegistry())
    monkeypatch.setattr("backend.data_pipeline_service.run_records.store", InMemoryRegistry())
    monkeypatch.setattr("backend.data_pipeline_service.router.approval_identity", lambda *args, **kwargs: "pipeline-steward")
    monkeypatch.setattr(
        "backend.data_pipeline_service.router.runner.normalize_ceim_batch",
        lambda payload, *, correlation_id, validate: {"job_id": "run-ceim", "status": "completed", "validation": {"conforms": True}, "series": []},
    )
    client = TestClient(app)
    created = client.post("/api/v1/pipeline/jobs/definitions", json={
        "job_id": "ap242-normalize",
        "name": "AP242 normalization",
        "version": "1.0.0",
        "owner": "data-engineering",
        "job_type": "normalize-ceim",
        "quality_profile": "semantic-core-v1",
        "allowed_standards": ["ap242"],
    })
    assert created.status_code == 201
    client.post("/api/v1/pipeline/jobs/definitions/ap242-normalize/1.0.0/approve", json={"approved_by": "pipeline-steward"})

    rejected = client.post("/api/v1/pipeline/jobs/definitions/ap242-normalize/1.0.0/run", json={"standard": "qif", "entities": [{"source_type": "Part", "source_id": "1"}]})
    assert rejected.status_code == 422

    completed = client.post("/api/v1/pipeline/jobs/definitions/ap242-normalize/1.0.0/run", json={"standard": "ap242", "entities": [{"source_type": "Part", "source_id": "1"}]})
    assert completed.status_code == 200
    assert completed.json()["configured_job"]["job_type"] == "normalize-ceim"
    assert completed.json()["run_manifest"]["input_manifest"]["payload_digest"].startswith("sha256:")


def test_configured_unstructured_evidence_job_uses_the_governed_run_surface(monkeypatch):
    monkeypatch.setattr("backend.data_pipeline_service.job_definitions.store", InMemoryRegistry())
    monkeypatch.setattr("backend.data_pipeline_service.run_records.store", InMemoryRegistry())
    monkeypatch.setattr("backend.data_pipeline_service.router.approval_identity", lambda *args, **kwargs: "pipeline-steward")
    monkeypatch.setattr(
        "backend.data_pipeline_service.router.runner.validate_unstructured_evidence",
        lambda payload, *, correlation_id: {"job_id": "run-document", "status": "completed", "counts": {"accepted_documents": 1}, "quality": {}, "series": []},
    )
    client = TestClient(app)
    created = client.post("/api/v1/pipeline/jobs/definitions", json={
        "job_id": "document-evidence-check",
        "name": "Document evidence quality check",
        "version": "1.0.0",
        "owner": "knowledge-engineering",
        "job_type": "validate-unstructured-evidence",
        "quality_profile": "semantic-core-v1",
    })
    assert created.status_code == 201
    client.post("/api/v1/pipeline/jobs/definitions/document-evidence-check/1.0.0/approve", json={"approved_by": "pipeline-steward"})

    completed = client.post("/api/v1/pipeline/jobs/definitions/document-evidence-check/1.0.0/run", json={
        "artifact_ids": ["sha256:" + "a" * 64],
        "documents": [{"artifact_id": "sha256:" + "a" * 64, "document_id": "doc-1", "chunks": [{"chunk_id": "chunk-1", "content": "A traceable requirement."}]}],
    })
    assert completed.status_code == 200
    assert completed.json()["configured_job"]["job_type"] == "validate-unstructured-evidence"


def test_document_enrichment_job_creates_a_provenance_preserving_graph_proposal(monkeypatch):
    class FakeRow:
        def __init__(self, value): self.value = value
        def asDict(self): return self.value
    class FakeFrame:
        def groupBy(self, *_): return self
        def sum(self, *_): return self
        def orderBy(self, *_): return self
        def collect(self): return [FakeRow({"media_type": "text/plain", "sum(chunk_count)": 2, "sum(token_count)": 4})]
    class FakeSpark:
        def createDataFrame(self, _): return FakeFrame()
    source = __import__("backend.artifact_store", fromlist=["ArtifactStore"]).ArtifactStore().ingest_bytes(
        b"Traceable engineering evidence", filename="evidence.txt", kind="unstructured-document", media_type="text/plain"
    )
    runner = SparkJobRunner()
    monkeypatch.setattr(runner, "_spark_session", lambda: FakeSpark())

    result = runner.enrich_document_evidence({"documents": [{
        "artifact_id": source["artifact_id"], "document_id": "spec-1",
        "chunks": [{"chunk_id": "a", "content": " Motor   cover\ufeff "}, {"chunk_id": "b", "content": "Must be traceable."}],
    }]}, correlation_id="test-correlation")

    assert result["output_contract"] == "document-graph-proposal-v1"
    assert result["counts"]["graph_nodes"] == 3
    assert result["counts"]["graph_relationships"] == 2
    assert result["quality"]["not_performed"] == ["OCR", "model-based NER", "embedding generation", "graph publication"]
    _, proposal_path = __import__("backend.artifact_store", fromlist=["ArtifactStore"]).ArtifactStore().resolve(result["partition_artifacts"]["accepted"])
    proposal = __import__("json").loads(proposal_path.read_text(encoding="utf-8"))
    assert proposal["documents"][0]["chunks"][0]["content"] == "Motor cover"
    assert proposal["documents"][0]["chunks"][0]["content_digest"].startswith("sha256:")
    assert proposal["publication"].startswith("not_attempted")


def test_unstructured_proposal_uses_the_same_ceim_validation_contract(monkeypatch):
    class FakeRow:
        def __init__(self, value): self.value = value
        def asDict(self): return self.value
    class FakeFrame:
        def groupBy(self, *_): return self
        def count(self): return self
        def orderBy(self, *_): return self
        def collect(self): return [FakeRow({"ceim_type": "Document", "count": 1})]
    class FakeSpark:
        def createDataFrame(self, _): return FakeFrame()

    proposal = {
        "contract": "document-graph-proposal-v1",
        "nodes": [
            {"id": "document:spec-1", "type": "Document", "document_id": "spec-1", "artifact_id": "sha256:" + "a" * 64, "media_type": "text/plain"},
            {"id": "document-chunk:spec-1:1", "type": "DocumentChunk", "document_id": "spec-1", "chunk_id": "1", "ordinal": 0, "content_digest": "sha256:" + "b" * 64},
        ],
        "relationships": [{"type": "HAS_CHUNK", "source": "document:spec-1", "target": "document-chunk:spec-1:1"}],
    }
    artifact = __import__("backend.artifact_store", fromlist=["ArtifactStore"]).ArtifactStore().ingest_bytes(
        __import__("json").dumps(proposal).encode("utf-8"), filename="document-proposal.json", kind="document-graph-proposal", media_type="application/json"
    )
    runner = SparkJobRunner()
    monkeypatch.setattr(runner, "_spark_session", lambda: FakeSpark())

    result = runner.normalize_unstructured_ceim({"proposal_artifact_id": artifact["artifact_id"]}, correlation_id="unstructured-ceim")

    assert result["job_type"] == "normalize-unstructured-ceim"
    assert result["input_contract"] == "document-graph-proposal-v1"
    assert result["validation"]["conforms"] is True
    assert result["partition_artifacts"]["accepted"]


def test_document_evidence_workflow_uses_approved_stages_and_artifact_handoffs(monkeypatch):
    from backend.data_pipeline_service import router

    definitions = {
        ("document-validate", "1.0.0"): {"job_id": "document-validate", "version": "1.0.0", "job_type": "validate-unstructured-evidence", "lifecycle_state": "approved", "enabled": True},
        ("document-enrich", "1.0.0"): {"job_id": "document-enrich", "version": "1.0.0", "job_type": "enrich-document-evidence", "lifecycle_state": "approved", "enabled": True},
        ("document-normalize", "1.0.0"): {"job_id": "document-normalize", "version": "1.0.0", "job_type": "normalize-unstructured-ceim", "lifecycle_state": "approved", "enabled": True},
    }
    monkeypatch.setattr(router.job_definitions, "get", lambda job_id, version: definitions.get((job_id, version)))
    calls = []
    def execute(definition, payload, correlation_id):
        calls.append((definition["job_type"], payload))
        accepted = "sha256:" + ("a" if definition["job_type"] == "enrich-document-evidence" else "b") * 64
        return {"status": "completed", "run_manifest": {"run_id": f"{definition['job_id']}-run", "output_manifest": {"partition_artifacts": {"accepted": accepted}}}}
    monkeypatch.setattr(router, "execute_configured_job", execute)

    result = router.execute_document_evidence_workflow({
        "documents": [{"document_id": "d1"}],
        "stages": {
            "validation": {"job_id": "document-validate", "version": "1.0.0"},
            "enrichment": {"job_id": "document-enrich", "version": "1.0.0"},
            "normalization": {"job_id": "document-normalize", "version": "1.0.0"},
        },
    }, correlation_id="workflow-test", actor="pipeline-steward")

    assert result["status"] == "completed"
    assert [job_type for job_type, _ in calls] == ["validate-unstructured-evidence", "enrich-document-evidence", "normalize-unstructured-ceim"]
    assert calls[-1][1]["proposal_artifact_id"] == "sha256:" + "a" * 64
    assert calls[-1][1]["standard"] == "unstructured-evidence"


def test_configured_document_enrichment_job_uses_governed_run_surface(monkeypatch):
    monkeypatch.setattr("backend.data_pipeline_service.job_definitions.store", InMemoryRegistry())
    monkeypatch.setattr("backend.data_pipeline_service.run_records.store", InMemoryRegistry())
    monkeypatch.setattr("backend.data_pipeline_service.router.approval_identity", lambda *args, **kwargs: "pipeline-steward")
    monkeypatch.setattr(
        "backend.data_pipeline_service.router.runner.enrich_document_evidence",
        lambda payload, *, correlation_id: {"job_id": "run-enriched-document", "status": "completed", "counts": {"accepted_documents": 1, "graph_nodes": 2}, "quality": {}, "series": []},
    )
    client = TestClient(app)
    definition = {"job_id": "document-structure", "name": "Document structural enrichment", "version": "1.0.0", "owner": "knowledge-engineering", "job_type": "enrich-document-evidence", "quality_profile": "unstructured-evidence-v1"}
    assert client.post("/api/v1/pipeline/jobs/definitions", json=definition).status_code == 201
    assert client.post("/api/v1/pipeline/jobs/definitions/document-structure/1.0.0/approve", json={}).status_code == 200
    response = client.post("/api/v1/pipeline/jobs/definitions/document-structure/1.0.0/run", json={"documents": [{"artifact_id": "sha256:" + "a" * 64, "document_id": "spec-1", "chunks": [{"chunk_id": "1", "content": "Evidence"}]}]})
    assert response.status_code == 200
    assert response.json()["configured_job"]["job_type"] == "enrich-document-evidence"
    assert response.json()["run_manifest"]["output_manifest"]["contract"] == "document-graph-proposal-v1"


def test_completed_job_can_replay_its_exact_retained_input(monkeypatch):
    registry = InMemoryRegistry()
    monkeypatch.setattr("backend.data_pipeline_service.job_definitions.store", registry)
    monkeypatch.setattr("backend.data_pipeline_service.run_records.store", InMemoryRegistry())
    monkeypatch.setattr("backend.data_pipeline_service.router.approval_identity", lambda *args, **kwargs: "pipeline-steward")
    calls = []
    def transform(payload, *, correlation_id):
        calls.append(payload)
        return {"job_id": f"run-{len(calls)}", "status": "completed", "correlation_id": correlation_id, "quality": {}, "series": [], "echarts": {}}
    monkeypatch.setattr("backend.data_pipeline_service.router.runner.transform_quality_summary", transform)
    client = TestClient(app)
    definition = {"job_id": "replayable-quality", "name": "Replayable quality", "version": "1.0.0", "owner": "data-engineering", "job_type": "interactive-quality-summary", "quality_profile": "semantic-core-v1"}
    assert client.post("/api/v1/pipeline/jobs/definitions", json=definition).status_code == 201
    assert client.post("/api/v1/pipeline/jobs/definitions/replayable-quality/1.0.0/approve", json={"approved_by": "pipeline-steward"}).status_code == 200
    first = client.post("/api/v1/pipeline/jobs/definitions/replayable-quality/1.0.0/run", json={"records": [{"source_standard": "QIF", "canonical_concept": "Part"}]})
    assert first.status_code == 200
    assert first.json()["run_manifest"]["input_manifest"]["raw_payload_artifact_id"].startswith("sha256:")
    replay = client.post(f"/api/v1/pipeline/jobs/runs/{first.json()['run_manifest']['run_id']}/replay")
    assert replay.status_code == 200
    assert calls[1]["records"] == calls[0]["records"]
    assert calls[1]["replay_of"] == first.json()["run_manifest"]["run_id"]


def test_rdf_quality_job_is_governed_and_read_only(monkeypatch):
    monkeypatch.setattr("backend.data_pipeline_service.job_definitions.store", InMemoryRegistry())
    monkeypatch.setattr("backend.data_pipeline_service.run_records.store", InMemoryRegistry())
    monkeypatch.setattr("backend.data_pipeline_service.router.approval_identity", lambda *args, **kwargs: "pipeline-steward")
    monkeypatch.setattr(
        "backend.data_pipeline_service.router.runner.rdf_quality_statistics",
        lambda payload, *, correlation_id: {"job_id": "rdf-1", "status": "completed", "counts": {"triples_examined": 2}, "quality": {"publication": "not_attempted"}},
    )
    client = TestClient(app)
    definition = {"job_id": "rdf-quality", "name": "RDF quality", "version": "1.0.0", "owner": "data-engineering", "job_type": "rdf-quality-statistics", "quality_profile": "semantic-core-v1"}
    assert client.post("/api/v1/pipeline/jobs/definitions", json=definition).status_code == 201
    assert client.post("/api/v1/pipeline/jobs/definitions/rdf-quality/1.0.0/approve", json={"approved_by": "pipeline-steward"}).status_code == 200
    response = client.post("/api/v1/pipeline/jobs/definitions/rdf-quality/1.0.0/run", json={"artifact_id": "sha256:" + "b" * 64})
    assert response.status_code == 200
    assert response.json()["configured_job"]["job_type"] == "rdf-quality-statistics"
    assert response.json()["quality"]["publication"] == "not_attempted"


def test_rdf_deduplicate_job_is_governed_and_retains_partitions(monkeypatch):
    monkeypatch.setattr("backend.data_pipeline_service.job_definitions.store", InMemoryRegistry())
    monkeypatch.setattr("backend.data_pipeline_service.run_records.store", InMemoryRegistry())
    monkeypatch.setattr(
        "backend.data_pipeline_service.router.runner.rdf_deduplicate_serialize",
        lambda payload, *, correlation_id: {
            "job_id": "rdf-normalized-1", "job_type": "rdf-deduplicate-serialize", "status": "quality_warning",
            "counts": {"triples_examined": 4, "distinct_triples": 2, "duplicate_triples": 1, "malformed_lines": 1},
            "quality": {"publication": "not_attempted; canonical publication approval is required"},
            "partition_artifacts": {"accepted": "sha256:" + "a" * 64, "rejected": "sha256:" + "b" * 64},
        },
    )
    client = TestClient(app)
    definition = {"job_id": "rdf-canonicalize", "name": "RDF canonicalization", "version": "1.0.0", "owner": "data-engineering", "job_type": "rdf-deduplicate-serialize", "quality_profile": "semantic-core-v1"}
    assert client.post("/api/v1/pipeline/jobs/definitions", json=definition).status_code == 201
    assert client.post("/api/v1/pipeline/jobs/definitions/rdf-canonicalize/1.0.0/approve", json={}).status_code == 200
    response = client.post("/api/v1/pipeline/jobs/definitions/rdf-canonicalize/1.0.0/run", json={"artifact_id": "sha256:" + "c" * 64})
    assert response.status_code == 200
    body = response.json()
    assert body["configured_job"]["job_type"] == "rdf-deduplicate-serialize"
    assert body["run_manifest"]["output_manifest"]["contract"] == "canonical-ntriples-v1"
    assert body["run_manifest"]["output_manifest"]["partition_artifacts"]["accepted"].startswith("sha256:")


def test_speed_path_is_idempotent_and_reconciles_through_ceim_without_graph_write(monkeypatch):
    from types import SimpleNamespace
    from backend.data_pipeline_service import speed_path
    monkeypatch.setattr(speed_path, "sources", InMemoryRegistry())
    monkeypatch.setattr(speed_path, "events", InMemoryRegistry())
    monkeypatch.setattr(speed_path, "reconciliations", InMemoryRegistry())
    fake_contract = SimpleNamespace(
        version="0.1.0",
        mapping_pack=lambda standard: {"digest": "sha256:mapping"},
        normalize_entity=lambda *, standard, record: {"id": record["id"], "ceim_type": "Part"},
        normalize_relationship=lambda *, standard, record: record,
        validate_projection=lambda *, entities, relationships: {"conforms": True, "triple_count": len(entities) + len(relationships)},
    )
    monkeypatch.setattr(speed_path, "contract", fake_contract)
    client = TestClient(app)
    source = {"source_id": "plm-events", "name": "PLM changes", "owner": "engineering", "allowed_standards": ["ap242"], "max_lateness_seconds": 3600}
    assert client.post("/api/v1/pipeline/speed/sources", json=source).status_code == 201
    assert client.post("/api/v1/pipeline/speed/sources/plm-events/approve", json={}).status_code == 200
    event = {"event_id": "event-1", "source_id": "plm-events", "standard": "ap242", "occurred_at": "2026-09-04T10:00:00+00:00", "records": {"entities": [{"id": "part-1"}], "relationships": []}}
    captured = client.post("/api/v1/pipeline/speed/events", json=event)
    assert captured.status_code == 202
    assert client.post("/api/v1/pipeline/speed/events", json=event).json()["idempotent"] is True
    reconciled = client.post("/api/v1/pipeline/speed/reconciliations", json={"event_ids": ["event-1"]})
    assert reconciled.status_code == 202
    assert reconciled.json()["status"] == "ready_for_approved_publication"
    assert reconciled.json()["publication"].startswith("not_attempted")


def test_speed_path_publication_uses_ceim_boundary(monkeypatch):
    import httpx
    from backend.data_pipeline_service import speed_path
    monkeypatch.setattr(speed_path, "reconciliations", InMemoryRegistry())
    artifact = __import__("backend.artifact_store", fromlist=["ArtifactStore"]).ArtifactStore().ingest_bytes(
        b'{"standard":"qif","entities":[],"relationships":[]}', filename="speed.json", kind="accepted-semantic-partition", media_type="application/json"
    )
    speed_path.reconciliations.put("reconcile-1", {"reconciliation_id": "reconcile-1", "status": "ready_for_approved_publication", "partition_artifact_id": artifact["artifact_id"]})
    class FakeClient:
        def __init__(self, *args, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def post(self, url, **kwargs): return httpx.Response(200, request=httpx.Request("POST", url), json={"status": "published", "ontology_id": "speed"})
    monkeypatch.setattr("backend.data_pipeline_service.speed_router.httpx.AsyncClient", FakeClient)
    response = TestClient(app).post("/api/v1/pipeline/speed/reconciliations/reconcile-1/publish", json={"ontology_id": "speed", "semantic_release": {"asset_id": "ceim", "version": "0.1.0"}})
    assert response.status_code == 200
    assert response.json()["status"] == "published"


def test_schedule_is_configured_after_a_compatible_retained_run(monkeypatch):
    monkeypatch.setattr("backend.data_pipeline_service.job_definitions.store", InMemoryRegistry())
    monkeypatch.setattr("backend.data_pipeline_service.run_records.store", InMemoryRegistry())
    monkeypatch.setattr("backend.data_pipeline_service.router.approval_identity", lambda *args, **kwargs: "pipeline-steward")
    monkeypatch.setattr("backend.data_pipeline_service.router.runner.transform_quality_summary", lambda payload, *, correlation_id: {"status": "completed", "quality": {"input_records": 1, "accepted_records": 1, "rejected_records": 0}, "duration_ms": 1})
    client = TestClient(app)
    definition = {"job_id": "scheduled-quality", "name": "Scheduled quality", "version": "1.0.0", "owner": "data-engineering", "job_type": "interactive-quality-summary", "quality_profile": "semantic-core-v1"}
    assert client.post("/api/v1/pipeline/jobs/definitions", json=definition).status_code == 201
    assert client.post("/api/v1/pipeline/jobs/definitions/scheduled-quality/1.0.0/approve", json={}).status_code == 200
    run = client.post("/api/v1/pipeline/jobs/definitions/scheduled-quality/1.0.0/run", json={"records": [{"source_standard": "QIF", "canonical_concept": "Part"}]})
    assert run.status_code == 200
    configured = client.post("/api/v1/pipeline/jobs/definitions/scheduled-quality/1.0.0/schedule", json={"replay_run_id": run.json()["run_manifest"]["run_id"], "interval_seconds": 60, "retry_policy": {"max_attempts": 2, "backoff_seconds": 1}})
    assert configured.status_code == 200
    assert configured.json()["schedule"]["replay_run_id"] == run.json()["run_manifest"]["run_id"]


def test_scheduler_replays_due_input_with_bounded_retry(monkeypatch):
    definitions = InMemoryRegistry()
    runs = InMemoryRegistry()
    monkeypatch.setattr("backend.data_pipeline_service.job_definitions.store", definitions)
    monkeypatch.setattr("backend.data_pipeline_service.run_records.store", runs)
    prior = {"run_id": "seed-run", "job_id": "scheduled-quality", "job_version": "1.0.0", "started_at": "2000-01-01T00:00:00+00:00", "input_manifest": {"raw_payload_artifact_id": "sha256:" + "a" * 64}}
    runs.put("seed-run", prior)
    definitions.put("scheduled-quality:1.0.0", {"job_id": "scheduled-quality", "version": "1.0.0", "lifecycle_state": "approved", "enabled": True, "schedule": {"replay_run_id": "seed-run", "interval_seconds": 60}, "retry_policy": {"max_attempts": 2, "backoff_seconds": 1}})
    monkeypatch.setattr("backend.data_pipeline_service.scheduler.run_records.replay_payload", lambda record: {"records": [{"source_standard": "QIF", "canonical_concept": "Part"}], "replay_of": record["run_id"]})
    calls = []
    supervisor = ScheduledJobSupervisor(lambda definition, payload, correlation_id: calls.append((definition, payload, correlation_id)) or {"status": "completed"})
    supervisor.scan_once()
    assert len(calls) == 1
    assert calls[0][1]["replay_of"] == "seed-run"


def test_scheduler_skips_execution_when_another_worker_owns_the_job(monkeypatch):
    from contextlib import contextmanager

    class LockedRegistry(InMemoryRegistry):
        @contextmanager
        def advisory_lock(self, key):
            yield False

    definitions = LockedRegistry()
    monkeypatch.setattr("backend.data_pipeline_service.job_definitions.store", definitions)
    definitions.put("scheduled-quality:1.0.0", {
        "job_id": "scheduled-quality", "version": "1.0.0", "lifecycle_state": "approved", "enabled": True,
        "schedule": {"replay_run_id": "seed-run", "interval_seconds": 60},
    })
    calls = []
    ScheduledJobSupervisor(lambda *args: calls.append(args)).scan_once()
    assert calls == []


def test_completed_run_records_partition_and_gated_checkpoint_evidence(monkeypatch):
    from backend.data_pipeline_service import run_records

    monkeypatch.setattr(run_records, "store", InMemoryRegistry())
    definition = {
        "job_id": "checkpoint-quality", "version": "1.0.0", "job_type": "interactive-quality-summary",
        "input_contract": "quality-records-v1",
    }
    record = run_records.start(definition, {
        "records": [{"source_standard": "PLMXML", "canonical_concept": "Part"}],
        "source_system": "Teamcenter",
        "checkpoint": {"offset": 10}, "next_checkpoint": {"offset": 11},
    }, correlation_id="checkpoint-test")
    completed = run_records.complete(record, {
        "status": "completed", "quality": {"accepted_records": 1},
        "standard": "plmxml",
        "mapping": "sha256:" + "b" * 64,
        "validation": {"conforms": True},
        "partition_artifacts": {"accepted": "sha256:" + "a" * 64, "rejected": None},
    })
    output = completed["output_manifest"]
    assert completed["source_standard"] == "plmxml"
    assert completed["source_system"] == "Teamcenter"
    assert output["source_standard"] == "plmxml"
    assert output["source_system"] == "Teamcenter"
    assert output["mapping_digest"].startswith("sha256:")
    assert output["validation_status"] == "conforms"
    assert output["checkpoint_candidate"] == {"offset": 11}
    assert output["checkpoint_state"] == "awaiting_approved_publication"
    assert output["partition_artifacts"]["accepted"].startswith("sha256:")

    published = run_records.publication_succeeded(completed, {"status": "published", "ontology_id": "ceim-qif"})
    assert published["checkpoint"] == {"offset": 11}
    assert published["output_manifest"]["checkpoint_state"] == "advanced"
    assert published["output_manifest"]["publication_digest"].startswith("sha256:")
    assert run_records.publication_succeeded(published, {"status": "published"}) == published


def test_publish_run_uses_canonical_api_before_advancing_checkpoint(monkeypatch):
    import json
    import httpx
    from backend.artifact_store import ArtifactStore
    from backend.data_pipeline_service import run_records

    registry = InMemoryRegistry()
    monkeypatch.setattr(run_records, "store", registry)
    artifact = ArtifactStore().ingest_bytes(
        json.dumps({
            "representation": "normalized-ceim-v1", "ceim_version": "0.1.0", "standard": "qif",
            "entities": [], "relationships": [],
        }).encode(),
        filename="accepted.json", kind="accepted-semantic-partition", media_type="application/json",
    )
    registry.put("publish-run", {
        "run_id": "publish-run", "job_type": "validate-semantic-batch", "status": "completed",
        "checkpoint": {"offset": 1},
        "output_manifest": {
            "partition_artifacts": {"accepted": artifact["artifact_id"]},
            "checkpoint_candidate": {"offset": 2}, "checkpoint_state": "awaiting_approved_publication",
        },
    })

    class FakeClient:
        def __init__(self, *args, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def post(self, url, **kwargs):
            return httpx.Response(200, request=httpx.Request("POST", url), json={"status": "published", "ontology_id": "qif"})

    monkeypatch.setattr("backend.data_pipeline_service.router.httpx.AsyncClient", FakeClient)
    response = TestClient(app).post("/api/v1/pipeline/jobs/runs/publish-run/publish", json={
        "approved_by": "pipeline-steward", "semantic_release": {"asset_id": "ceim", "version": "0.1.0", "lifecycle_status": "approved"},
    })
    assert response.status_code == 200
    assert response.json()["checkpoint"] == {"offset": 2}
    assert response.json()["output_manifest"]["checkpoint_state"] == "advanced"
