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
        metadata = {
            "ontology_id": ontology_id,
            "ontology_name": str(ontology_name or prefix),
            "prefix": prefix,
            "description": str(description or ""),
            "source": source,
            "original_filename": safe_filename,
            "artifact_path": str(artifact_path),
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

    def list(self) -> list[dict[str, Any]]:
        entries = []
        for metadata_path in self.root.glob("*/metadata.json"):
            entries.append(json.loads(metadata_path.read_text(encoding="utf-8")))
        return sorted(entries, key=lambda item: item["created_at"], reverse=True)


catalog = OntologyCatalog()
