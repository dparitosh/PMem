"""
Durable workflow artifact storage.

Each workflow task gets a stable folder under uploads/workflow_artifacts/<task_id>/ by default.
Generated files are recorded in manifest.json so UI/API services can show what
was produced and downstream workflows can reuse outputs without relying on
in-memory task state.
"""

import json
import mimetypes
import os
import re
import hashlib
import threading
import uuid
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional


class WorkflowArtifactService:
    ARTIFACT_ROOT = Path(
        os.getenv("WORKFLOW_ARTIFACT_ROOT")
        or str(Path(__file__).parent.parent.parent / "uploads" / "workflow_artifacts")
    )
    _manifest_lock = threading.RLock()

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @classmethod
    def task_dir(cls, task_id: str) -> Path:
        raw_task = str(task_id or "").strip()
        if not raw_task:
            raise ValueError("task_id is required")
        safe_task = re.sub(r"[^a-zA-Z0-9_-]", "_", raw_task)
        if safe_task != raw_task:
            safe_task = f"{safe_task}_{hashlib.sha256(raw_task.encode('utf-8')).hexdigest()[:10]}"
        return cls.ARTIFACT_ROOT / safe_task

    @classmethod
    def manifest_path(cls, task_id: str) -> Path:
        return cls.task_dir(task_id) / "manifest.json"

    @classmethod
    def ensure_task(cls, task_id: str, workflow_id: str = "", filename: str = "") -> Path:
        with cls._manifest_lock:
            root = cls.task_dir(task_id)
            for folder in ("source", "preview", "ontology", "validation", "reports", "manifests"):
                (root / folder).mkdir(parents=True, exist_ok=True)

            manifest = cls.get_manifest(task_id) or {
                "task_id": task_id,
                "workflow_id": workflow_id,
                "source_filename": filename,
                "created_at": cls._now(),
                "updated_at": cls._now(),
                "artifacts": [],
            }
            if workflow_id and not manifest.get("workflow_id"):
                manifest["workflow_id"] = workflow_id
            if filename and not manifest.get("source_filename"):
                manifest["source_filename"] = filename
            cls._write_manifest(task_id, manifest)
            return root

    @classmethod
    def _write_manifest(cls, task_id: str, manifest: Dict[str, Any]) -> None:
        with cls._manifest_lock:
            path = cls.manifest_path(task_id)
            path.parent.mkdir(parents=True, exist_ok=True)
            manifest["updated_at"] = cls._now()
            temp_path = path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
            try:
                with open(temp_path, "w", encoding="utf-8") as handle:
                    json.dump(manifest, handle, indent=2, ensure_ascii=True, default=str)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temp_path, path)
            finally:
                if temp_path.exists():
                    temp_path.unlink(missing_ok=True)

    @classmethod
    def get_manifest(cls, task_id: str) -> Optional[Dict[str, Any]]:
        path = cls.manifest_path(task_id)
        if not path.exists():
            return None
        manifest = json.loads(path.read_text(encoding="utf-8"))
        for artifact in manifest.get("artifacts", []):
            artifact.pop("absolute_path", None)
        return manifest

    @classmethod
    def resolve_artifact_path(cls, task_id: str, artifact_path: str) -> Optional[Path]:
        manifest = cls.get_manifest(task_id)
        if not manifest:
            return None
        normalized = Path(artifact_path).as_posix().lstrip("/")
        if not any(a.get("path") == normalized for a in manifest.get("artifacts", [])):
            return None
        root = cls.task_dir(task_id).resolve()
        candidate = (root / normalized).resolve()
        if root != candidate and root not in candidate.parents:
            return None
        return candidate if candidate.exists() else None

    @classmethod
    def write_bytes(
        cls,
        task_id: str,
        category: str,
        filename: str,
        content: bytes,
        artifact_type: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        cls.ensure_task(task_id)
        safe_category = re.sub(r"[^a-zA-Z0-9_-]", "_", category or "reports")
        safe_name = re.sub(r"[^a-zA-Z0-9_.-]", "_", filename or "artifact.bin")
        rel_path = Path(safe_category) / safe_name
        abs_path = cls.task_dir(task_id) / rel_path
        abs_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = abs_path.with_name(f".{abs_path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
        try:
            temp_path.write_bytes(content)
            os.replace(temp_path, abs_path)
        finally:
            if temp_path.exists():
                temp_path.unlink(missing_ok=True)
        return cls._record(task_id, rel_path, artifact_type, metadata)

    @classmethod
    def copy_file(
        cls,
        task_id: str,
        category: str,
        filename: str,
        source_path: str | Path,
        artifact_type: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Stream a local file into durable artifact storage using atomic replacement."""
        cls.ensure_task(task_id)
        source = Path(source_path).resolve()
        if not source.is_file():
            raise FileNotFoundError(f"Artifact source file not found: {source}")
        safe_category = re.sub(r"[^a-zA-Z0-9_-]", "_", category or "source")
        safe_name = re.sub(r"[^a-zA-Z0-9_.-]", "_", filename or source.name or "artifact.bin")
        rel_path = Path(safe_category) / safe_name
        abs_path = cls.task_dir(task_id) / rel_path
        abs_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = abs_path.with_name(f".{abs_path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
        try:
            with source.open("rb") as input_handle, temp_path.open("wb") as output_handle:
                shutil.copyfileobj(input_handle, output_handle, length=1024 * 1024)
                output_handle.flush()
                os.fsync(output_handle.fileno())
            os.replace(temp_path, abs_path)
        finally:
            if temp_path.exists():
                temp_path.unlink(missing_ok=True)
        return cls._record(task_id, rel_path, artifact_type, metadata)

    @classmethod
    def write_text(
        cls,
        task_id: str,
        category: str,
        filename: str,
        content: str,
        artifact_type: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        return cls.write_bytes(
            task_id=task_id,
            category=category,
            filename=filename,
            content=(content or "").encode("utf-8"),
            artifact_type=artifact_type,
            metadata=metadata,
        )

    @classmethod
    def write_json(
        cls,
        task_id: str,
        category: str,
        filename: str,
        content: Any,
        artifact_type: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        return cls.write_text(
            task_id=task_id,
            category=category,
            filename=filename,
            content=json.dumps(content, indent=2, ensure_ascii=True, default=str),
            artifact_type=artifact_type,
            metadata=metadata,
        )

    @classmethod
    def _record(
        cls,
        task_id: str,
        rel_path: Path,
        artifact_type: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        abs_path = cls.task_dir(task_id) / rel_path
        with cls._manifest_lock:
            manifest = cls.get_manifest(task_id) or {
                "task_id": task_id,
                "created_at": cls._now(),
                "artifacts": [],
            }
            rel_posix = rel_path.as_posix()
            checksum = hashlib.sha256()
            if abs_path.is_file():
                with abs_path.open("rb") as handle:
                    for block in iter(lambda: handle.read(1024 * 1024), b""):
                        checksum.update(block)
            artifact = {
                "id": hashlib.sha256(f"{artifact_type}:{rel_posix}".encode("utf-8")).hexdigest()[:20],
                "type": artifact_type,
                "path": rel_posix,
                "size_bytes": abs_path.stat().st_size if abs_path.exists() else 0,
                "sha256": checksum.hexdigest() if abs_path.is_file() else "",
                "mime_type": mimetypes.guess_type(abs_path.name)[0] or "application/octet-stream",
                "created_at": cls._now(),
                "metadata": metadata or {},
            }
            artifacts = [a for a in manifest.get("artifacts", []) if a.get("path") != rel_posix]
            artifacts.append(artifact)
            manifest["artifacts"] = artifacts
            cls._write_manifest(task_id, manifest)
            return artifact
