"""Approval-backed RDF ontology merge service.

Previews are persisted so an operator approves the exact reviewed merge rather
than an arbitrary re-run.  The result is a normal catalog artifact with clear
provenance plus a Semantica version snapshot.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from rdflib import Graph, Literal


class GovernedMergeService:
    def __init__(self, catalog: Any, intelligence: Any, root: Path) -> None:
        self.catalog, self.intelligence = catalog, intelligence
        self.path = root / "governed_merge_previews.json"

    def _load(self) -> dict[str, dict[str, Any]]:
        return json.loads(self.path.read_text(encoding="utf-8")) if self.path.exists() else {}

    def _save(self, values: dict[str, dict[str, Any]]) -> None:
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(values, indent=2), encoding="utf-8")
        temporary.replace(self.path)

    def preview(self, payload: dict[str, Any]) -> dict[str, Any]:
        source_ids = list(dict.fromkeys(str(value) for value in payload.get("source_ontology_ids", [])))
        if len(source_ids) < 2:
            raise ValueError("At least two distinct source_ontology_ids are required")
        merged, occurrences, sources = Graph(), {}, []
        for ontology_id in source_ids:
            metadata, content = self.catalog.read_artifact(ontology_id)
            source = Graph()
            source.parse(data=content, format="turtle")
            sources.append({"ontology_id": ontology_id, "ontology_name": metadata["ontology_name"]})
            for triple in source:
                key = tuple(map(str, triple))
                occurrences[key] = occurrences.get(key, 0) + 1
                merged.add(triple)
        conflicts = self._literal_conflicts(merged)
        preview_id = uuid.uuid4().hex
        record = {"preview_id": preview_id, "created_at": datetime.now(timezone.utc).isoformat(),
                  "source_ontology_ids": source_ids, "sources": sources,
                  "ontology_name": str(payload.get("ontology_name") or "Merged Ontology"),
                  "prefix": str(payload.get("prefix") or "merged"),
                  "description": str(payload.get("description") or ""),
                  "triple_count": len(merged), "duplicate_triple_count": sum(value - 1 for value in occurrences.values() if value > 1),
                  "conflicts": conflicts, "publish_recommended": not conflicts,
                  "turtle": merged.serialize(format="turtle")}
        values = self._load(); values[preview_id] = record; self._save(values)
        return {key: value for key, value in record.items() if key != "turtle"}

    def apply(self, preview_id: str, approved_by: str) -> dict[str, Any]:
        if not str(approved_by).strip():
            raise ValueError("approved_by is required for a governed merge")
        record = self._load().get(preview_id)
        if not record:
            raise ValueError("Merge preview not found")
        if record["conflicts"]:
            raise ValueError("Merge preview contains unresolved literal conflicts")
        artifact = self.catalog.register(
            content=record["turtle"].encode("utf-8"), filename=f"{record['prefix']}_merged.ttl",
            ontology_name=record["ontology_name"], prefix=record["prefix"], description=record["description"],
            source="governed-merge", extra_metadata={"status": "merged", "provenance": {"preview_id": preview_id,
            "source_ontology_ids": record["source_ontology_ids"], "approved_by": approved_by}},
        )
        version = self.intelligence.create_version(ontology={"ontology_id": artifact["ontology_id"], "provenance": artifact["provenance"], "triple_count": record["triple_count"]}, label=f"merge:{artifact['ontology_id']}", author=approved_by, description="Approved ontology merge")
        return {"status": "merged", "ontology": artifact, "version": version, "preview_id": preview_id}

    @staticmethod
    def _literal_conflicts(graph: Graph) -> list[dict[str, str]]:
        values: dict[tuple[str, str], set[str]] = {}
        for subject, predicate, obj in graph:
            if isinstance(obj, Literal):
                values.setdefault((str(subject), str(predicate)), set()).add(str(obj))
        return [{"subject": subject, "predicate": predicate, "values": sorted(items)}
                for (subject, predicate), items in values.items() if len(items) > 1]
