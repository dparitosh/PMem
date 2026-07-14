"""Durable background jobs for retained unstructured-document processing."""

from __future__ import annotations

import json
import os
import threading
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .document_processor import DocumentProcessingCancelled, process_documents_batch
from .workflow_artifact_service import WorkflowArtifactService


def _worker_count() -> int:
    try:
        return max(1, min(16, int(os.getenv("DOCUMENT_JOB_WORKERS", "2"))))
    except (TypeError, ValueError):
        return 2


class DocumentJobService:
    _executor = ThreadPoolExecutor(
        max_workers=_worker_count(),
        thread_name_prefix="document-job",
    )
    _lock = threading.RLock()
    _futures: dict[str, Future] = {}
    _cancel_events: dict[str, threading.Event] = {}
    _terminal = {"completed", "partial", "failed", "cancelled"}

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @classmethod
    def _state_path(cls, task_id: str) -> Path:
        return WorkflowArtifactService.task_dir(task_id) / "manifests" / "document_job.json"

    @classmethod
    def _read_state(cls, task_id: str) -> dict[str, Any] | None:
        path = cls._state_path(task_id)
        if not path.is_file():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            return payload if isinstance(payload, dict) else None
        except (OSError, json.JSONDecodeError):
            return None

    @classmethod
    def _write_state(cls, task_id: str, state: dict[str, Any]) -> dict[str, Any]:
        state = dict(state)
        state["updated_at"] = cls._now()
        WorkflowArtifactService.write_json(
            task_id,
            "manifests",
            "document_job.json",
            state,
            "document_job_state",
        )
        return state

    @classmethod
    def _update_state(cls, task_id: str, **updates: Any) -> dict[str, Any]:
        with cls._lock:
            state = cls._read_state(task_id) or {"task_id": task_id, "created_at": cls._now()}
            state.update(updates)
            return cls._write_state(task_id, state)

    @classmethod
    def submit(
        cls,
        retained_paths: list[str],
        source_artifacts: list[dict[str, Any]],
        *,
        task_id: str | None = None,
        index_name: str | None = None,
    ) -> dict[str, Any]:
        if not retained_paths:
            raise ValueError("At least one retained document is required")
        task_id = str(task_id or uuid.uuid4())
        WorkflowArtifactService.ensure_task(task_id, workflow_id="document.unstructured")
        event = threading.Event()
        with cls._lock:
            state = cls._write_state(task_id, {
                "task_id": task_id,
                "workflow_id": "document.unstructured",
                "status": "queued",
                "stage": "queued",
                "progress": 0,
                "cancel_requested": False,
                "created_at": cls._now(),
                "worker_pid": os.getpid(),
                "source_artifacts": source_artifacts,
                "result": None,
                "error": "",
            })
            cls._cancel_events[task_id] = event
            cls._futures[task_id] = cls._executor.submit(
                cls._run,
                task_id,
                retained_paths,
                index_name,
                event,
            )
        return state

    @classmethod
    def _cancel_requested(cls, task_id: str, event: threading.Event) -> bool:
        if event.is_set():
            return True
        state = cls._read_state(task_id) or {}
        return bool(state.get("cancel_requested"))

    @staticmethod
    def _pid_alive(pid: int) -> bool:
        if pid <= 0:
            return False
        try:
            os.kill(pid, 0)
            return True
        except (OSError, ValueError):
            return False

    @classmethod
    def _run(
        cls,
        task_id: str,
        retained_paths: list[str],
        index_name: str | None,
        event: threading.Event,
    ) -> None:
        try:
            cls._update_state(
                task_id,
                status="processing",
                stage="extract",
                progress=10,
                started_at=cls._now(),
                worker_pid=os.getpid(),
            )

            stage_progress = {"extract": 20, "embed": 45, "index": 75, "file_complete": 85}

            def progress(stage: str, detail: dict[str, Any]) -> None:
                cls._update_state(
                    task_id,
                    stage=stage,
                    progress=stage_progress.get(stage, 10),
                    stage_detail=detail,
                )

            result = process_documents_batch(
                retained_paths,
                index_name=index_name,
                cancel_check=lambda: cls._cancel_requested(task_id, event),
                progress_callback=progress,
                include_semantic_proposals=True,
            )
            if cls._cancel_requested(task_id, event):
                raise DocumentProcessingCancelled("Document processing was cancelled")

            WorkflowArtifactService.write_json(
                task_id,
                "reports",
                "processing_result.json",
                result,
                "document_processing_result",
            )
            proposals = [
                item.get("semantic_proposals")
                for item in result.get("processing_results", [])
                if item.get("semantic_proposals")
            ]
            WorkflowArtifactService.write_json(
                task_id,
                "reports",
                "semantic_proposals.json",
                {"documents": proposals, "requires_human_approval": True, "committed": False},
                "document_semantic_proposals",
            )
            summary = result.get("summary") or {}
            succeeded = int(summary.get("successfully_processed") or 0)
            failed = int(summary.get("failed_processing") or 0)
            status = "completed" if failed == 0 else ("failed" if succeeded == 0 else "partial")
            public_results = []
            for item in result.get("processing_results", []):
                public_item = {key: value for key, value in item.items() if key != "semantic_proposals"}
                semantic = item.get("semantic_proposals") or {}
                public_item["semantic_proposal_count"] = int(semantic.get("entity_count") or 0)
                public_results.append(public_item)
            cls._update_state(
                task_id,
                status=status,
                stage="complete",
                progress=100,
                completed_at=cls._now(),
                result={"summary": summary, "processing_results": public_results},
                error="",
            )
        except DocumentProcessingCancelled as exc:
            cls._update_state(
                task_id,
                status="cancelled",
                stage="cancelled",
                progress=0,
                completed_at=cls._now(),
                error=str(exc),
            )
        except Exception as exc:
            cls._update_state(
                task_id,
                status="failed",
                stage="failed",
                progress=0,
                completed_at=cls._now(),
                error=str(exc),
            )

    @classmethod
    def get_status(cls, task_id: str) -> dict[str, Any] | None:
        state = cls._read_state(task_id)
        if not state:
            return None
        if state.get("status") in {"queued", "processing"}:
            worker_pid = int(state.get("worker_pid") or 0)
            with cls._lock:
                local_future = cls._futures.get(task_id)
            worker_missing = worker_pid == os.getpid() and local_future is None
            worker_stopped = worker_pid != os.getpid() and not cls._pid_alive(worker_pid)
            if worker_missing or worker_stopped:
                state = cls._update_state(
                    task_id,
                    status="failed",
                    stage="interrupted",
                    progress=0,
                    error="Document job was interrupted before completion",
                    completed_at=cls._now(),
                )
        return state

    @classmethod
    def cancel(cls, task_id: str) -> dict[str, Any] | None:
        with cls._lock:
            state = cls._read_state(task_id)
            if not state:
                return None
            if state.get("status") in cls._terminal:
                return state
            event = cls._cancel_events.setdefault(task_id, threading.Event())
            event.set()
            state = cls._update_state(task_id, cancel_requested=True, stage="cancelling")
            future = cls._futures.get(task_id)
            if future is not None and future.cancel():
                state = cls._update_state(
                    task_id,
                    status="cancelled",
                    stage="cancelled",
                    progress=0,
                    completed_at=cls._now(),
                    error="Document processing was cancelled before execution",
                )
            return state
