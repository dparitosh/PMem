"""Durable, staged workflow service for QIF schema-set ingestion."""
from __future__ import annotations

import json
import re
import shutil
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from fastapi import HTTPException

from backend.artifact_store import artifact_store
from backend.depo_platform.network import bounded_timeout_seconds, graph_dispatch_timeout_seconds
from backend.depo_platform.operations import OperationContext, operation_scope, remaining_seconds
from backend.depo_platform.execution_guard import ensure_execution_allowed, guarded_execution

from .preparation_worker import run_stage
from .ownership import task_root, state_lock, execution_owner, ensure_owner
from .publishing import get_publisher
from backend.depo_platform.graph_publication_transport import PublicationUnverified


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class QifTaskService:
    """Stores workflow state and artifacts under one task-owned folder."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = root or task_root(Path(__file__).resolve().parents[2] / "uploads" / "qif_workflows")
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="qif-worker")
        self._running: set[str] = set()
        from backend.depo_platform.qos import positive_capacity
        self._slots = threading.BoundedSemaphore(positive_capacity('QIF_MAX_PENDING_TASKS', 16))
        self._closing = threading.Event()

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
        ensure_owner()
        with self._lock, state_lock(task_id):
            path = self._manifest_path(task_id)
            # Cancellation is terminal: stale worker snapshots cannot resurrect it.
            if path.exists():
                current = json.loads(path.read_text(encoding="utf-8"))
                if current.get("status") == "cancelled":
                    return current
            temp = path.with_suffix(".tmp")
            temp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
            temp.replace(path)
            return data

    def _event(self, task: dict[str, Any], stage: str, message: str, level: str = "info") -> None:
        task.setdefault("events", []).append({"at": _now(), "stage": stage, "level": level, "message": message})

    def create(self, *, source_paths: list[Path], ontology_name: str, prefix: str, description: str, source: str, standard_id: str = "generic-xsd") -> dict[str, Any]:
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
            "standard_id": standard_id,
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
        self._event(task, "queued", f"Accepted {len(copied)} XSD source files for {standard_id}.")
        self._write(task_id, task)
        return task

    def list(self, limit: int = 25) -> list[dict[str, Any]]:
        manifests = sorted(self.root.glob("*/manifest.json"), key=lambda path: path.stat().st_mtime, reverse=True)
        return [self._read(path.parent.name) for path in manifests[:limit]]

    def get(self, task_id: str) -> dict[str, Any]:
        return self._read(task_id)

    def _update(self, task_id: str, **changes: Any) -> dict[str, Any]:
        with self._lock, state_lock(task_id):
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
            if self._closing.is_set() or not self._slots.acquire(blocking=False):
                raise HTTPException(status_code=503, detail="Schema-set worker is busy; retained task can be resumed later", headers={"Retry-After": "5"})
            self._running.add(task_id)
            try:
                task = self._read(task_id)
                field = 'preparation_deadline_at' if work == self.prepare else 'execution_deadline_at'
                if work == self.retry_graph_sync:
                    # Explicit receipt checks are new read operations, never new publications.
                    field = 'verification_deadline_at' if task.get('graph_sync', {}).get('status') in {'publishing', 'unverified'} else field
                if field not in task or field == 'verification_deadline_at':
                    budget = 10 if field == 'verification_deadline_at' else bounded_timeout_seconds(
                        'QIF_TASK_TIMEOUT_SECONDS', default=max(900, graph_dispatch_timeout_seconds() + 120), maximum=86400)
                    accepted = datetime.fromisoformat(task['created_at']) if field == 'preparation_deadline_at' else datetime.now(timezone.utc)
                    task[field] = (accepted + timedelta(seconds=budget)).isoformat()
                    self._write(task_id, task)
                deadline = task[field]
                admitted_state = (task.get("status"), task.get("stage"))
            except BaseException:
                self._running.discard(task_id)
                self._slots.release()
                raise

        def check():
            ensure_owner()
            remaining_seconds(deadline)
            if self._closing.is_set():
                raise RuntimeError('Schema-set service is stopping; no further workflow stages may start')
            if self._cancelled(task_id):
                raise RuntimeError('Schema-set task was cancelled')

        def wrapped() -> None:
            try:
                with execution_owner(task_id, self.root) as acquired:
                    if not acquired:
                        return
                    current = self._read(task_id)
                    if (current.get("status"), current.get("stage")) != admitted_state:
                        return  # Another replica already advanced this queued phase.
                    try:
                        with operation_scope(OperationContext(task_id, deadline)), guarded_execution(check):
                            work(task_id)
                    except Exception as exc:
                        # Persist terminal state while still owning the execution
                        # lock. Lost connections fail this check and leave intent
                        # for a new owner to reconcile, never a stale-worker write.
                        ensure_owner()
                        if not self._cancelled(task_id):
                            current = self._read(task_id)
                            uncertain = current.get('graph_sync', {}).get('status') in {'publishing', 'unverified'}
                            self._update(task_id, status='publication_unverified' if uncertain else 'failed',
                                         stage='recovery_review' if uncertain else 'failed', error=type(exc).__name__)
            except Exception:
                import logging
                logging.getLogger(__name__).exception('QIF execution ownership unavailable; retained task requires recovery')
            finally:
                with self._lock:
                    self._running.discard(task_id)
                self._slots.release()

        try:
            future = self._executor.submit(wrapped)
            def cancelled(pending):
                if pending.cancelled():
                    with self._lock:
                        self._running.discard(task_id)
                    self._slots.release()
            future.add_done_callback(cancelled)
        except BaseException:
            with self._lock:
                self._running.discard(task_id)
            self._slots.release()
            raise
        return True

    def shutdown(self):
        """Stop admission and cooperatively fence active work; retain queued manifests."""
        self._closing.set()
        self._executor.shutdown(wait=False, cancel_futures=True)

    def submit_prepare(self, task_id: str) -> bool:
        return self._submit(task_id, self.prepare)

    def submit_commit(self, task_id: str) -> bool:
        return self._submit(task_id, self.commit)

    def submit_graph_retry(self, task_id: str) -> bool:
        return self._submit(task_id, self.retry_graph_sync)

    def queue_commit(self, task_id: str) -> dict[str, Any]:
        """Atomically mark a reviewed task for publishing and enqueue it once."""
        with self._lock, state_lock(task_id):
            task = self._read(task_id)
            if task["status"] != "awaiting_approval":
                raise HTTPException(status_code=409, detail="QIF task is not ready for approval")
            budget = bounded_timeout_seconds('QIF_TASK_TIMEOUT_SECONDS', default=max(900, graph_dispatch_timeout_seconds() + 120), maximum=86400)
            task.setdefault('execution_deadline_at', (datetime.now(timezone.utc) + timedelta(seconds=budget)).isoformat())
            task.update({"status": "commit_queued", "stage": "register_queued", "progress": 82, "updated_at": _now()})
            self._event(task, "register", "Publishing approved ontology through the durable worker.")
            self._write(task_id, task)
            if not self.submit_commit(task_id):
                raise HTTPException(status_code=409, detail="QIF task is already being processed")
            return task

    def queue_graph_retry(self, task_id: str) -> dict[str, Any]:
        """Atomically enqueue one retry for a registered ontology with a failed graph sync."""
        with self._lock, state_lock(task_id):
            task = self._read(task_id)
            if task.get("graph_sync", {}).get("status") not in {"failed", "unverified", "publishing"} or not task.get("ontology_id"):
                raise HTTPException(status_code=409, detail="Graph synchronization is not eligible for retry")
            task.update({"status": "graph_retry_queued", "stage": "graph_sync_queued", "progress": 92, "updated_at": _now()})
            self._event(task, "graph_sync", "Graph synchronization retry queued.")
            self._write(task_id, task)
            if not self.submit_graph_retry(task_id):
                raise HTTPException(status_code=409, detail="Graph synchronization is already being retried")
            return task

    def pending(self):
        """Scan every retained manifest; completed history cannot hide pending work."""
        for path in sorted(self.root.glob("*/manifest.json")):
            task = self._read(path.parent.name)
            if task.get("status") in {"queued", "running", "commit_queued", "graph_retry_queued"}:
                yield task

    def recover_pending(self) -> dict[str, int]:
        """Resume interruptible preparation jobs after service startup."""
        recovered = 0
        attention = 0
        for task in self.pending():
            with execution_owner(task['task_id'], self.root) as acquired:
                if not acquired:
                    continue
                task = self._read(task['task_id'])
                if task['task_id'] in self._running:
                    continue
                if task.get("status") in {"queued", "running"} and task.get("stage") in {"queued", "inspect", "validate", "generate"}:
                    task["status"] = "queued"
                    task["stage"] = "queued"
                    self._event(task, "recovery", "Recovered after a service restart; resuming preparation.", "warning")
                    self._write(task["task_id"], task)
                    try:
                        self.submit_prepare(task["task_id"])
                    except HTTPException as exc:
                        if exc.status_code == 503:
                            break  # Leave the rest durable for the next recovery pass.
                        raise
                    recovered += 1
                elif task.get('status') in {'commit_queued', 'graph_retry_queued'} and task.get('stage') in {'register_queued', 'graph_sync_queued'}:
                    try:
                        if task['status'] == 'commit_queued':
                            self.submit_commit(task['task_id'])
                        else:
                            self.submit_graph_retry(task['task_id'])
                    except HTTPException as exc:
                        if exc.status_code == 503:
                            break
                        raise
                    recovered += 1
                elif task.get("status") in {"commit_queued", "running"} and task.get("stage") in {"register", "graph_sync"}:
                    task["status"] = "publication_unverified" if task.get("graph_sync", {}).get("status") == "publishing" else "requires_review"
                    task["stage"] = "recovery_review"
                    self._event(task, "recovery", "Service stopped during publishing. Review the task before retrying graph synchronization.", "warning")
                    self._write(task["task_id"], task)
                    attention += 1
        return {"recovered": recovered, "requires_review": attention}

    def cancel(self, task_id: str) -> dict[str, Any]:
        with self._lock, state_lock(task_id):
            task = self._read(task_id)
            if task.get('stage') == 'graph_sync' or task.get('graph_sync', {}).get('status') in {'publishing', 'unverified'}:
                raise HTTPException(status_code=409, detail='Publication may already be committing; verify its receipt instead of cancelling')
            if task["status"] in {"completed", "completed_with_warnings", "failed", "publication_unverified"}:
                raise HTTPException(status_code=409, detail="A completed or failed QIF task cannot be cancelled")
            task.update({"status": "cancelled", "stage": "cancelled", "updated_at": _now()})
            self._event(task, "cancelled", "Cancellation requested; no additional workflow stages will run.", "warning")
            return self._write(task_id, task)

    def prepare(self, task_id: str) -> None:
        """Run inspect → validate → generate, leaving an approval gate before persistence."""
        try:
            with self._lock:
                if self._cancelled(task_id):
                    return
                ensure_execution_allowed()
                task = self._update(task_id, status="running", stage="inspect", progress=10)
            task["agent"] = "SchemaSet_Ontology"
            self._event(task, "inspect", "Schema-set ontology agent is inspecting XSD declarations and documentation.")
            self._write(task_id, task)
            paths = [self._task_dir(task_id) / "source" / name for name in task["source_files"]]
            ensure_execution_allowed()
            inspection = run_stage("inspect", paths=paths)
            ensure_execution_allowed()
            if self._cancelled(task_id):
                return

            task = self._update(task_id, stage="validate", progress=35)
            self._event(task, "validate", "Resolving schema-set references and quality checks.")
            ensure_execution_allowed()
            validation = run_stage("validate", inspection=inspection, paths=paths)
            ensure_execution_allowed()
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
            ensure_execution_allowed()
            artifact, summary = run_stage("generate", inspection=inspection, prefix=task["prefix"])
            ensure_execution_allowed()
            artifact_dir = self._task_dir(task_id) / "ontology"
            artifact_dir.mkdir(exist_ok=True)
            artifact_path = artifact_dir / f"{task['prefix']}_qif_ontology.ttl"
            artifact_path.write_bytes(artifact)
            shared_artifact = artifact_store.ingest(
                artifact_path, kind="ontology", media_type="text/turtle",
                provenance={"qif_task_id": task_id, "prefix": task["prefix"]},
            )
            report_dir = self._task_dir(task_id) / "reports"
            report_dir.mkdir(exist_ok=True)
            report_path = report_dir / "validation.json"
            report_path.write_text(json.dumps(validation, indent=2), encoding="utf-8")
            task = self._update(task_id, status="awaiting_approval", stage="review", progress=80, summary=summary,
                artifacts=[
                    {"name": artifact_path.name, "path": "ontology/" + artifact_path.name, "kind": "ontology", "artifact_id": shared_artifact["artifact_id"]},
                    {"name": report_path.name, "path": "reports/validation.json", "kind": "validation"},
                ])
            self._event(task, "review", "Preview is ready. Approve persistence to register the ontology and synchronize the graph.")
            self._write(task_id, task)
        except Exception as exc:
            if self._cancelled(task_id):
                return
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
            ensure_execution_allowed()
            saved = get_publisher().register(
                artifact=artifact, ontology_name=task["ontology_name"],
                prefix=task["prefix"], description=task["description"],
            )
            if saved.get("status") != "success":
                raise RuntimeError(saved.get("error", "Unable to register ontology"))
            ontology_id = saved["ontology_id"]
            self._update(task_id, ontology_id=ontology_id)
            ensure_execution_allowed()
            # Sources remain in this service-owned task and are available through
            # its artifact API; a peer filesystem path is never writable here.
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
        verify_only = task.get("graph_sync", {}).get("status") in {"unverified", "publishing"}
        try:
            artifact = self._task_dir(task_id) / "ontology" / f"{task['prefix']}_qif_ontology.ttl"
            if not verify_only:
                # Persist intent before dispatch: process loss must never turn into a blind replay.
                self._update(task_id, graph_sync={"status": "publishing", "attempts": attempts})
            publisher = get_publisher()
            ensure_execution_allowed()
            sync_result = (publisher.verify_graph if verify_only else publisher.sync_graph)(ontology_id=ontology_id, artifact=artifact)
            success = sync_result.get("status") == "success"
            graph_sync = {**task.get("graph_sync", {}), "status": "completed" if success else ("unverified" if verify_only else "failed"), "attempts": attempts, "detail": sync_result}
        except PublicationUnverified as exc:
            success = False
            graph_sync = {"status": "unverified", "attempts": attempts,
                          "publication_id": exc.publication_id, "receipt_url": exc.receipt_url,
                          "detail": "Commit outcome unverified. Verify the receipt; no write was retried."}
        except Exception as exc:
            success = False
            graph_sync = {**task.get("graph_sync", {}), "status": "unverified" if verify_only else "failed",
                          "attempts": attempts, "detail": f"{type(exc).__name__}: {exc}"}
        status = "completed" if success else ("publication_unverified" if graph_sync["status"] == "unverified" else "completed_with_warnings")
        task = self._update(task_id, status=status, stage="completed", progress=100, graph_sync=graph_sync)
        self._event(task, "completed", "Ontology registration and graph synchronization completed." if success else ("Ontology registered; publication outcome unverified. Check the receipt before retrying." if graph_sync["status"] == "unverified" else "Ontology registered; graph synchronization failed and can be retried."), "info" if success else "warning")
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
