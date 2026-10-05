"""Approval-backed RDF ontology merge service.

Previews are persisted so an operator approves the exact reviewed merge rather
than an arbitrary re-run.  The result is a normal catalog artifact with clear
provenance plus a Semantica version snapshot.
"""
from __future__ import annotations

import json
import hashlib
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from rdflib import Graph, Literal


class GovernedMergeService:
    def __init__(self, catalog: Any, intelligence: Any, root: Path) -> None:
        self.catalog, self.intelligence = catalog, intelligence
        self.path = root / "governed_merge_previews.json"
        self.lock = threading.RLock()
        self.registry = None
        if getattr(catalog, '_postgres_enabled', False):
            from backend.mesh_store import PostgresRegistry
            self.registry = PostgresRegistry('ontology_merge_previews')

    def _operation_lock(self):
        return self.registry.advisory_lock('merge-store') if self.registry is not None else self.lock

    def _load(self) -> dict[str, dict[str, Any]]:
        values = json.loads(self.path.read_text(encoding='utf-8')) if self.path.exists() else {}
        if self.registry is not None:
            values.update(self.registry.all())
        return values

    def _save(self, values: dict[str, dict[str, Any]], changed_key: str | None = None) -> None:
        if self.registry is not None:
            selected = {changed_key: values[changed_key]} if changed_key else values
            for key, value in selected.items():
                self.registry.put(key, value)
            return
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(values, indent=2), encoding="utf-8")
        temporary.replace(self.path)

    def preview(self, payload: dict[str, Any]) -> dict[str, Any]:
        with self._operation_lock() as acquired:
            if acquired is False:
                raise ValueError('A merge operation is already running; refresh and retry')
            return self._preview(payload)

    def _preview(self, payload: dict[str, Any]) -> dict[str, Any]:
        supplied = payload.get('source_ontology_ids', [])
        if not isinstance(supplied, list) or not all(isinstance(value, str) and value.strip() for value in supplied):
            raise ValueError('source_ontology_ids must be a list of nonempty ontology IDs')
        source_ids = list(dict.fromkeys(value.strip() for value in supplied))
        if len(source_ids) < 2:
            raise ValueError("At least two distinct source_ontology_ids are required")
        if len(source_ids) > 16:
            raise ValueError('Merge at most 16 ontologies per preview')
        merged, occurrences, sources = Graph(), {}, []
        for ontology_id in source_ids:
            if self.catalog.get(ontology_id) is not None:
                metadata, content = self.catalog.read_artifact(ontology_id)
            else:
                from .domain.reasoning import OntologyReasoningService
                context = OntologyReasoningService.semantic_context(ontology_id)
                metadata = context['meta']
                path = context['file_path']
                from backend.depo_platform.upload_limits import ontology_upload_limit
                with path.open('rb') as handle:
                    content = handle.read(ontology_upload_limit() + 1)
                if len(content) > ontology_upload_limit():
                    raise ValueError('Merge source exceeds ONTOLOGY_MAX_UPLOAD_BYTES')
                metadata = {**metadata, 'original_filename': path.name}
            parsed = self.catalog._parse_ontology(content, metadata.get('original_filename') or 'ontology.ttl')
            source = Graph()
            source.parse(data=content, format=parsed['rdf_format'])
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
        values = {} if self.registry is not None else self._load()
        values[preview_id] = record
        self._save(values, preview_id)
        return {key: value for key, value in record.items() if key != "turtle"}

    def apply(self, preview_id: str, approved_by: str) -> dict[str, Any]:
        with self._operation_lock() as acquired:
            if acquired is False:
                raise ValueError('A merge operation is already running; refresh and retry')
            return self._apply(preview_id, approved_by)

    def _apply(self, preview_id: str, approved_by: str) -> dict[str, Any]:
        if not str(approved_by).strip():
            raise ValueError("approved_by is required for a governed merge")
        if self.registry is not None:
            retained = self.registry.get(preview_id)
            values = {preview_id: retained} if retained else self._load()
        else:
            values = self._load()
        record = values.get(preview_id)
        if not record:
            raise ValueError("Merge preview not found")
        if record["conflicts"]:
            raise ValueError("Merge preview contains unresolved literal conflicts")
        if record.get('applied_result'):
            return record['applied_result']
        artifact = self.catalog.register(
            content=record["turtle"].encode("utf-8"), filename=f"{record['prefix']}_merged.ttl",
            ontology_name=record["ontology_name"], prefix=record["prefix"], description=record["description"],
            source='governed-merge:' + hashlib.sha256(preview_id.encode('utf-8')).hexdigest(), extra_metadata={"status": "merged", "provenance": {"preview_id": preview_id,
            "source_ontology_ids": record["source_ontology_ids"], "approved_by": approved_by}},
        )
        version = self.intelligence.create_version(ontology={"ontology_id": artifact["ontology_id"], "provenance": artifact["provenance"], "triple_count": record["triple_count"]}, label=f"merge:{artifact['ontology_id']}", author=approved_by, description="Approved ontology merge")
        result = {"status": "merged", "ontology": artifact, "version": version, "preview_id": preview_id}
        record['applied_result'] = result
        self._save(values, preview_id)
        return result

    @staticmethod
    def _literal_conflicts(graph: Graph) -> list[dict[str, str]]:
        from rdflib.namespace import RDF, OWL
        functional = set(graph.subjects(RDF.type, OWL.FunctionalProperty))
        values: dict[tuple[str, str], set[str]] = {}
        for subject, predicate, obj in graph:
            # RDF properties are multivalued unless declared functional.
            # Distinct labels/comments (including translations) are not conflicts.
            if predicate in functional and isinstance(obj, Literal):
                values.setdefault((str(subject), str(predicate)), set()).add(obj.n3())
        return [{"subject": subject, "predicate": predicate, "values": sorted(items)}
                for (subject, predicate), items in values.items() if len(items) > 1]
