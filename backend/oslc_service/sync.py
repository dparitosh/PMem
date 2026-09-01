"""Auditable, on-demand OSLC pull synchronization without a task queue."""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .client import OSLCClient


class OSLCSyncStore:
    """Persist remote OSLC query snapshots for explicit review and ingestion.

    This service deliberately does not push to a remote provider or publish to
    the semantic graph. Both actions need a target-domain mapping and an
    explicit approval step, rather than an opaque scheduled mutation.
    """

    def __init__(self) -> None:
        self.root = Path(os.getenv("OSLC_SYNC_STORAGE", "data/oslc_service/syncs"))

    def _path(self, sync_id: str) -> Path:
        try:
            return self.root / f"{uuid.UUID(sync_id)}.json"
        except (AttributeError, ValueError) as exc:
            raise ValueError("sync_id must be a UUID") from exc

    def create(self, *, resource_type: str, parameters: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
        self.root.mkdir(parents=True, exist_ok=True)
        sync_id = str(uuid.uuid4())
        resources = payload.get("value") or payload.get("resources") or payload.get("results") or []
        if not isinstance(resources, list):
            resources = [resources]
        snapshot = {
            "sync_id": sync_id,
            "status": "staged",
            "direction": "pull",
            "resource_type": resource_type,
            "parameters": parameters,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "resources": resources,
            "resource_count": len(resources),
            "next_action": "Map and approve this snapshot through the ingestion service before graph publication.",
        }
        self._path(sync_id).write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
        return snapshot

    def list(self) -> list[dict[str, Any]]:
        if not self.root.exists():
            return []
        entries = []
        for path in self.root.glob("*.json"):
            try:
                snapshot = json.loads(path.read_text(encoding="utf-8"))
                entries.append({key: value for key, value in snapshot.items() if key != "resources"})
            except (OSError, json.JSONDecodeError):
                continue
        return sorted(entries, key=lambda item: str(item.get("created_at", "")), reverse=True)

    def get(self, sync_id: str) -> dict[str, Any] | None:
        try:
            path = self._path(sync_id)
        except ValueError:
            return None
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))


class OSLCSynchronizer:
    def __init__(self, client: OSLCClient, store: OSLCSyncStore | None = None) -> None:
        self.client, self.store = client, store or OSLCSyncStore()

    def pull(self, resource_type: str, parameters: dict[str, Any]) -> dict[str, Any]:
        return self.store.create(resource_type=resource_type, parameters=parameters, payload=self.client.query(resource_type, parameters))
