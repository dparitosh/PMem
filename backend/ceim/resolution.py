"""Provenance-preserving CEIM entity deduplication and conflict cases."""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Any

from backend.mesh_store import PostgresRegistry


def _digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def _key(entity: dict[str, Any]) -> tuple[str, str]:
    properties = dict(entity.get("properties") or {})
    return str(entity.get("ceim_type") or ""), str(properties.get("external_id") or entity.get("id") or "")


def _without_provenance(entity: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in entity.items() if key != "provenance"}


def analyze_entities(entities: list[dict[str, Any]]) -> dict[str, Any]:
    """Merge exact duplicates only; divergent facts become blocking review cases."""
    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for entity in entities: groups.setdefault(_key(entity), []).append(entity)
    canonical, merges, conflicts = [], [], []
    for key, group in groups.items():
        if len(group) == 1:
            canonical.append(group[0]); continue
        bodies = {_digest(_without_provenance(item)) for item in group}
        if len(bodies) == 1:
            first = dict(group[0]); provenance = dict(first.get("provenance") or {})
            provenance["merged_source_provenance"] = [dict(item.get("provenance") or {}) for item in group]
            provenance["entity_resolution"] = {"strategy": "exact_duplicate_merge", "input_count": len(group)}
            first["provenance"] = provenance; canonical.append(first)
            merges.append({"entity_key": list(key), "strategy": "exact_duplicate_merge", "merged_count": len(group), "entity_id": first.get("id")})
        else:
            conflicts.append({"entity_key": list(key), "strategy_options": ["keep_most_complete", "source_priority", "manual"], "candidate_ids": [item.get("id") for item in group], "candidates": group})
            canonical.extend(group)
    return {"entities": canonical, "duplicate_merges": merges, "conflicts": conflicts, "blocking": bool(conflicts)}


class EntityResolutionRegistry:
    def __init__(self) -> None: self.store = PostgresRegistry("ceim_entity_resolution_cases")

    def record(self, analysis: dict[str, Any], actor: str = "system") -> dict[str, Any]:
        case_ids = []
        for conflict in analysis["conflicts"]:
            fingerprint = _digest({"entity_key": conflict["entity_key"], "candidates": conflict["candidates"]})
            key = f"case:{fingerprint}"
            current = self.store.get(key)
            if current is None:
                current = {"case_id": str(uuid.uuid4()), "fingerprint": fingerprint, "status": "open", "created_at": datetime.now(timezone.utc).isoformat(), "created_by": actor, **conflict, "history": [{"action": "detected", "at": datetime.now(timezone.utc).isoformat(), "actor": actor}]}
                self.store.put(key, current)
            case_ids.append(current["case_id"])
        return {**analysis, "resolution_case_ids": case_ids}

    def list(self) -> list[dict[str, Any]]:
        return sorted([value for key, value in self.store.all().items() if key.startswith("case:")], key=lambda value: value["created_at"], reverse=True)

    def resolve(self, case_id: str, strategy: str, actor: str, rationale: str, selected_candidate_index: int | None = None) -> dict[str, Any]:
        if strategy not in {"keep_most_complete", "source_priority", "manual"} or not rationale.strip():
            raise ValueError("A supported strategy and rationale are required")
        for key, record in self.store.all().items():
            if key.startswith("case:") and record.get("case_id") == case_id:
                if record.get("status") == "resolved": return record
                candidates = list(record.get("candidates") or [])
                if not candidates: raise ValueError("Resolution case has no candidates")
                if strategy == "keep_most_complete":
                    index = max(range(len(candidates)), key=lambda value: len([item for item in dict(candidates[value].get("properties") or {}).values() if item not in (None, "")]))
                else:
                    if not isinstance(selected_candidate_index, int) or not 0 <= selected_candidate_index < len(candidates):
                        raise ValueError("source_priority and manual strategies require a valid selected_candidate_index")
                    index = selected_candidate_index
                resolved_entity = dict(candidates[index]); provenance = dict(resolved_entity.get("provenance") or {})
                provenance["entity_resolution"] = {"case_id": record["case_id"], "strategy": strategy, "rationale": rationale, "resolved_by": actor, "candidate_index": index}
                provenance["merged_source_provenance"] = [dict(item.get("provenance") or {}) for item in candidates]
                resolved_entity["provenance"] = provenance
                resolved = {**record, "status": "resolved", "resolved_entity": resolved_entity, "resolution": {"strategy": strategy, "rationale": rationale, "resolved_by": actor, "resolved_at": datetime.now(timezone.utc).isoformat(), "candidate_index": index}, "history": [*record.get("history", []), {"action": "resolved", "strategy": strategy, "actor": actor, "at": datetime.now(timezone.utc).isoformat()}]}
                return self.store.put(key, resolved)
        raise LookupError("Entity resolution case was not found")

    def apply(self, analysis: dict[str, Any], case_ids: list[str]) -> dict[str, Any]:
        """Replace only explicitly resolved conflict groups for a replayed batch."""
        if not case_ids:
            return analysis
        resolved = {record.get("fingerprint"): record for record in self.list() if record.get("case_id") in set(case_ids) and record.get("status") == "resolved"}
        entities = list(analysis["entities"]); remaining = []
        for conflict in analysis["conflicts"]:
            fingerprint = _digest({"entity_key": conflict["entity_key"], "candidates": conflict["candidates"]})
            record = resolved.get(fingerprint)
            if not record: remaining.append(conflict); continue
            candidate_digests = {_digest(item) for item in conflict["candidates"]}
            entities = [item for item in entities if _digest(item) not in candidate_digests]
            entities.append(record["resolved_entity"])
        return {**analysis, "entities": entities, "conflicts": remaining, "blocking": bool(remaining)}


resolution_registry = EntityResolutionRegistry()
