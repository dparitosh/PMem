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
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional


class WorkflowArtifactService:
    ARTIFACT_ROOT = Path(
        os.getenv("WORKFLOW_ARTIFACT_ROOT")
        or str(Path(__file__).parent.parent.parent / "uploads" / "workflow_artifacts")
    )

    @classmethod
    def task_dir(cls, task_id: str) -> Path:
        safe_task = re.sub(r"[^a-zA-Z0-9_-]", "_", str(task_id))
        return cls.ARTIFACT_ROOT / safe_task

    @classmethod
    def manifest_path(cls, task_id: str) -> Path:
        return cls.task_dir(task_id) / "manifest.json"

    @classmethod
    def ensure_task(cls, task_id: str, workflow_id: str = "", filename: str = "") -> Path:
        root = cls.task_dir(task_id)
        for folder in ("source", "preview", "ontology", "validation", "reports", "manifests"):
            (root / folder).mkdir(parents=True, exist_ok=True)

        manifest = cls.get_manifest(task_id) or {
            "task_id": task_id,
            "workflow_id": workflow_id,
            "source_filename": filename,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
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
        path = cls.manifest_path(task_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        manifest["updated_at"] = datetime.now().isoformat()
        path.write_text(json.dumps(manifest, indent=2, ensure_ascii=True, default=str), encoding="utf-8")

    @classmethod
    def get_manifest(cls, task_id: str) -> Optional[Dict[str, Any]]:
        path = cls.manifest_path(task_id)
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

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
        abs_path.write_bytes(content)
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
        manifest = cls.get_manifest(task_id) or {
            "task_id": task_id,
            "created_at": datetime.now().isoformat(),
            "artifacts": [],
        }
        rel_posix = rel_path.as_posix()
        artifact = {
            "id": re.sub(r"[^a-zA-Z0-9_-]", "_", f"{artifact_type}_{rel_path.stem}"),
            "type": artifact_type,
            "path": rel_posix,
            "absolute_path": str(abs_path),
            "size_bytes": abs_path.stat().st_size if abs_path.exists() else 0,
            "mime_type": mimetypes.guess_type(abs_path.name)[0] or "application/octet-stream",
            "created_at": datetime.now().isoformat(),
            "metadata": metadata or {},
        }
        artifacts = [a for a in manifest.get("artifacts", []) if a.get("path") != rel_posix]
        artifacts.append(artifact)
        manifest["artifacts"] = artifacts
        cls._write_manifest(task_id, manifest)
        return artifact
