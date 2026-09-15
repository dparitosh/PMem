"""Durable ontology artifact catalog owned by the ontology service.

This deliberately does not import the legacy upload manager.  It is the
replacement persistence boundary for newly published ontology artifacts.
"""
from __future__ import annotations

import json
import os
import re
import uuid
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from rdflib import Graph

from backend.artifact_store import artifact_store
from backend.mesh_store import PostgresRegistry


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_token(value: str, *, field: str) -> str:
    token = str(value or "").strip()
    if not token or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,63}", token):
        raise ValueError(f"{field} must start with a letter and contain only letters, numbers, _ or -")
    return token


class OntologyCatalog:
    _transition_lock = threading.RLock()
    def __init__(self, root: Path | None = None, registry: Any | None = None) -> None:
        configured = os.getenv("ONTOLOGY_SERVICE_STORAGE")
        self.root = root or (Path(configured) if configured else Path(__file__).resolve().parents[2] / "data" / "ontology_service")
        self.root.mkdir(parents=True, exist_ok=True)
        self.registry = registry or PostgresRegistry("ontology_catalog")

    @property
    def _postgres_enabled(self) -> bool:
        return bool(os.getenv("DEPO_DATABASE_URL") or os.getenv("DATABASE_URL"))

    def _save_metadata(self, metadata: dict[str, Any]) -> dict[str, Any]:
        """PostgreSQL is authoritative; the local file is a recoverable artifact mirror."""
        if self._postgres_enabled:
            self.registry.put(str(metadata["ontology_id"]), metadata)
        artifact_dir = self.root / str(metadata["ontology_id"])
        artifact_dir.mkdir(parents=True, exist_ok=True)
        (artifact_dir / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
        return metadata

    @staticmethod
    def _parse_ontology(content: bytes, filename: str) -> dict[str, Any]:
        """Reject malformed RDF/OWL before it becomes a governed artifact."""
        suffix = Path(filename).suffix.lower()
        formats = {
            ".ttl": ("turtle",),
            ".rdf": ("xml", "turtle"),
            ".xml": ("xml", "turtle"),
            # OWL has no single concrete syntax: accept XML or Turtle based
            # on the actual artifact, rather than trusting its extension.
            ".owl": ("xml", "turtle"),
            ".jsonld": ("json-ld",),
            ".json": ("json-ld",),
        }
        candidates = formats.get(suffix)
        if candidates is None:
            raise ValueError("Ontology artifact must be TTL, RDF/XML, OWL, or JSON-LD")
        last_error: Exception | None = None
        for rdf_format in candidates:
            try:
                graph = Graph()
                graph.parse(data=content, format=rdf_format)
                return {"rdf_format": rdf_format, "triple_count": len(graph)}
            except Exception as exc:  # try the other supported syntax
                last_error = exc
        raise ValueError(f"Ontology RDF/OWL parsing failed: {last_error}") from last_error

    def register(self, *, content: bytes, filename: str, ontology_name: str, prefix: str, description: str = "", source: str = "api", extra_metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        if not content:
            raise ValueError("An ontology artifact is required")
        prefix = _safe_token(prefix, field="prefix")
        safe_filename = Path(filename or "ontology.ttl").name
        if not safe_filename or safe_filename in {".", ".."}:
            raise ValueError("A valid artifact filename is required")
        parse_result = self._parse_ontology(content, safe_filename)
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
            "lifecycle_status": "draft",
            "validation": {"status": "passed", **parse_result},
            "lifecycle_events": [{"at": _now(), "actor": source, "from": None, "to": "draft", "reason": "artifact registered and syntax validated"}],
        }
        metadata.update(extra_metadata or {})
        return self._save_metadata(metadata)

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
            return self._save_metadata(existing)
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
            "lifecycle_status": "draft",
            "lifecycle_events": [{"at": _now(), "actor": "legacy_ingestion_migration", "from": None, "to": "draft", "reason": "legacy artifact adopted; review required"}],
        }
        metadata.update(extra_metadata or {})
        return self._save_metadata(metadata)

    def get(self, ontology_id: str) -> dict[str, Any] | None:
        _safe_token(ontology_id, field="ontology_id")
        if self._postgres_enabled:
            record = self.registry.get(ontology_id)
            if record is not None:
                return record
        metadata_path = self.root / ontology_id / "metadata.json"
        if not metadata_path.exists():
            return None
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        if self._postgres_enabled:
            self.registry.put(ontology_id, metadata)
        return metadata

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
        return self._save_metadata(metadata)

    def transition(self, *, ontology_id: str, target: str, actor: str, reason: str = "") -> dict[str, Any]:
        """Move an ontology through the minimal review lifecycle with evidence."""
        _safe_token(ontology_id, field="ontology_id")
        with self._transition_lock:
            if self._postgres_enabled:
                with self.registry.advisory_lock(f"lifecycle:{ontology_id}") as acquired:
                    if not acquired:
                        raise ValueError("Ontology lifecycle is being updated; retry")
                    return self._transition(ontology_id, target, actor, reason)
            return self._transition(ontology_id, target, actor, reason)

    def _transition(self, ontology_id: str, target: str, actor: str, reason: str) -> dict[str, Any]:
        metadata = self.get(ontology_id)
        if metadata is None:
            raise LookupError(f"Ontology artifact not found: {ontology_id}")
        transitions = {
            "draft": {"in_review", "retired"},
            "in_review": {"draft", "approved", "retired"},
            "approved": {"deprecated", "retired"},
            "deprecated": {"retired"},
            "retired": set(),
        }
        current = str(metadata.get("lifecycle_status") or "draft")
        normalized_target = str(target or "").strip().lower()
        if normalized_target not in transitions.get(current, set()):
            raise ValueError(f"Invalid lifecycle transition: {current} -> {normalized_target or 'missing'}")
        if not str(actor or "").strip():
            raise ValueError("A review identity is required")
        if normalized_target == "approved":
            _, content = self.read_artifact(ontology_id)
            parsed = self._parse_ontology(content, metadata["original_filename"])
            metadata["validation"] = {"status": "passed", **parsed}
        metadata["lifecycle_status"] = normalized_target
        metadata.setdefault("lifecycle_events", []).append({
            "at": _now(), "actor": str(actor), "from": current,
            "to": normalized_target, "reason": str(reason or ""),
        })
        return self._save_metadata(metadata)

    def list(self) -> list[dict[str, Any]]:
        entries = list(self.registry.all().values()) if self._postgres_enabled else []
        known = {str(item.get("ontology_id") or "") for item in entries}
        for metadata_path in self.root.glob("*/metadata.json"):
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            if metadata.get("ontology_id") not in known:
                if self._postgres_enabled:
                    self.registry.put(str(metadata["ontology_id"]), metadata)
                entries.append(metadata)
        active_entries = [entry for entry in entries if entry.get("status") != "superseded"]
        return sorted(active_entries, key=lambda item: item["created_at"], reverse=True)


catalog = OntologyCatalog()
