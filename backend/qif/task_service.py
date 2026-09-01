"""Durable, staged workflow service for QIF schema-set ingestion."""
from __future__ import annotations

import json
import re
import shutil
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import HTTPException

from .agent_registry import registry
from .ontology_builder import build_ontology_turtle, inspect_schema_set, validate_schema_set


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class QifTaskService:
    """Stores workflow state and artifacts under one task-owned folder."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = root or Path(__file__).resolve().parents[2] / "uploads" / "qif_workflows"
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="qif-worker")
        self._running: set[str] = set()

    def _task_dir(self, task_id: str) -> Path:
        if not re.fullmatch(r"[a-f0-9]{32}", task_id or ""):
            raise HTTPException(status_code=404, detail="QIF task not found")
        return self.root / task_id

    def _manifest_path(self, task_id: str) -> Path:
        return self._task_dir(task_id) / "manifest.json"

    def _read(self, task_id: str) -> dict[str, Any]:
        path = self._manifest_path(task_id)
        if not path.exists():
            raise HTTPException(status_code=404, detail="QIF task not found")
        return json.loads(path.read_text(encoding="utf-8"))

    def _write(self, task_id: str, data: dict[str, Any]) -> dict[str, Any]:
        path = self._manifest_path(task_id)
        temp = path.with_suffix(".tmp")
        temp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        temp.replace(path)
        return data

    def _event(self, task: dict[str, Any], stage: str, message: str, level: str = "info") -> None:
        task.setdefault("events", []).append({"at": _now(), "stage": stage, "level": level, "message": message})

    def create(self, *, source_paths: list[Path], ontology_name: str, prefix: str, description: str, source: str) -> dict[str, Any]:
        task_id = uuid.uuid4().hex
        task_dir = self._task_dir(task_id)
        source_dir = task_dir / "source"
        source_dir.mkdir(parents=True)
        copied: list[str] = []
        for path in source_paths:
            target = source_dir / path.name
            shutil.copy2(path, target)
            copied.append(path.name)
        task = {
            "task_id": task_id,
            "source": source,
            "ontology_name": ontology_name,
            "prefix": prefix,
            "description": description,
            "status": "queued",
            "stage": "queued",
            "progress": 0,
            "created_at": _now(),
            "updated_at": _now(),
            "source_files": copied,
            "events": [],
            "validation": None,
            "summary": None,
            "artifacts": [],
            "graph_sync": {"status": "not_started"},
        }
        self._event(task, "queued", f"Accepted {len(copied)} XSD source files.")
        self._write(task_id, task)
        return task

    def list(self, limit: int = 25) -> list[dict[str, Any]]:
        manifests = sorted(self.root.glob("*/manifest.json"), key=lambda path: path.stat().st_mtime, reverse=True)
        return [self._read(path.parent.name) for path in manifests[:limit]]

    def get(self, task_id: str) -> dict[str, Any]:
        return self._read(task_id)

    def _update(self, task_id: str, **changes: Any) -> dict[str, Any]:
        with self._lock:
            task = self._read(task_id)
            task.update(changes)
            task["updated_at"] = _now()
            return self._write(task_id, task)

    def _cancelled(self, task_id: str) -> bool:
        return self._read(task_id).get("status") == "cancelled"

    def _submit(self, task_id: str, work) -> bool:
        with self._lock:
            if task_id in self._running:
                return False
            self._running.add(task_id)

        def wrapped() -> None:
            try:
                work(task_id)
            finally:
                with self._lock:
                    self._running.discard(task_id)

        self._executor.submit(wrapped)
        return True

    def submit_prepare(self, task_id: str) -> bool:
        return self._submit(task_id, self.prepare)

    def submit_commit(self, task_id: str) -> bool:
        return self._submit(task_id, self.commit)

    def submit_graph_retry(self, task_id: str) -> bool:
        return self._submit(task_id, self.retry_graph_sync)

    def queue_commit(self, task_id: str) -> dict[str, Any]:
        """Atomically mark a reviewed task for publishing and enqueue it once."""
        with self._lock:
            task = self._read(task_id)
            if task["status"] != "awaiting_approval":
                raise HTTPException(status_code=409, detail="QIF task is not ready for approval")
            task.update({"status": "commit_queued", "stage": "register_queued", "progress": 82, "updated_at": _now()})
            self._event(task, "register", "Publishing approved ontology through the durable worker.")
            self._write(task_id, task)
            if not self.submit_commit(task_id):
                raise HTTPException(status_code=409, detail="QIF task is already being processed")
            return task

    def queue_graph_retry(self, task_id: str) -> dict[str, Any]:
        """Atomically enqueue one retry for a registered ontology with a failed graph sync."""
        with self._lock:
            task = self._read(task_id)
            if task.get("graph_sync", {}).get("status") != "failed" or not task.get("ontology_id"):
                raise HTTPException(status_code=409, detail="Graph synchronization is not eligible for retry")
            task.update({"status": "graph_retry_queued", "stage": "graph_sync_queued", "progress": 92, "updated_at": _now()})
            self._event(task, "graph_sync", "Graph synchronization retry queued.")
            self._write(task_id, task)
            if not self.submit_graph_retry(task_id):
                raise HTTPException(status_code=409, detail="Graph synchronization is already being retried")
            return task

    def recover_pending(self) -> dict[str, int]:
        """Resume interruptible preparation jobs after service startup."""
        recovered = 0
        attention = 0
        for task in self.list(limit=1000):
            if task.get("status") in {"queued", "running"} and task.get("stage") in {"queued", "inspect", "validate", "generate"}:
                task["status"] = "queued"
                task["stage"] = "queued"
                self._event(task, "recovery", "Recovered after a service restart; resuming preparation.", "warning")
                self._write(task["task_id"], task)
                self.submit_prepare(task["task_id"])
                recovered += 1
            elif task.get("status") in {"commit_queued", "running"} and task.get("stage") in {"register", "graph_sync"}:
                task["status"] = "requires_review"
                task["stage"] = "recovery_review"
                self._event(task, "recovery", "Service stopped during publishing. Review the task before retrying graph synchronization.", "warning")
                self._write(task["task_id"], task)
                attention += 1
        return {"recovered": recovered, "requires_review": attention}

    def cancel(self, task_id: str) -> dict[str, Any]:
        task = self._read(task_id)
        if task["status"] in {"completed", "completed_with_warnings", "failed"}:
            raise HTTPException(status_code=409, detail="A completed or failed QIF task cannot be cancelled")
        task.update({"status": "cancelled", "stage": "cancelled", "updated_at": _now()})
        self._event(task, "cancelled", "Cancellation requested; no additional workflow stages will run.", "warning")
        return self._write(task_id, task)

    def prepare(self, task_id: str) -> None:
        """Run inspect → validate → generate, leaving an approval gate before persistence."""
        try:
            task = self._update(task_id, status="running", stage="inspect", progress=10)
            task["agent"] = "QIF_Ontology"
            self._event(task, "inspect", "QIF_Ontology agent is inspecting XSD declarations and documentation.")
            self._write(task_id, task)
            paths = [self._task_dir(task_id) / "source" / name for name in task["source_files"]]
            tools = registry.resolve_tools("QIF_Ontology")
            inspection = tools["inspect_schema_set"](paths)
            if self._cancelled(task_id):
                return

            task = self._update(task_id, stage="validate", progress=35)
            self._event(task, "validate", "Resolving schema-set references and quality checks.")
            validation = validate_schema_set(inspection, paths)
            task["validation"] = validation
            self._write(task_id, task)
            if validation["errors"]:
                task = self._update(task_id, status="failed", stage="validation_failed", progress=100)
                self._event(task, "validate", "Validation failed; correct the reported schema-set errors before retrying.", "error")
                self._write(task_id, task)
                return
            if self._cancelled(task_id):
                return

            task = self._update(task_id, stage="generate", progress=60)
            self._event(task, "generate", "Generating a traceable ontology preview.")
            artifact, summary = tools["build_ontology_turtle"](inspection, task["prefix"])
            artifact_dir = self._task_dir(task_id) / "ontology"
            artifact_dir.mkdir(exist_ok=True)
            artifact_path = artifact_dir / f"{task['prefix']}_qif_ontology.ttl"
            artifact_path.write_bytes(artifact)
            report_dir = self._task_dir(task_id) / "reports"
            report_dir.mkdir(exist_ok=True)
            report_path = report_dir / "validation.json"
            report_path.write_text(json.dumps(validation, indent=2), encoding="utf-8")
            task = self._update(task_id, status="awaiting_approval", stage="review", progress=80, summary=summary,
                artifacts=[
                    {"name": artifact_path.name, "path": "ontology/" + artifact_path.name, "kind": "ontology"},
                    {"name": report_path.name, "path": "reports/validation.json", "kind": "validation"},
                ])
            self._event(task, "review", "Preview is ready. Approve persistence to register the ontology and synchronize the graph.")
            self._write(task_id, task)
        except Exception as exc:
            task = self._update(task_id, status="failed", stage="failed", progress=100)
            self._event(task, "failed", f"Workflow failed: {type(exc).__name__}: {exc}", "error")
            self._write(task_id, task)

    def commit(self, task_id: str) -> None:
        """Register a reviewed ontology and capture final graph persistence status."""
        try:
            task = self._read(task_id)
            if task["status"] not in {"awaiting_approval", "commit_queued"}:
                raise HTTPException(status_code=409, detail="Only a reviewed QIF task can be committed")
            task = self._update(task_id, status="running", stage="register", progress=85)
            self._event(task, "register", "Registering ontology artifact.")
            self._write(task_id, task)
            artifact = self._task_dir(task_id) / "ontology" / f"{task['prefix']}_qif_ontology.ttl"
            try:
                from ..Services.ontology_upload_manager import OntologyUploadManager
            except ImportError:
                from Services.ontology_upload_manager import OntologyUploadManager
            saved = OntologyUploadManager.save_ontology_file(
                file_content=artifact.read_bytes(), filename=artifact.name,
                ontology_name=task["ontology_name"], prefix=task["prefix"], file_type="ontology",
                generation_type="as_is", description=task["description"], schema_type="schema",
            )
            if saved.get("status") != "success":
                raise RuntimeError(saved.get("error", "Unable to register ontology"))
            ontology_id = saved["ontology_id"]
            registered_source = Path(saved["storage_path"]).parent / "qif_sources"
            shutil.copytree(self._task_dir(task_id) / "source", registered_source, dirs_exist_ok=True)
            task = self._update(task_id, stage="graph_sync", progress=92, ontology_id=ontology_id)
            self._event(task, "graph_sync", "Synchronizing registered ontology with the graph.")
            self._write(task_id, task)
            self._sync_graph(task_id)
        except HTTPException:
            raise
        except Exception as exc:
            task = self._update(task_id, status="failed", stage="failed", progress=100)
            self._event(task, "failed", f"Commit failed: {type(exc).__name__}: {exc}", "error")
            self._write(task_id, task)

    def _sync_graph(self, task_id: str) -> None:
        task = self._read(task_id)
        ontology_id = task.get("ontology_id")
        if not ontology_id:
            raise RuntimeError("Cannot synchronize a task without a registered ontology")
        attempts = int(task.get("graph_sync", {}).get("attempts", 0)) + 1
        try:
            try:
                from ..Services.ontology_upload_manager import OntologyUploadManager
                from ..core.graph import graph
            except ImportError:
                from Services.ontology_upload_manager import OntologyUploadManager
                from core.graph import graph
            sync_result = OntologyUploadManager.push_to_neo4j(ontology_id, graph)
            success = sync_result.get("status") == "success"
            graph_sync = {"status": "completed" if success else "failed", "attempts": attempts, "detail": sync_result}
        except Exception as exc:
            success = False
            graph_sync = {"status": "failed", "attempts": attempts, "detail": f"{type(exc).__name__}: {exc}"}
        status = "completed" if success else "completed_with_warnings"
        task = self._update(task_id, status=status, stage="completed", progress=100, graph_sync=graph_sync)
        self._event(task, "completed", "Ontology registration and graph synchronization completed." if success else "Ontology registered; graph synchronization failed and can be retried.", "info" if success else "warning")
        self._write(task_id, task)

    def retry_graph_sync(self, task_id: str) -> None:
        task = self._read(task_id)
        if not task.get("ontology_id"):
            raise HTTPException(status_code=409, detail="No registered ontology is available for graph synchronization")
        task = self._update(task_id, status="running", stage="graph_sync", progress=92)
        self._event(task, "graph_sync", "Retrying graph synchronization.")
        self._write(task_id, task)
        self._sync_graph(task_id)

    def preview(self, task_id: str) -> dict[str, Any]:
        task = self._read(task_id)
        return {
            "task_id": task_id,
            "status": task["status"],
            "validation": task.get("validation"),
            "summary": task.get("summary"),
            "artifacts": task.get("artifacts", []),
            "events": task.get("events", []),
        }


task_service = QifTaskService()
