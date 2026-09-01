"""Semantica quality and evolution capabilities exposed as explicit APIs."""
from __future__ import annotations

from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

from semantica.change_management import OntologyVersionManager
from semantica.conflicts import detect_conflicts, resolve_conflicts
from semantica.deduplication import detect_duplicates, merge_entities
from semantica.kg import GraphAnalyzer


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
        self.versions = OntologyVersionManager(storage_path=str(root / "semantica_versions.sqlite"))

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
