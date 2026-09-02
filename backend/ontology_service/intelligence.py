"""Semantica quality and evolution capabilities exposed as explicit APIs."""
from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from typing import Any

from semantica.change_management import OntologyVersionManager
from semantica.conflicts import detect_conflicts, resolve_conflicts
from semantica.deduplication import detect_duplicates, merge_entities
from semantica.kg import GraphAnalyzer
from semantica.context import ContextGraph
from backend.mesh_store import PostgresRegistry


def serialise(value: Any) -> Any:
    if is_dataclass(value):
        return {key: serialise(item) for key, item in asdict(value).items()}
    if isinstance(value, dict):
        return {str(key): serialise(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [serialise(item) for item in value]
    if hasattr(value, "__dict__"):
        return serialise(vars(value))
    if hasattr(value, "value"):
        return value.value
    return value


class SemanticIntelligence:
    def __init__(self, root: Path, registry: Any | None = None) -> None:
        root.mkdir(parents=True, exist_ok=True)
        self.root = root
        self.registry = registry or PostgresRegistry("ontology_semantic_policies")
        self.legacy_policy_path = root / "semantica_policies.json"

    def _policies(self) -> list[dict[str, Any]]:
        value = self.registry.get("policies")
        if isinstance(value, dict) and isinstance(value.get("items"), list):
            for policy in value["items"]:
                if isinstance(policy, dict) and policy.get("policy_id"):
                    self.registry.put(f"policy:{policy['policy_id']}", policy)
            self.registry.put("policies", {"migrated": True})
            value = {"migrated": True}
        if value is None and self.legacy_policy_path.is_file():
            try:
                items = json.loads(self.legacy_policy_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise RuntimeError(f"Legacy Semantica policies are unreadable: {exc}") from exc
            for policy in items if isinstance(items, list) else []:
                if isinstance(policy, dict) and policy.get("policy_id"):
                    self.registry.put(f"policy:{policy['policy_id']}", policy)
            self.registry.put("policies", {"migrated": True})
        return [value for key, value in self.registry.all().items() if key.startswith("policy:")]

    def _save_policies(self, policies: list[dict[str, Any]]) -> None:
        for policy in policies:
            self.registry.put(f"policy:{policy['policy_id']}", policy)

    def add_policy(self, policy: dict[str, Any]) -> dict[str, Any]:
        policy_id = str(policy.get("policy_id") or policy.get("name") or "").strip().lower().replace(" ", "-")
        if not policy_id or not isinstance(policy.get("rules"), dict):
            raise ValueError("policy_id/name and rules are required")
        record = {"policy_id": policy_id, "name": str(policy.get("name") or policy_id), "rules": policy["rules"], "active": bool(policy.get("active", True)), "updated_at": datetime.now(timezone.utc).isoformat()}
        self.registry.put(f"policy:{policy_id}", record)
        return record

    def evaluate_policies(self, decision: dict[str, Any], exception_policy_ids: list[str] | None = None) -> dict[str, Any]:
        exceptions = set(exception_policy_ids or [])
        checks = []
        engine = ContextGraph()
        for policy in self._policies():
            if not policy.get("active", True):
                continue
            result = engine.enforce_decision_policy(decision, policy["rules"])
            checks.append({"policy_id": policy["policy_id"], "excepted": policy["policy_id"] in exceptions, **serialise(result)})
        blocking = [item for item in checks if not item["compliant"] and not item["excepted"]]
        return {"compliant": not blocking, "checks": checks, "blocking_policy_ids": [item["policy_id"] for item in blocking]}

    def quality_gate(self, *, entities: list[dict[str, Any]], deduplicate: bool, conflict_property: str | None,
                     merge_strategy: str = "keep_most_complete") -> dict[str, Any]:
        # Semantica's similarity deduplication is intentionally exhaustive.
        # Running it across a multi-thousand-term standard schema is quadratic
        # and can starve the service.  For large inputs, first use a stable,
        # lossless normalized-name index and ask Semantica to review only true
        # collision groups.  The response records the bounded review mode so a
        # caller never mistakes it for a full semantic similarity pass.
        full_limit = max(1, int(os.getenv("SEMANTIC_FULL_DEDUPLICATION_LIMIT", "500")))
        review_entities = entities
        review_mode = "full"
        if deduplicate and len(entities) > full_limit:
            groups: dict[str, list[dict[str, Any]]] = {}
            for entity in entities:
                name = str(entity.get("name") or entity.get("id") or "").strip().casefold()
                if name:
                    groups.setdefault(name, []).append(entity)
            review_entities = [entity for group in groups.values() if len(group) > 1 for entity in group]
            review_mode = "normalized-name-collisions"
        duplicates = detect_duplicates(review_entities) if deduplicate and review_entities else []
        merges = merge_entities(review_entities, method=merge_strategy) if deduplicate and review_entities else []
        conflicts = detect_conflicts(entities, property_name=conflict_property) if conflict_property else []
        resolutions = resolve_conflicts(conflicts) if conflicts else []
        return {
            "entities_received": len(entities), "entities_semantically_reviewed": len(review_entities), "review_mode": review_mode,
            "duplicates": serialise(duplicates), "merge_operations": serialise(merges),
            "conflicts": serialise(conflicts), "resolutions": serialise(resolutions),
            "publish_recommended": not duplicates and not conflicts,
        }

    def create_version(self, *, ontology: dict[str, Any], label: str, author: str, description: str) -> dict[str, Any]:
        manager = self._version_manager()
        snapshot = serialise(manager.create_snapshot(ontology, label, author, description))
        self.registry.put(f"version:{label}", snapshot)
        return snapshot

    def list_versions(self) -> list[dict[str, Any]]:
        return serialise(self._version_manager().list_versions())

    def compare_versions(self, older: str, newer: str) -> dict[str, Any]:
        return serialise(self._version_manager().compare_versions(older, newer))

    def _version_manager(self) -> OntologyVersionManager:
        """Hydrate Semantica's native manager from durable PostgreSQL snapshots."""
        manager = OntologyVersionManager(storage_path=None)
        for key, snapshot in self.registry.all().items():
            if not key.startswith("version:") or not isinstance(snapshot, dict):
                continue
            manager.storage.save(snapshot)
            manager.versions[str(snapshot.get("label") or key.removeprefix("version:"))] = snapshot
        return manager

    def analytics(self, graph: dict[str, Any]) -> dict[str, Any]:
        analyzer = GraphAnalyzer()
        return serialise(analyzer.analyze_graph(graph))
