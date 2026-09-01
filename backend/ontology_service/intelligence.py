"""Semantica quality and evolution capabilities exposed as explicit APIs."""
from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from semantica.change_management import OntologyVersionManager
from semantica.conflicts import detect_conflicts, resolve_conflicts
from semantica.deduplication import detect_duplicates, merge_entities
from semantica.kg import GraphAnalyzer
from semantica.context import ContextGraph


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
    def __init__(self, root: Path) -> None:
        root.mkdir(parents=True, exist_ok=True)
        self.root = root
        self.versions = OntologyVersionManager(storage_path=str(root / "semantica_versions.sqlite"))
        self.policy_path = root / "semantica_policies.json"

    def _policies(self) -> list[dict[str, Any]]:
        if not self.policy_path.exists():
            return []
        import json
        return json.loads(self.policy_path.read_text(encoding="utf-8"))

    def _save_policies(self, policies: list[dict[str, Any]]) -> None:
        import json
        temporary = self.policy_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(policies, indent=2), encoding="utf-8")
        temporary.replace(self.policy_path)

    def add_policy(self, policy: dict[str, Any]) -> dict[str, Any]:
        policy_id = str(policy.get("policy_id") or policy.get("name") or "").strip().lower().replace(" ", "-")
        if not policy_id or not isinstance(policy.get("rules"), dict):
            raise ValueError("policy_id/name and rules are required")
        policies = [item for item in self._policies() if item["policy_id"] != policy_id]
        record = {"policy_id": policy_id, "name": str(policy.get("name") or policy_id), "rules": policy["rules"], "active": bool(policy.get("active", True)), "updated_at": datetime.now(timezone.utc).isoformat()}
        policies.append(record); self._save_policies(policies)
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
        duplicates = detect_duplicates(entities) if deduplicate else []
        merges = merge_entities(entities, method=merge_strategy) if deduplicate else []
        conflicts = detect_conflicts(entities, property_name=conflict_property) if conflict_property else []
        resolutions = resolve_conflicts(conflicts) if conflicts else []
        return {
            "entities_received": len(entities), "duplicates": serialise(duplicates), "merge_operations": serialise(merges),
            "conflicts": serialise(conflicts), "resolutions": serialise(resolutions),
            "publish_recommended": not duplicates and not conflicts,
        }

    def create_version(self, *, ontology: dict[str, Any], label: str, author: str, description: str) -> dict[str, Any]:
        return serialise(self.versions.create_snapshot(ontology, label, author, description))

    def list_versions(self) -> list[dict[str, Any]]:
        return serialise(self.versions.list_versions())

    def compare_versions(self, older: str, newer: str) -> dict[str, Any]:
        return serialise(self.versions.compare_versions(older, newer))

    def analytics(self, graph: dict[str, Any]) -> dict[str, Any]:
        analyzer = GraphAnalyzer()
        return serialise(analyzer.analyze_graph(graph))
