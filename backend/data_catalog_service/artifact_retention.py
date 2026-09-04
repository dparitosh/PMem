"""Governed retention, tier, legal-hold, and purge evidence for raw artifacts."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from backend.artifact_store import ArtifactStore
from backend.mesh_store import PostgresRegistry


TIERS = {"hot", "warm", "cold", "archive"}


class ArtifactRetentionRegistry:
    def __init__(self) -> None:
        self.store = PostgresRegistry("artifact_retention")
        self.artifact_store = ArtifactStore()

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    @staticmethod
    def _policy_key(artifact_id: str) -> str:
        return f"policy:{artifact_id}"

    def register(self, artifact_id: str, payload: dict[str, Any], actor: str) -> dict[str, Any]:
        metadata, _ = self.artifact_store.resolve(artifact_id)
        days, tier = payload.get("retention_days"), str(payload.get("tier") or "hot").lower()
        if not isinstance(days, int) or not 1 <= days <= 36_500:
            raise ValueError("retention_days must be an integer between 1 and 36500")
        if tier not in TIERS:
            raise ValueError(f"tier must be one of: {', '.join(sorted(TIERS))}")
        reason = str(payload.get("reason") or "").strip()
        if not reason:
            raise ValueError("reason is required for retention policy evidence")
        now = self._now()
        existing = self.store.get(self._policy_key(artifact_id)) or {}
        if existing.get("status") == "purged":
            raise ValueError("A purged artifact retention record cannot be reactivated")
        registered_at = existing.get("registered_at") or now.isoformat()
        record = {
            "artifact_id": artifact_id,
            "kind": metadata.get("kind"),
            "size": metadata.get("size"),
            "tier": tier,
            "retention_days": days,
            "legal_hold": bool(payload.get("legal_hold", False)),
            "status": "active",
            "registered_at": registered_at,
            "expires_at": (datetime.fromisoformat(registered_at) + timedelta(days=days)).isoformat(),
            "updated_at": now.isoformat(),
            "updated_by": actor,
            "reason": reason,
        }
        event = {
            "event_id": str(uuid.uuid4()), "artifact_id": artifact_id,
            "event_type": "retention_registered" if not existing else "retention_updated",
            "occurred_at": now.isoformat(), "actor": actor, "reason": reason,
            "tier": tier, "retention_days": days, "legal_hold": record["legal_hold"],
        }
        self.store.put_many({self._policy_key(artifact_id): record, f"event:{event['event_id']}": event})
        return record

    def policies(self) -> list[dict[str, Any]]:
        return sorted(
            [value for key, value in self.store.all().items() if key.startswith("policy:")],
            key=lambda item: item.get("updated_at", ""), reverse=True,
        )

    def history(self, artifact_id: str) -> list[dict[str, Any]]:
        return sorted(
            [value for key, value in self.store.all().items() if key.startswith("event:") and value.get("artifact_id") == artifact_id],
            key=lambda item: item.get("occurred_at", ""),
        )

    def due(self) -> list[dict[str, Any]]:
        now = self._now()
        return [
            record for record in self.policies()
            if record.get("status") == "active" and not record.get("legal_hold")
            and datetime.fromisoformat(record["expires_at"]) <= now
        ]

    def purge(self, artifact_id: str, actor: str, reason: str) -> dict[str, Any]:
        record = self.store.get(self._policy_key(artifact_id))
        if not record:
            raise LookupError("Artifact retention policy was not found")
        if record.get("status") == "purged":
            return record
        if record.get("legal_hold"):
            raise ValueError("Artifact is under legal hold")
        if datetime.fromisoformat(record["expires_at"]) > self._now():
            raise ValueError("Artifact has not reached its retention expiry")
        if not reason.strip():
            raise ValueError("reason is required for purge evidence")
        evidence = self.artifact_store.purge(artifact_id)
        now = self._now().isoformat()
        purged = {**record, "status": "purged", "purged_at": now, "purged_by": actor, "purge_reason": reason, **evidence}
        event = {
            "event_id": str(uuid.uuid4()), "artifact_id": artifact_id, "event_type": "artifact_purged",
            "occurred_at": now, "actor": actor, "reason": reason, **evidence,
        }
        self.store.put_many({self._policy_key(artifact_id): purged, f"event:{event['event_id']}": event})
        return purged


retention = ArtifactRetentionRegistry()
