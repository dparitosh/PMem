from __future__ import annotations

import threading
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.Services import document_job_service, document_processor, documents_api
from backend.Services.document_job_service import DocumentJobService
from backend.Services.workflow_artifact_service import WorkflowArtifactService


def test_semantic_proposals_extract_requirements_and_parameters() -> None:
    result = document_processor.extract_semantic_proposals(
        "REQ-101 The bearing shall operate at 3000 rpm. Temperature must remain below 85 °C.",
        "doc-1",
    )

    types = {entity["entity_type"] for entity in result["entities"]}
    assert types == {"Requirement", "Parameter"}
    assert result["requires_human_approval"] is True
    assert result["committed"] is False
    assert all(entity["mapping_proposal"]["status"] == "proposed" for entity in result["entities"])


def test_pdf_native_text_falls_back_to_optional_ocr(monkeypatch, tmp_path) -> None:
    sample = tmp_path / "scan.pdf"
    sample.write_bytes(b"pdf")

    class Page:
        def extract_text(self):
            return ""

    class Reader:
        def __init__(self, _path):
            self.pages = [Page()]

    monkeypatch.setattr(document_processor, "PdfReader", Reader)
    monkeypatch.setattr(document_processor, "_extract_pdf_ocr_text", lambda _path: "OCR requirement text")

    assert document_processor._extract_pdf_text(sample) == "OCR requirement text"


def test_document_job_writes_durable_result_and_proposal_artifacts(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(WorkflowArtifactService, "ARTIFACT_ROOT", tmp_path / "artifacts")
    monkeypatch.setenv("ARTIFACT_STORAGE", str(tmp_path / "content-addressed"))
    task_id = "document-job-1"
    WorkflowArtifactService.ensure_task(task_id, "document.unstructured")
    DocumentJobService._write_state(task_id, {
        "task_id": task_id,
        "status": "queued",
        "stage": "queued",
        "created_at": DocumentJobService._now(),
    })
    fake_result = {
        "summary": {"total_files": 1, "successfully_processed": 1, "failed_processing": 0},
        "processing_results": [{
            "status": "success",
            "semantic_proposals": {"entities": [{"entity_type": "Requirement"}]},
        }],
    }
    monkeypatch.setattr(document_job_service, "process_documents_batch", lambda *args, **kwargs: fake_result)

    DocumentJobService._run(task_id, [str(tmp_path / "retained.txt")], None, threading.Event())

    status = DocumentJobService.get_status(task_id)
    manifest = WorkflowArtifactService.get_manifest(task_id)
    assert status["status"] == "completed"
    paths = {artifact["path"] for artifact in manifest["artifacts"]}
    assert "reports/processing_result.json" in paths
    assert "reports/semantic_proposals.json" in paths
    assert "reports/unstructured_evidence.json" in paths
    assert "reports/unstructured_quality.json" in paths
    assert status["result"]["evidence_artifact_id"].startswith("sha256:")
    assert all(artifact["sha256"] for artifact in manifest["artifacts"])


def test_document_job_cancel_is_durable(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(WorkflowArtifactService, "ARTIFACT_ROOT", tmp_path / "artifacts")
    task_id = "document-job-cancel"
    WorkflowArtifactService.ensure_task(task_id, "document.unstructured")
    DocumentJobService._write_state(task_id, {
        "task_id": task_id,
        "status": "queued",
        "stage": "queued",
        "created_at": DocumentJobService._now(),
    })

    class Future:
        def cancel(self):
            return True

    monkeypatch.setitem(DocumentJobService._futures, task_id, Future())

    state = DocumentJobService.cancel(task_id)

    assert state["status"] == "cancelled"
    assert DocumentJobService._read_state(task_id)["cancel_requested"] is True


def test_document_job_api_retains_source_before_submission(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(WorkflowArtifactService, "ARTIFACT_ROOT", tmp_path / "artifacts")
    monkeypatch.setenv("ARTIFACT_STORAGE", str(tmp_path / "content-addressed"))
    monkeypatch.setattr(documents_api, "TEMP_UPLOAD_DIR", str(tmp_path / "temp"))
    monkeypatch.setattr(documents_api, "_require_document_processor", lambda: {"available": True})
    captured = {}

    def fake_submit(cls, retained_paths, source_artifacts, **kwargs):
        captured["retained_paths"] = retained_paths
        captured["source_artifacts"] = source_artifacts
        return {
            "task_id": kwargs["task_id"],
            "status": "queued",
            "stage": "queued",
            "progress": 0,
        }

    monkeypatch.setattr(DocumentJobService, "submit", classmethod(fake_submit))
    app = FastAPI()
    app.include_router(documents_api.router, prefix="/api/v1")

    response = TestClient(app).post(
        "/api/v1/documents/jobs",
        files={"files": ("requirements.txt", b"REQ-1 The bearing shall rotate.", "text/plain")},
    )

    assert response.status_code == 202
    retained = Path(captured["retained_paths"][0])
    assert retained.is_file()
    assert retained.read_bytes().startswith(b"REQ-1")
    assert captured["source_artifacts"][0]["sha256"]
    assert captured["source_artifacts"][0]["artifact_id"].startswith("sha256:")


def test_direct_document_indexing_routes_are_retired() -> None:
    app = FastAPI()
    app.include_router(documents_api.router, prefix="/api/v1")
    client = TestClient(app)

    response = client.post("/api/v1/documents/upload", files={"files": ("requirements.txt", b"REQ-1", "text/plain")})

    assert response.status_code == 410
    assert "retired" in response.json()["detail"]

