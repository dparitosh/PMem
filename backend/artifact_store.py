"""Content-addressed artifact storage shared by producer services."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
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

    @staticmethod
    def _digest(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
        return digest.hexdigest()

    def ingest(self, source: Path, *, kind: str = "artifact", media_type: str = "application/octet-stream", provenance: dict[str, Any] | None = None) -> dict[str, Any]:
        if not source.is_file():
            raise ValueError("artifact source does not exist")
        digest = self._digest(source)
        artifact_id = f"sha256:{digest}"
        directory = self.root / "sha256" / digest
        target, metadata_path = directory / "content", directory / "metadata.json"
        if not target.exists():
            directory.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            metadata = {"artifact_id": artifact_id, "sha256": digest, "size": target.stat().st_size,
                        "filename": source.name, "kind": kind, "media_type": media_type,
                        "created_at": datetime.now(timezone.utc).isoformat(), "provenance": provenance or {}}
            metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
        return json.loads(metadata_path.read_text(encoding="utf-8"))

    def ingest_bytes(self, content: bytes, *, filename: str, kind: str = "artifact", media_type: str = "application/octet-stream", provenance: dict[str, Any] | None = None) -> dict[str, Any]:
        """Atomically retain a small control-plane payload as immutable content.

        Large sources must still use :meth:`ingest` to stream a file. This
        helper is for bounded JSON job inputs and manifests only.
        """
        digest = hashlib.sha256(content).hexdigest()
        artifact_id = f"sha256:{digest}"
        directory = self.root / "sha256" / digest
        target, metadata_path = directory / "content", directory / "metadata.json"
        if not target.exists():
            directory.mkdir(parents=True, exist_ok=True)
            temporary = directory / ".content.tmp"
            temporary.write_bytes(content)
            os.replace(temporary, target)
            metadata = {"artifact_id": artifact_id, "sha256": digest, "size": len(content),
                        "filename": filename, "kind": kind, "media_type": media_type,
                        "created_at": datetime.now(timezone.utc).isoformat(), "provenance": provenance or {}}
            metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
        return json.loads(metadata_path.read_text(encoding="utf-8"))

    def resolve(self, artifact_id: str) -> tuple[dict[str, Any], Path]:
        if not artifact_id.startswith("sha256:") or len(artifact_id) != 71:
            raise ValueError("artifact_id must be a sha256 content address")
        directory = self.root / "sha256" / artifact_id.split(":", 1)[1]
        metadata_path, content = directory / "metadata.json", directory / "content"
        if not metadata_path.is_file() or not content.is_file():
            raise ValueError("artifact_id was not found")
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        if self._digest(content) != artifact_id.split(":", 1)[1]:
            raise ValueError("artifact content no longer matches its immutable artifact_id")
        return metadata, content

    def purge(self, artifact_id: str) -> dict[str, Any]:
        """Delete one verified artifact; callers must retain external audit evidence."""
        metadata, content = self.resolve(artifact_id)
        directory = content.parent.resolve()
        expected = (self.root.resolve() / "sha256" / artifact_id.split(":", 1)[1]).resolve()
        if directory != expected:
            raise ValueError("artifact path is outside the content-addressed store")
        metadata_path = directory / "metadata.json"
        content.unlink()
        metadata_path.unlink()
        directory.rmdir()
        return {"artifact_id": artifact_id, "bytes_deleted": int(metadata.get("size") or 0)}


artifact_store = ArtifactStore()
