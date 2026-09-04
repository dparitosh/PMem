"""Governed low-latency event path with the same CEIM contract as batch."""
from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import datetime, timezone
from typing import Any

from backend.artifact_store import ArtifactStore
from backend.ceim.contract import contract
from backend.mesh_store import PostgresRegistry


_ID = re.compile(r"[a-z][a-z0-9-]{2,62}$")
sources = PostgresRegistry("speed_path_sources")
events = PostgresRegistry("speed_path_events")
reconciliations = PostgresRegistry("speed_path_reconciliations")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def register_source(payload: dict[str, Any], actor: str) -> dict[str, Any]:
    source_id = str(payload.get("source_id") or "").strip().lower()
    standards = sorted({str(item).strip().lower() for item in payload.get("allowed_standards", []) if str(item).strip()})
    if not _ID.fullmatch(source_id) or not standards:
        raise ValueError("source_id must be lowercase kebab-case and allowed_standards must be non-empty")
    if sources.get(source_id):
        raise FileExistsError("Speed-path source already exists")
    retraction_policy = str(payload.get("retraction_policy") or "review").lower()
    if retraction_policy not in {"review", "tombstone"}:
        raise ValueError("retraction_policy must be review or tombstone")
    return sources.put(source_id, {
        "source_id": source_id, "name": str(payload.get("name") or source_id), "owner": str(payload.get("owner") or actor),
        "allowed_standards": standards, "max_lateness_seconds": max(0, min(int(payload.get("max_lateness_seconds", 300)), 86_400)), "retraction_policy": retraction_policy,
        "lifecycle_state": "draft", "enabled": False, "created_at": _now(), "created_by": actor,
    })


def approve_source(source_id: str, actor: str) -> dict[str, Any]:
    record = sources.get(source_id)
    if not record:
        raise LookupError("Speed-path source was not found")
    return sources.put(source_id, {**record, "lifecycle_state": "approved", "enabled": True, "approved_at": _now(), "approved_by": actor})


def list_sources() -> list[dict[str, Any]]:
    return sorted(sources.all().values(), key=lambda item: item["source_id"])


def capture_event(payload: dict[str, Any], actor: str) -> dict[str, Any]:
    event_id, source_id = str(payload.get("event_id") or "").strip(), str(payload.get("source_id") or "").strip().lower()
    standard = str(payload.get("standard") or "").strip().lower()
    occurred_at = str(payload.get("occurred_at") or "").strip()
    if len(json.dumps(payload, default=str).encode("utf-8")) > 1_048_576:
        raise ValueError("Speed-path event exceeds the 1 MiB bounded envelope limit")
    source = sources.get(source_id)
    event_type = str(payload.get("event_type") or "modification").lower()
    if event_type not in {"creation", "modification", "deletion"}:
        raise ValueError("event_type must be creation, modification or deletion")
    if not event_id or not source_id or not standard or not occurred_at or not isinstance(payload.get("records"), dict):
        raise ValueError("event_id, source_id, standard, occurred_at and records object are required")
    if event_type == "deletion" and not str(payload.get("resource_id") or "").strip():
        raise ValueError("Deletion events require resource_id for retraction review")
    if not source or source.get("lifecycle_state") != "approved" or not source.get("enabled"):
        raise ValueError("Speed-path source is not approved and enabled")
    if standard not in source["allowed_standards"]:
        raise ValueError("Event standard is not allowed for this source")
    try:
        timestamp = datetime.fromisoformat(occurred_at.replace("Z", "+00:00"))
        if timestamp.tzinfo is None: raise ValueError
    except ValueError as exc:
        raise ValueError("occurred_at must be an ISO-8601 timestamp with timezone") from exc
    digest = _digest(payload)
    existing = events.get(event_id)
    if existing:
        if existing["payload_digest"] != digest: raise ValueError("event_id was reused with a different payload")
        return {**existing, "idempotent": True}
    age_seconds = max(0, (datetime.now(timezone.utc) - timestamp.astimezone(timezone.utc)).total_seconds())
    late = age_seconds > int(source["max_lateness_seconds"])
    artifact = ArtifactStore().ingest_bytes(json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode(), filename=f"{event_id}.json", kind="speed-event-envelope", media_type="application/json", provenance={"source_id": source_id, "event_id": event_id, "captured_by": actor})
    record = {"event_id": event_id, "source_id": source_id, "standard": standard, "event_type": event_type, "occurred_at": occurred_at, "captured_at": _now(), "captured_by": actor, "payload_digest": digest, "artifact_id": artifact["artifact_id"], "status": "retraction_pending_review" if event_type == "deletion" else "late" if late else "accepted", "quality": {"event_id_unique": True, "provenance_present": True, "lateness_seconds": round(age_seconds, 3), "late": late, "retraction_policy": source["retraction_policy"]}, "reconciliation_id": None}
    return events.put(event_id, record)


def list_events(limit: int = 100) -> list[dict[str, Any]]:
    return sorted(events.all().values(), key=lambda item: item.get("captured_at", ""), reverse=True)[:max(1, min(limit, 1000))]


def reconcile(event_ids: list[str], actor: str) -> dict[str, Any]:
    if not event_ids or len(event_ids) > 500: raise ValueError("event_ids must contain between 1 and 500 events")
    selected = [events.get(str(event_id)) for event_id in event_ids]
    if any(item is None for item in selected): raise LookupError("One or more speed-path events were not found")
    selected = [item for item in selected if item]
    if any(item["status"] not in {"accepted", "late"} for item in selected): raise ValueError("Only non-deletion captured events can be reconciled; retractions require steward review")
    standards = {item["standard"] for item in selected}
    if len(standards) != 1: raise ValueError("A reconciliation batch must contain one source standard")
    standard = standards.pop()
    entities, relationships = [], []
    for item in selected:
        _, path = ArtifactStore().resolve(item["artifact_id"])
        payload = json.loads(path.read_text(encoding="utf-8"))
        records = payload["records"]
        entities.extend(list(records.get("entities") or [])); relationships.extend(list(records.get("relationships") or []))
    if not entities and not relationships: raise ValueError("Events contain no CEIM source records")
    normalized_entities = [contract.normalize_entity(standard=standard, record=dict(row)) for row in entities]
    normalized_relationships = [contract.normalize_relationship(standard=standard, record=dict(row)) for row in relationships]
    validation = contract.validate_projection(entities=normalized_entities, relationships=normalized_relationships)
    batch = {"contract": "normalized-ceim-batch-v1", "representation": "normalized-ceim-v1", "standard": standard, "ceim_version": contract.version, "mapping_digest": contract.mapping_pack(standard)["digest"], "entities": normalized_entities, "relationships": normalized_relationships, "source_event_ids": [item["event_id"] for item in selected], "provisional": True}
    artifact = ArtifactStore().ingest_bytes(json.dumps(batch, sort_keys=True, separators=(",", ":")).encode(), filename=f"speed-reconciliation-{uuid.uuid4()}.json", kind="accepted-semantic-partition" if validation.get("conforms") else "rejected-semantic-partition", media_type="application/json", provenance={"producer": "speed-path", "reconciled_by": actor})
    reconciliation_id = str(uuid.uuid4())
    result = {"reconciliation_id": reconciliation_id, "status": "ready_for_approved_publication" if validation.get("conforms") else "quarantined", "standard": standard, "ceim_version": contract.version, "mapping_digest": batch["mapping_digest"], "event_ids": batch["source_event_ids"], "partition_artifact_id": artifact["artifact_id"], "validation": validation, "created_at": _now(), "created_by": actor, "publication": "not_attempted; canonical CEIM approval is required"}
    reconciliations.put(reconciliation_id, result)
    for item in selected: events.put(item["event_id"], {**item, "status": "reconciled" if validation.get("conforms") else "quarantined", "reconciliation_id": reconciliation_id})
    return result
