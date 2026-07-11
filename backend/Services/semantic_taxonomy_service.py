"""SKOS taxonomy services for ontology-adjacent vocabulary.

This module intentionally keeps SKOS concepts separate from OWL classes and
instance data. OWL is still handled by Owlready2/RDFLib services; this layer is
for concept schemes, labels, synonyms, hierarchy, mappings, validation, search,
and Neo4j storage plans.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Mapping, Sequence, Tuple


SKOS_MAPPING_TYPES = {
    "exactMatch",
    "closeMatch",
    "broadMatch",
    "narrowMatch",
    "relatedMatch",
}


@dataclass(frozen=True)
class SkosConceptScheme:
    scheme_id: str
    pref_label: str
    definition: str = ""
    version: str = "1"


@dataclass(frozen=True)
class SkosConcept:
    concept_id: str
    scheme_id: str
    pref_label: str
    alt_labels: Tuple[str, ...] = ()
    definition: str = ""
    broader: Tuple[str, ...] = ()
    narrower: Tuple[str, ...] = ()
    related: Tuple[str, ...] = ()
    mappings: Mapping[str, Tuple[str, ...]] = field(default_factory=dict)

    def all_labels(self) -> Tuple[str, ...]:
        return tuple(label for label in (self.pref_label, *self.alt_labels) if label)


def _as_tuple(value: Any) -> Tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value.strip(),) if value.strip() else ()
    if isinstance(value, Iterable):
        return tuple(str(item).strip() for item in value if str(item or "").strip())
    return ()


def normalize_skos_payload(payload: Mapping[str, Any]) -> Tuple[SkosConceptScheme, List[SkosConcept]]:
    """Normalize loose API payloads into typed SKOS records."""
    scheme_raw = payload.get("scheme") or {}
    scheme_id = str(scheme_raw.get("scheme_id") or scheme_raw.get("id") or payload.get("scheme_id") or "").strip()
    if not scheme_id:
        raise ValueError("SKOS scheme_id is required")

    scheme = SkosConceptScheme(
        scheme_id=scheme_id,
        pref_label=str(scheme_raw.get("pref_label") or scheme_raw.get("label") or scheme_id).strip(),
        definition=str(scheme_raw.get("definition") or "").strip(),
        version=str(scheme_raw.get("version") or payload.get("version") or "1").strip(),
    )

    concepts: List[SkosConcept] = []
    for raw in payload.get("concepts") or []:
        concept_id = str(raw.get("concept_id") or raw.get("id") or raw.get("uri") or "").strip()
        pref_label = str(raw.get("pref_label") or raw.get("label") or raw.get("name") or "").strip()
        if not concept_id or not pref_label:
            continue
        raw_mappings = raw.get("mappings") or {}
        mappings = {
            mapping_type: _as_tuple(targets)
            for mapping_type, targets in raw_mappings.items()
            if mapping_type in SKOS_MAPPING_TYPES and _as_tuple(targets)
        }
        concepts.append(
            SkosConcept(
                concept_id=concept_id,
                scheme_id=str(raw.get("scheme_id") or scheme.scheme_id).strip(),
                pref_label=pref_label,
                alt_labels=_as_tuple(raw.get("alt_labels") or raw.get("altLabel")),
                definition=str(raw.get("definition") or "").strip(),
                broader=_as_tuple(raw.get("broader")),
                narrower=_as_tuple(raw.get("narrower")),
                related=_as_tuple(raw.get("related")),
                mappings=mappings,
            )
        )
    return scheme, concepts


class SemanticTaxonomyService:
    """Pure SKOS validation, traversal, and semantic label search."""

    @staticmethod
    def validate(concepts: Sequence[SkosConcept]) -> Dict[str, Any]:
        by_id = {concept.concept_id: concept for concept in concepts}
        issues: List[Dict[str, Any]] = []

        label_owner: Dict[str, str] = {}
        for concept in concepts:
            for label in concept.all_labels():
                key = label.casefold()
                if key in label_owner and label_owner[key] != concept.concept_id:
                    issues.append({
                        "severity": "error",
                        "code": "duplicate_label",
                        "message": f"Duplicate SKOS label '{label}'",
                        "concepts": [label_owner[key], concept.concept_id],
                    })
                else:
                    label_owner[key] = concept.concept_id

            for ref_kind in ("broader", "narrower", "related"):
                for target in getattr(concept, ref_kind):
                    if target not in by_id:
                        issues.append({
                            "severity": "warning",
                            "code": "missing_reference",
                            "message": f"{concept.concept_id} has {ref_kind} reference to unknown concept {target}",
                            "concept": concept.concept_id,
                            "target": target,
                        })

        cycles = SemanticTaxonomyService.detect_cycles(concepts)
        for cycle in cycles:
            issues.append({
                "severity": "error",
                "code": "taxonomy_cycle",
                "message": "SKOS broader/narrower hierarchy contains a cycle",
                "cycle": cycle,
            })

        return {
            "valid": not any(issue["severity"] == "error" for issue in issues),
            "issues": issues,
            "summary": {
                "concepts": len(concepts),
                "duplicate_labels": sum(1 for i in issues if i["code"] == "duplicate_label"),
                "cycles": len(cycles),
            },
        }

    @staticmethod
    def detect_cycles(concepts: Sequence[SkosConcept]) -> List[List[str]]:
        children: Dict[str, List[str]] = {concept.concept_id: [] for concept in concepts}
        by_id = {concept.concept_id: concept for concept in concepts}
        for concept in concepts:
            for parent_id in concept.broader:
                if parent_id in by_id:
                    children.setdefault(parent_id, []).append(concept.concept_id)
            for child_id in concept.narrower:
                if child_id in by_id:
                    children.setdefault(concept.concept_id, []).append(child_id)

        cycles: List[List[str]] = []
        visiting: List[str] = []
        visited: set[str] = set()

        def visit(node_id: str) -> None:
            if node_id in visiting:
                cycles.append(visiting[visiting.index(node_id):] + [node_id])
                return
            if node_id in visited:
                return
            visiting.append(node_id)
            for child_id in children.get(node_id, []):
                visit(child_id)
            visiting.pop()
            visited.add(node_id)

        for concept_id in children:
            visit(concept_id)
        return cycles

    @staticmethod
    def traverse(concepts: Sequence[SkosConcept], root_id: str, direction: str = "narrower", depth: int = 3) -> Dict[str, Any]:
        by_id = {concept.concept_id: concept for concept in concepts}
        if root_id not in by_id:
            return {"root": root_id, "nodes": [], "edges": [], "message": "Root concept not found"}

        depth = max(1, min(int(depth or 1), 10))
        queue: List[Tuple[str, int]] = [(root_id, 0)]
        visited: set[str] = set()
        edges: List[Dict[str, str]] = []

        while queue:
            current, level = queue.pop(0)
            if current in visited or level > depth:
                continue
            visited.add(current)
            concept = by_id[current]
            next_ids = concept.broader if direction == "broader" else concept.narrower
            for next_id in next_ids:
                if next_id not in by_id:
                    continue
                source, target = (current, next_id) if direction == "narrower" else (next_id, current)
                edges.append({"source": source, "target": target, "type": "skos:narrower"})
                queue.append((next_id, level + 1))

        return {
            "root": root_id,
            "direction": direction,
            "nodes": [SemanticTaxonomyService.to_dict(by_id[node_id]) for node_id in visited],
            "edges": edges,
        }

    @staticmethod
    def search(concepts: Sequence[SkosConcept], query: str, limit: int = 25) -> List[Dict[str, Any]]:
        q = str(query or "").strip().casefold().replace("*", "")
        if not q:
            return []
        limit = max(1, min(int(limit or 25), 100))
        by_id = {concept.concept_id: concept for concept in concepts}
        results: List[Dict[str, Any]] = []

        for concept in concepts:
            score = 0
            reasons: List[str] = []
            pref = concept.pref_label.casefold()
            alt = [label.casefold() for label in concept.alt_labels]
            definition = concept.definition.casefold()
            if pref == q:
                score += 100
                reasons.append("preferred label exact match")
            elif q in pref:
                score += 75
                reasons.append("preferred label contains query")
            if any(label == q for label in alt):
                score += 90
                reasons.append("synonym exact match")
            elif any(q in label for label in alt):
                score += 65
                reasons.append("synonym contains query")
            if q in definition:
                score += 35
                reasons.append("definition contains query")
            for ref_id in (*concept.broader, *concept.narrower, *concept.related):
                ref = by_id.get(ref_id)
                if ref and q in ref.pref_label.casefold():
                    score += 20
                    reasons.append("hierarchy/related concept match")
            for mapping_targets in concept.mappings.values():
                if any(q in target.casefold() for target in mapping_targets):
                    score += 30
                    reasons.append("mapping target match")
            if score:
                row = SemanticTaxonomyService.to_dict(concept)
                row.update({"score": score, "reasons": sorted(set(reasons))})
                results.append(row)
        return sorted(results, key=lambda row: (-row["score"], row["pref_label"].casefold()))[:limit]

    @staticmethod
    def to_dict(concept: SkosConcept) -> Dict[str, Any]:
        return {
            "concept_id": concept.concept_id,
            "scheme_id": concept.scheme_id,
            "pref_label": concept.pref_label,
            "alt_labels": list(concept.alt_labels),
            "definition": concept.definition,
            "broader": list(concept.broader),
            "narrower": list(concept.narrower),
            "related": list(concept.related),
            "mappings": {key: list(value) for key, value in concept.mappings.items()},
        }


class SkosNeo4jRepository:
    """Parameterized Cypher plans for SKOS storage.

    The app can execute these through the centralized Neo4j driver. Tests assert
    the generated Cypher remains parameterized; stable business keys are
    schemeId/conceptId and elementId() is only used by consumers at runtime.
    """

    @staticmethod
    def storage_plan(scheme: SkosConceptScheme, concepts: Sequence[SkosConcept]) -> List[Dict[str, Any]]:
        now = datetime.now(timezone.utc).isoformat()
        concept_rows = [
            {
                "conceptId": c.concept_id,
                "schemeId": c.scheme_id,
                "prefLabel": c.pref_label,
                "altLabels": list(c.alt_labels),
                "definition": c.definition,
                "updatedAt": now,
            }
            for c in concepts
        ]
        hierarchy_keys: set[Tuple[str, str]] = set()
        related_keys: set[Tuple[str, str]] = set()
        mapping_keys: set[Tuple[str, str, str]] = set()
        for concept in concepts:
            for parent in concept.broader:
                hierarchy_keys.add((concept.concept_id, parent))
            for child in concept.narrower:
                hierarchy_keys.add((child, concept.concept_id))
            for target in concept.related:
                related_keys.add((concept.concept_id, target))
            for mapping_type, targets in concept.mappings.items():
                for target in targets:
                    mapping_keys.add((concept.concept_id, target, mapping_type))

        hierarchy_rows = [
            {"childId": child_id, "parentId": parent_id}
            for child_id, parent_id in sorted(hierarchy_keys)
        ]
        related_rows = [
            {"sourceId": source_id, "targetId": target_id}
            for source_id, target_id in sorted(related_keys)
        ]
        mapping_rows = [
            {"sourceId": source_id, "targetIri": target_iri, "mappingType": mapping_type}
            for source_id, target_iri, mapping_type in sorted(mapping_keys)
        ]

        return [
            {
                "name": "skos_constraints",
                "cypher": "CREATE CONSTRAINT skos_concept_scheme_id IF NOT EXISTS FOR (s:SkosConceptScheme) REQUIRE s.schemeId IS UNIQUE",
                "params": {},
            },
            {
                "name": "skos_concept_constraint",
                "cypher": "CREATE CONSTRAINT skos_concept_id IF NOT EXISTS FOR (c:SkosConcept) REQUIRE c.conceptId IS UNIQUE",
                "params": {},
            },
            {
                "name": "upsert_scheme",
                "cypher": (
                    "MERGE (s:SkosConceptScheme {schemeId: $schemeId}) "
                    "SET s.prefLabel = $prefLabel, s.definition = $definition, "
                    "s.version = $version, s.updatedAt = $updatedAt"
                ),
                "params": {
                    "schemeId": scheme.scheme_id,
                    "prefLabel": scheme.pref_label,
                    "definition": scheme.definition,
                    "version": scheme.version,
                    "updatedAt": now,
                },
            },
            {
                "name": "upsert_concepts",
                "cypher": (
                    "UNWIND $rows AS row "
                    "MATCH (s:SkosConceptScheme {schemeId: row.schemeId}) "
                    "MERGE (c:SkosConcept {conceptId: row.conceptId}) "
                    "SET c.prefLabel = row.prefLabel, c.altLabels = row.altLabels, "
                    "c.definition = row.definition, c.schemeId = row.schemeId, c.updatedAt = row.updatedAt "
                    "MERGE (s)-[:HAS_CONCEPT]->(c)"
                ),
                "params": {"rows": concept_rows},
            },
            {
                "name": "upsert_hierarchy",
                "cypher": (
                    "UNWIND $rows AS row "
                    "MATCH (child:SkosConcept {conceptId: row.childId}) "
                    "MATCH (parent:SkosConcept {conceptId: row.parentId}) "
                    "MERGE (parent)-[:SKOS_NARROWER]->(child) "
                    "MERGE (child)-[:SKOS_BROADER]->(parent)"
                ),
                "params": {"rows": hierarchy_rows},
            },
            {
                "name": "upsert_related",
                "cypher": (
                    "UNWIND $rows AS row "
                    "MATCH (source:SkosConcept {conceptId: row.sourceId}) "
                    "MATCH (target:SkosConcept {conceptId: row.targetId}) "
                    "MERGE (source)-[:SKOS_RELATED]->(target)"
                ),
                "params": {"rows": related_rows},
            },
            {
                "name": "upsert_mappings",
                "cypher": (
                    "UNWIND $rows AS row "
                    "MATCH (source:SkosConcept {conceptId: row.sourceId}) "
                    "MERGE (target:ExternalSemanticResource {iri: row.targetIri}) "
                    "MERGE (source)-[r:SKOS_MAPPING {mappingType: row.mappingType}]->(target)"
                ),
                "params": {"rows": mapping_rows},
            },
        ]
