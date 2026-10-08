"""Content-addressed artifact storage shared by producer services."""
from __future__ import annotations

from backend.depo_platform.execution_guard import ensure_execution_allowed
import hashlib
import json
import os
import shutil
import uuid
import re
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class ArtifactStore:
    def __init__(self, root: Path | None = None) -> None:
        configured = os.getenv("ARTIFACT_STORAGE", "")
        if root is not None:
            self.root = root
        elif configured:
            self.root = Path(configured)
        else:
            self.root = Path(__file__).resolve().parents[1] / "data" / "artifacts"
        self.root.mkdir(parents=True, exist_ok=True)
        self.root = self.root.resolve()

    @staticmethod
    def _digest(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
        return digest.hexdigest()

    def _directory(self, digest: str, *, create: bool = False) -> Path:
        if not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ValueError("artifact_id must contain a lowercase SHA-256 digest")
        directory = self.root / "sha256" / digest
        if create:
            directory.mkdir(parents=True, exist_ok=True)
        if not directory.resolve().is_relative_to(self.root):
            raise ValueError("artifact path is outside the content-addressed store")
        return directory

    @contextmanager
    def _write_lock(self, directory: Path):
        directory.mkdir(parents=True, exist_ok=True)
        # OS locks are released if a process crashes; do not unlink the lock
        # file, because another process may already be waiting on its handle.
        with (directory / ".write-lock").open("a+b") as lock:
            if lock.seek(0, os.SEEK_END) == 0:
                lock.write(b"0")
                lock.flush()
            deadline = time.monotonic() + 30
            while True:
                try:
                    lock.seek(0)
                    if os.name == "nt":
                        import msvcrt
                        msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
                    else:
                        import fcntl
                        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except OSError:
                    if time.monotonic() >= deadline:
                        raise ValueError("Artifact write is busy; retry") from None
                    time.sleep(0.05)
            try:
                yield
            finally:
                lock.seek(0)
                if os.name == "nt":
                    msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(lock.fileno(), fcntl.LOCK_UN)

    def _retain(self, digest: str, writer, *, filename: str, kind: str, media_type: str,
                provenance: dict[str, Any] | None) -> dict[str, Any]:
        artifact_id = f"sha256:{digest}"
        directory = self._directory(digest, create=True)
        target, metadata_path = directory / "content", directory / "metadata.json"
        with self._write_lock(directory):
            # A previous interrupted write may have content but no metadata.
            # Serialize writers and repair that pair instead of returning a missing file.
            if target.exists() and metadata_path.exists():
                metadata, _ = self.resolve(artifact_id)
                return metadata
            temporary = directory / f".content.{uuid.uuid4().hex}.tmp"
            metadata_tmp = directory / f".metadata.{uuid.uuid4().hex}.tmp"
            try:
                writer(temporary)
                if self._digest(temporary) != digest:
                    raise ValueError("Artifact source changed during ingestion; retry with a stable source")
                metadata = {"artifact_id": artifact_id, "sha256": digest, "size": temporary.stat().st_size,
                            "filename": filename, "kind": kind, "media_type": media_type,
                            "created_at": datetime.now(timezone.utc).isoformat(), "provenance": provenance or {}}
                ensure_execution_allowed()
                metadata_tmp.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
                os.replace(temporary, target)
                os.replace(metadata_tmp, metadata_path)
                return metadata
            finally:
                temporary.unlink(missing_ok=True)
                metadata_tmp.unlink(missing_ok=True)

    def ingest(self, source: Path, *, kind: str = "artifact", media_type: str = "application/octet-stream", provenance: dict[str, Any] | None = None) -> dict[str, Any]:
        if not source.is_file():
            raise ValueError("artifact source does not exist")
        ensure_execution_allowed()
        return self._retain(self._digest(source), lambda temporary: shutil.copy2(source, temporary),
                            filename=source.name, kind=kind, media_type=media_type, provenance=provenance)

    def ingest_bytes(self, content: bytes, *, filename: str, kind: str = "artifact", media_type: str = "application/octet-stream", provenance: dict[str, Any] | None = None) -> dict[str, Any]:
        ensure_execution_allowed()
        return self._retain(hashlib.sha256(content).hexdigest(), lambda temporary: temporary.write_bytes(content),
                            filename=filename, kind=kind, media_type=media_type, provenance=provenance)

    def resolve(self, artifact_id: str) -> tuple[dict[str, Any], Path]:
        if not artifact_id.startswith("sha256:") or len(artifact_id) != 71:
            raise ValueError("artifact_id must be a sha256 content address")
        directory = self._directory(artifact_id.split(":", 1)[1])
        metadata_path, content = directory / "metadata.json", directory / "content"
        if not metadata_path.is_file() or not content.is_file():
            raise ValueError("artifact_id was not found")
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        if self._digest(content) != artifact_id.split(":", 1)[1]:
            raise ValueError("artifact content no longer matches its immutable artifact_id")
        if metadata.get("artifact_id") != artifact_id or metadata.get("sha256") != artifact_id.split(":", 1)[1]:
            raise ValueError("Artifact metadata does not match its content address")
        return metadata, content

    def purge(self, artifact_id: str, *, recovery_metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        """Delete one verified artifact; callers must retain external audit evidence."""
        if not artifact_id.startswith('sha256:'):
            raise ValueError('artifact_id must be a sha256 content address')
        directory = self._directory(artifact_id.split(':', 1)[1])
        with self._write_lock(directory):
            content, metadata_path = directory / 'content', directory / 'metadata.json'
            if content.is_file() and metadata_path.is_file():
                metadata, _ = self.resolve(artifact_id)
            elif recovery_metadata and recovery_metadata.get('artifact_id') == artifact_id:
                metadata = recovery_metadata
                if content.is_file() and self._digest(content) != artifact_id.split(':', 1)[1]:
                    raise ValueError('Artifact content does not match retained purge intent')
            else:
                raise ValueError('artifact_id was not found')
            ensure_execution_allowed()
            content.unlink(missing_ok=True)
            metadata_path.unlink(missing_ok=True)
            # Preserve the lock inode for concurrent writers and crash recovery.
            return {"artifact_id": artifact_id, "bytes_deleted": int(metadata.get("size") or 0)}


artifact_store = ArtifactStore()
