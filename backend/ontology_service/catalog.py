"""Durable ontology artifact catalog owned by the ontology service.

This deliberately does not import the legacy upload manager.  It is the
replacement persistence boundary for newly published ontology artifacts.
"""
from __future__ import annotations

import json
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.artifact_store import artifact_store


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_token(value: str, *, field: str) -> str:
    token = str(value or "").strip()
    if not token or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,63}", token):
        raise ValueError(f"{field} must start with a letter and contain only letters, numbers, _ or -")
    return token


class OntologyCatalog:
    def __init__(self, root: Path | None = None) -> None:
        configured = os.getenv("ONTOLOGY_SERVICE_STORAGE")
        self.root = root or (Path(configured) if configured else Path(__file__).resolve().parents[2] / "data" / "ontology_service")
        self.root.mkdir(parents=True, exist_ok=True)

    def register(self, *, content: bytes, filename: str, ontology_name: str, prefix: str, description: str = "", source: str = "api", extra_metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        if not content:
            raise ValueError("An ontology artifact is required")
        prefix = _safe_token(prefix, field="prefix")
        safe_filename = Path(filename or "ontology.ttl").name
        if not safe_filename or safe_filename in {".", ".."}:
            raise ValueError("A valid artifact filename is required")
        ontology_id = f"{prefix.lower()}_{uuid.uuid4().hex[:16]}"
        artifact_dir = self.root / ontology_id
        artifact_dir.mkdir(parents=True, exist_ok=False)
        artifact_path = artifact_dir / safe_filename
        artifact_path.write_bytes(content)
        shared_artifact = artifact_store.ingest(
            artifact_path,
            kind="ontology",
            media_type="text/turtle" if artifact_path.suffix.lower() == ".ttl" else "application/octet-stream",
            provenance={"ontology_id": ontology_id, "source": source},
        )
        metadata = {
            "ontology_id": ontology_id,
            "ontology_name": str(ontology_name or prefix),
            "prefix": prefix,
            "description": str(description or ""),
            "source": source,
            "original_filename": safe_filename,
            "artifact_path": str(artifact_path),
            "artifact_id": shared_artifact["artifact_id"],
            "created_at": _now(),
            "status": "registered",
        }
        metadata.update(extra_metadata or {})
        (artifact_dir / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
        return metadata

    def adopt_legacy(
        self,
        *,
        ontology_id: str,
        content: bytes,
        filename: str,
        ontology_name: str,
        prefix: str,
        description: str = "",
        extra_metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Adopt a legacy-ingestion artifact without changing its stable ID.

        The operation is additive and idempotent: the original ingestion
        record remains available for rollback while the native catalog becomes
        the canonical discovery boundary.
        """
        stable_id = _safe_token(ontology_id, field="ontology_id")
        existing = self.get(stable_id)
        if not content:
            raise ValueError("A legacy ontology artifact is required")
        normalized_prefix = _safe_token(prefix, field="prefix")
        safe_filename = Path(filename or "ontology.artifact").name
        if existing is not None:
            # Early migrations did not preserve the original suffix.  Repair
            # that metadata idempotently so catalog consumers can negotiate
            # the correct artifact media type.
            if existing.get("source") != "legacy_ingestion_migration" or existing.get("original_filename") == safe_filename:
                return existing
            artifact_dir = self.root / stable_id
            artifact_path = artifact_dir / safe_filename
            artifact_path.write_bytes(content)
            shared_artifact = artifact_store.ingest(
                artifact_path,
                kind="ontology",
                media_type="text/turtle" if artifact_path.suffix.lower() == ".ttl" else "application/octet-stream",
                provenance={"ontology_id": stable_id, "source": "legacy_ingestion_migration"},
            )
            existing.update({"original_filename": safe_filename, "artifact_path": str(artifact_path), "artifact_id": shared_artifact["artifact_id"]})
            (artifact_dir / "metadata.json").write_text(json.dumps(existing, indent=2), encoding="utf-8")
            return existing
        artifact_dir = self.root / stable_id
        artifact_dir.mkdir(parents=True, exist_ok=False)
        artifact_path = artifact_dir / safe_filename
        artifact_path.write_bytes(content)
        shared_artifact = artifact_store.ingest(
            artifact_path,
            kind="ontology",
            media_type="text/turtle" if artifact_path.suffix.lower() == ".ttl" else "application/octet-stream",
            provenance={"ontology_id": stable_id, "source": "legacy_ingestion_migration"},
        )
        metadata = {
            "ontology_id": stable_id,
            "ontology_name": str(ontology_name or normalized_prefix),
            "prefix": normalized_prefix,
            "description": str(description or ""),
            "source": "legacy_ingestion_migration",
            "original_filename": safe_filename,
            "artifact_path": str(artifact_path),
            "artifact_id": shared_artifact["artifact_id"],
            "created_at": _now(),
            "status": "registered",
        }
        metadata.update(extra_metadata or {})
        (artifact_dir / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
        return metadata

    def get(self, ontology_id: str) -> dict[str, Any] | None:
        metadata_path = self.root / ontology_id / "metadata.json"
        if not metadata_path.exists():
            return None
        return json.loads(metadata_path.read_text(encoding="utf-8"))

    def read_artifact(self, ontology_id: str) -> tuple[dict[str, Any], bytes]:
        metadata = self.get(ontology_id)
        if metadata is None:
            raise ValueError(f"Ontology artifact not found: {ontology_id}")
        path = Path(str(metadata["artifact_path"]))
        if not path.is_file():
            raise ValueError(f"Ontology artifact is missing: {ontology_id}")
        return metadata, path.read_bytes()

    def mark_superseded(self, *, ontology_id: str, successor_id: str) -> dict[str, Any]:
        """Retire an accidental or replaced catalog version without deleting it."""
        metadata = self.get(ontology_id)
        if metadata is None:
            raise ValueError(f"Ontology artifact not found: {ontology_id}")
        metadata.update({"status": "superseded", "superseded_by": _safe_token(successor_id, field="successor_id"), "superseded_at": _now()})
        (self.root / ontology_id / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
        return metadata

    def list(self) -> list[dict[str, Any]]:
        entries = []
        for metadata_path in self.root.glob("*/metadata.json"):
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            if metadata.get("status") != "superseded":
                entries.append(metadata)
        return sorted(entries, key=lambda item: item["created_at"], reverse=True)


catalog = OntologyCatalog()
