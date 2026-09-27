"""Durable worker heartbeat visible to the pipeline control plane and UI."""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

from backend.mesh_store import PostgresRegistry

store = PostgresRegistry("data_pipeline_workers")


def put(worker_id: str, **values: Any) -> dict[str, Any]:
    current = store.get(worker_id) or {}
    return store.put(worker_id, {**current, "worker_id": worker_id, "heartbeat_at": datetime.now(timezone.utc).isoformat(), **values})


def summary() -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    stale_after = max(30, min(int(os.getenv("DEPO_PIPELINE_WORKER_STALE_SECONDS", "60")), 3600))
    workers = []
    for stored in store.all().values():
        item = dict(stored)
        try:
            age = (now - datetime.fromisoformat(str(item.get("heartbeat_at")))).total_seconds()
        except (TypeError, ValueError):
            age = float("inf")
        item["heartbeat_age_seconds"] = round(max(0, age), 1) if age != float("inf") else None
        item["available"] = item.get("status") != "stopped" and age <= stale_after
        if not item["available"] and item.get("status") != "stopped":
            item["status"] = "stale"
        workers.append(item)
    active = [item for item in workers if item["available"]]
    return {"workers": workers, "worker_count": len(active), "registered_worker_count": len(workers),
            "busy_workers": sum(1 for item in active if item.get("status") == "busy"), "worker_stale_after_seconds": stale_after}
