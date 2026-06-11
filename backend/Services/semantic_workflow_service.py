"""
Semantic workflow execution service.

These workflows are intentionally artifact-first: each run writes reviewable
outputs to WorkflowArtifactService before any destructive or graph-mutating
operation is introduced.
"""

import json
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from .ontology_taxonomy_service import OntologyTaxonomyService
from .ontology_upload_manager import OntologyUploadManager
from .unified_data_import import UnifiedDataImportService
from .workflow_artifact_service import WorkflowArtifactService


def _tokenize(value: str) -> List[str]:
    return [t for t in re.split(r"[^a-zA-Z0-9]+", value.lower()) if len(t) > 1]


def _jaccard(left: List[str], right: List[str]) -> float:
    lset, rset = set(left), set(right)
    if not lset or not rset:
        return 0.0
    return len(lset & rset) / len(lset | rset)


GENERIC_ONTOLOGY_TERMS = {
    "class",
    "entity",
    "item",
    "object",
    "part",
    "product",
    "resource",
    "thing",
    "type",
    "value",
}


class SemanticWorkflowService:
    LINK_BATCH_SIZE = 500
    AUTO_APPLY_CONFIDENCE = 0.82
    REVIEW_CONFIDENCE = 0.55
    AMBIGUITY_DELTA = 0.08
    TYPE_FIELDS = ("entity_type", "element_type", "type", "xsi:type", "class", "category", "part_type")
    FALLBACK_FIELDS = ("name",)

    @staticmethod
    def _new_task(workflow_id: str, source_filename: str = "") -> str:
        task_id = f"{workflow_id.replace('.', '-')}-{uuid.uuid4()}"
        WorkflowArtifactService.ensure_task(task_id, workflow_id=workflow_id, filename=source_filename)
        return task_id

    @staticmethod
    def _ontology_metadata(ontology_id: str) -> Dict[str, Any]:
        result = OntologyUploadManager.get_ontology(ontology_id)
        if result.get("status") != "success":
            resolved = SemanticWorkflowService._resolve_ontology_id(ontology_id)
            if not resolved or resolved == ontology_id:
                raise ValueError(result.get("error") or f"Ontology not found: {ontology_id}")
            result = OntologyUploadManager.get_ontology(resolved)
            if result.get("status") != "success":
                raise ValueError(result.get("error") or f"Ontology not found: {ontology_id}")
        return result["metadata"]

    @staticmethod
    def _resolve_ontology_id(ontology_ref: str) -> str:
        """Resolve a user-selected ontology reference to a stored ontology_id."""
        ref = str(ontology_ref or "").strip()
        if not ref:
            return ""
        direct = OntologyUploadManager.get_ontology(ref)
        if direct.get("status") == "success":
            return ref

        registry = OntologyUploadManager.list_ontologies()
        if registry.get("status") != "success":
            return ref

        for meta in registry.get("ontologies", []):
            ontology_id = str(meta.get("ontology_id") or "").strip()
            prefix = str(meta.get("prefix") or meta.get("ontology_prefix") or "").strip()
            if ref in {ontology_id, prefix}:
                return ontology_id or ref
        return ref

    @staticmethod
    def _read_ontology_file(meta: Dict[str, Any]) -> str:
        path = Path(meta.get("file_path", ""))
        if not path.exists():
            return ""
        try:
            return path.read_text(encoding="utf-8-sig", errors="replace")
        except Exception:
            return path.read_bytes().decode("utf-8", errors="replace")

    @staticmethod
    def _extract_terms(text: str) -> List[Dict[str, Any]]:
        candidates = re.findall(r"\b[A-Z][A-Za-z0-9_]{2,}\b|\b[a-z][a-z0-9_]{3,}\b", text or "")
        seen = {}
        for term in candidates:
            key = term.lower()
            if key in seen:
                seen[key]["frequency"] += 1
            else:
                seen[key] = {
                    "term": term,
                    "normalized": key,
                    "frequency": 1,
                    "tokens": _tokenize(term),
                }
        terms = sorted(seen.values(), key=lambda x: (-x["frequency"], x["normalized"]))
        return terms[:500]

    @staticmethod
    def _load_import_task(import_manifest: Dict[str, Any]) -> Dict[str, Any]:
        import_task_id = str((import_manifest or {}).get("task_id") or "").strip()
        if not import_task_id:
            raise ValueError("Import artifact manifest does not include a task_id")

        task = UnifiedDataImportService._restore_task(import_task_id)
        if not task:
            raise ValueError(f"Import task not found: {import_task_id}")

        if not task.get("parsed_rows"):
            path = UnifiedDataImportService._task_snapshot_path(import_task_id)
            parsed_name = task.get('_parsed_rows_file') or (path.name + '.parsed_rows.json')
            parsed_path = path.parent / parsed_name
            if not parsed_path.exists():
                raise ValueError(f"Parsed rows snapshot not found for import task: {import_task_id}")
            parsed_text = parsed_path.read_text(encoding='utf-8')
            task["parsed_rows"] = json.loads(parsed_text)

        return task

    @staticmethod
    def _candidate_display_value(row: Dict[str, Any]) -> str:
        for key in ("name", "entity_type", "element_type", "type", "part_type", "id"):
            value = row.get(key)
            if value:
                return str(value)
        return "Imported entity"

    @staticmethod
    def _normalized_key(value: Any) -> str:
        return UnifiedDataImportService._ontology_match_key(value)

    @staticmethod
    def _is_generic_term(value: str) -> bool:
        normalized = str(value or "").strip().lower()
        return normalized in GENERIC_ONTOLOGY_TERMS

    @classmethod
    def _collect_row_signals(cls, row: Dict[str, Any]) -> List[Dict[str, Any]]:
        signals: List[Dict[str, Any]] = []
        seen = set()

        def add_signal(raw_value: Any, source_field: str, signal_type: str, weight: float) -> None:
            value = str(raw_value or "").strip()
            if not value:
                return
            variants = [value]
            if ":" in value:
                variants.append(value.split(":")[-1])
            if "#" in value:
                variants.append(value.split("#")[-1])

            for variant in variants:
                normalized = cls._normalized_key(variant)
                if not normalized:
                    continue
                signature = (normalized, signal_type)
                if signature in seen:
                    continue
                seen.add(signature)
                signals.append({
                    "raw": variant,
                    "normalized": normalized,
                    "tokens": _tokenize(variant),
                    "source_field": source_field,
                    "signal_type": signal_type,
                    "weight": weight,
                })

        for field_name in cls.TYPE_FIELDS:
            add_signal(row.get(field_name), field_name, "type", 1.0 if field_name != "category" else 0.9)

        if not signals:
            for field_name in cls.FALLBACK_FIELDS:
                add_signal(row.get(field_name), field_name, "name", 0.6)

        return signals

    @classmethod
    def _score_link_candidate(cls, signal: Dict[str, Any], match: Dict[str, Any], row: Dict[str, Any]) -> float:
        score = 0.0
        signal_weight = float(signal.get("weight") or 0.0)
        signal_type = signal.get("signal_type")
        signal_tokens = signal.get("tokens") or []
        class_tokens = match.get("tokens") or []

        if signal.get("normalized") == match.get("normalized"):
            score += 0.72 * signal_weight

        overlap = _jaccard(signal_tokens, class_tokens)
        if overlap:
            score += 0.22 * overlap * signal_weight

        if signal_type == "type":
            score += 0.12
        else:
            score -= 0.08

        row_name = str(row.get("name") or "").strip()
        class_name = str(match.get("class_name") or "").strip()
        if row_name and class_name and row_name.lower() == class_name.lower():
            score += 0.08

        if match.get("is_generic"):
            score -= 0.28

        return max(0.0, min(1.0, round(score, 4)))

    @classmethod
    def _build_link_candidates(cls, rows: List[Dict[str, Any]], ontology_prefix: str, import_task_id: str) -> List[Dict[str, Any]]:
        class_lookup = UnifiedDataImportService._load_ontology_class_lookup(ontology_prefix)
        candidates: List[Dict[str, Any]] = []

        for row in rows:
            row_key = row.get("import_row_key") or row.get("id")
            if not row_key:
                continue

            scored_matches: Dict[str, Dict[str, Any]] = {}
            for signal in cls._collect_row_signals(row):
                matches = class_lookup.get(signal["normalized"], [])
                for match in matches:
                    score = cls._score_link_candidate(signal, match, row)
                    if score < cls.REVIEW_CONFIDENCE:
                        continue
                    existing = scored_matches.get(match["element_id"])
                    if existing and existing["confidence"] >= score:
                        continue
                    scored_matches[match["element_id"]] = {
                        "import_id": import_task_id,
                        "import_row_key": row_key,
                        "source_term": cls._candidate_display_value(row),
                        "ontology_term": match["class_name"],
                        "ontology_class_element_id": match["element_id"],
                        "confidence": score,
                        "mapping": ontology_prefix,
                        "match_source": signal["source_field"],
                        "signal_type": signal["signal_type"],
                        "generic_match": bool(match.get("is_generic")),
                    }

            if not scored_matches:
                continue

            ranked = sorted(
                scored_matches.values(),
                key=lambda item: (-item["confidence"], item["generic_match"], item["ontology_term"].lower()),
            )
            best_confidence = ranked[0]["confidence"]
            ambiguous_count = sum(
                1 for item in ranked
                if best_confidence - item["confidence"] <= cls.AMBIGUITY_DELTA
            )

            for idx, item in enumerate(ranked[:3]):
                item["rank"] = idx + 1
                item["ambiguous"] = ambiguous_count > 1 and item["rank"] <= ambiguous_count
                item["selected_for_apply"] = (
                    idx == 0
                    and not item["ambiguous"]
                    and not item["generic_match"]
                    and item["confidence"] >= cls.AUTO_APPLY_CONFIDENCE
                )
                candidates.append(item)

        return candidates

    @classmethod
    def _apply_instance_links(cls, candidates: List[Dict[str, Any]]) -> int:
        if not candidates:
            return 0
        try:
            try:
                from core.graph import query_with_timeout as _query_with_timeout
            except ModuleNotFoundError:
                from ..core.graph import query_with_timeout as _query_with_timeout

            link_cypher = """
            UNWIND $rows AS row
            MATCH (n {import_row_key: row.import_row_key, import_id: row.import_id})
            MATCH (c:OntologyClass)
            WHERE elementId(c) = row.ontology_class_element_id
            MERGE (n)-[rel:INSTANCE_OF]->(c)
            SET rel.mapping = row.mapping,
                rel.class_name = row.ontology_term,
                rel.import_id = row.import_id,
                rel.linked_by = 'semantic_bridge'
            RETURN count(rel) AS linked
            """

            linked_total = 0
            for idx in range(0, len(candidates), cls.LINK_BATCH_SIZE):
                batch = candidates[idx:idx + cls.LINK_BATCH_SIZE]
                result = _query_with_timeout(link_cypher, {"rows": batch}) or []
                if result and isinstance(result[0], dict):
                    linked_total += int(result[0].get("linked") or 0)
            return linked_total
        except Exception as exc:
            raise ValueError(f"Failed to apply semantic links: {exc}") from exc

    @classmethod
    def execute(cls, workflow_id: str, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        payload = payload or {}
        handlers = {
            "instance.link": cls.link_instances,
            "ontology.merge": cls.merge_ontologies,
            "ontology.validate": cls.validate_ontology,
            "dictionary.generate": cls.generate_dictionary,
            "taxonomy.generate": cls.generate_taxonomy,
            "graph.chunk": cls.chunk_graph,
        }
        workflow_id = str(workflow_id or "").strip()
        handler = handlers.get(workflow_id)
        if not handler:
            raise ValueError(f"Unsupported workflow: {workflow_id}")
        return handler(payload)

    @classmethod
    def validate_ontology(cls, payload: Dict[str, Any]) -> Dict[str, Any]:
        ontology_id = cls._resolve_ontology_id(payload.get("ontology_id"))
        if not ontology_id:
            raise ValueError("ontology_id is required")
        meta = cls._ontology_metadata(ontology_id)
        text = cls._read_ontology_file(meta)
        task_id = cls._new_task("ontology.validate", meta.get("original_filename", ""))

        findings = []
        if not meta.get("prefix"):
            findings.append({"severity": "error", "message": "Ontology prefix is missing"})
        if not meta.get("ontology_name"):
            findings.append({"severity": "warning", "message": "Ontology name is missing"})
        if not Path(meta.get("file_path", "")).exists():
            findings.append({"severity": "error", "message": "Source ontology file is missing"})
        if text and len(text.strip()) < 20:
            findings.append({"severity": "warning", "message": "Ontology file content is very small"})
        if text and "http://" not in text and "https://" not in text and "xmlns" not in text:
            findings.append({"severity": "info", "message": "No namespace URI detected in source text"})

        report = {
            "workflow_id": "ontology.validate",
            "ontology_id": ontology_id,
            "ontology_name": meta.get("ontology_name"),
            "prefix": meta.get("prefix"),
            "file_type": meta.get("file_type"),
            "checked_at": datetime.now().isoformat(),
            "findings": findings,
            "summary": {
                "errors": sum(1 for f in findings if f["severity"] == "error"),
                "warnings": sum(1 for f in findings if f["severity"] == "warning"),
                "infos": sum(1 for f in findings if f["severity"] == "info"),
            },
        }
        WorkflowArtifactService.write_json(task_id, "validation", "ontology_validation_report.json", report, "validation_report")
        return {"task_id": task_id, "status": "completed", "result": report, "artifact_manifest": WorkflowArtifactService.get_manifest(task_id)}

    @classmethod
    def generate_dictionary(cls, payload: Dict[str, Any]) -> Dict[str, Any]:
        ontology_id = cls._resolve_ontology_id(payload.get("ontology_id"))
        if not ontology_id:
            raise ValueError("ontology_id is required")
        meta = cls._ontology_metadata(ontology_id)
        text = cls._read_ontology_file(meta)
        task_id = cls._new_task("dictionary.generate", meta.get("original_filename", ""))
        terms = cls._extract_terms(text)
        dictionary = {
            "workflow_id": "dictionary.generate",
            "ontology_id": ontology_id,
            "prefix": meta.get("prefix"),
            "generated_at": datetime.now().isoformat(),
            "terms": [
                {
                    "term": t["term"],
                    "definition": "",
                    "frequency": t["frequency"],
                    "source": meta.get("original_filename"),
                    "status": "needs_review",
                }
                for t in terms
            ],
        }
        WorkflowArtifactService.write_json(task_id, "reports", "data_dictionary.json", dictionary, "data_dictionary")
        csv_lines = ["term,frequency,status,source"] + [
            f"{json.dumps(t['term'])},{t['frequency']},needs_review,{json.dumps(meta.get('original_filename', ''))}"
            for t in terms
        ]
        WorkflowArtifactService.write_text(task_id, "reports", "data_dictionary.csv", "\n".join(csv_lines), "data_dictionary_csv")
        return {"task_id": task_id, "status": "completed", "result": dictionary, "artifact_manifest": WorkflowArtifactService.get_manifest(task_id)}

    @classmethod
    def generate_taxonomy(cls, payload: Dict[str, Any]) -> Dict[str, Any]:
        ontology_id = cls._resolve_ontology_id(payload.get("ontology_id"))
        if not ontology_id:
            raise ValueError("ontology_id is required")
        meta = cls._ontology_metadata(ontology_id)
        text = cls._read_ontology_file(meta)
        task_id = cls._new_task("taxonomy.generate", meta.get("original_filename", ""))
        terms = cls._extract_terms(text)
        groups: Dict[str, List[str]] = {}
        for item in terms:
            key = item["normalized"][0].upper()
            groups.setdefault(key, []).append(item["term"])
        taxonomy = {
            "workflow_id": "taxonomy.generate",
            "ontology_id": ontology_id,
            "root": meta.get("ontology_name") or meta.get("prefix") or ontology_id,
            "generated_at": datetime.now().isoformat(),
            "children": [
                {"label": letter, "children": [{"label": term} for term in sorted(set(values))[:50]]}
                for letter, values in sorted(groups.items())
            ],
        }
        WorkflowArtifactService.write_json(task_id, "reports", "taxonomy.json", taxonomy, "taxonomy")
        return {"task_id": task_id, "status": "completed", "result": taxonomy, "artifact_manifest": WorkflowArtifactService.get_manifest(task_id)}

    @classmethod
    def merge_ontologies(cls, payload: Dict[str, Any]) -> Dict[str, Any]:
        source_id = cls._resolve_ontology_id(payload.get("source_ontology_id") or payload.get("from_ontology_id"))
        target_id = cls._resolve_ontology_id(payload.get("target_ontology_id") or payload.get("to_ontology_id"))
        if not source_id or not target_id:
            raise ValueError("source_ontology_id and target_ontology_id are required")
        source = cls._ontology_metadata(source_id)
        target = cls._ontology_metadata(target_id)
        source_reasoning = OntologyTaxonomyService.get_reasoning(source_id)
        target_reasoning = OntologyTaxonomyService.get_reasoning(target_id)
        task_id = cls._new_task("ontology.merge", f"{source_id}__{target_id}")

        def normalized_label(value: str) -> str:
            return str(value or "").strip().lower()

        def semantic_entries(reasoning: Dict[str, Any], key: str, entry_type: str) -> List[Dict[str, Any]]:
            rows = []
            for row in reasoning.get(key, []) or []:
                label = str(row.get("label") or row.get("name") or row.get("iri") or "").strip()
                iri = str(row.get("iri") or "").strip()
                if not label and not iri:
                    continue
                rows.append({
                    "type": entry_type,
                    "label": label or iri,
                    "normalized": normalized_label(label or iri),
                    "iri": iri,
                    "domain": sorted(item.get("label") or item.get("iri") or "" for item in row.get("domain", []) or []),
                    "range": sorted(item.get("label") or item.get("iri") or "" for item in row.get("range", []) or []),
                })
            return rows

        source_classes = semantic_entries(source_reasoning, "classes", "class")
        target_classes = semantic_entries(target_reasoning, "classes", "class")
        source_properties = semantic_entries(source_reasoning, "object_properties", "object_property") + semantic_entries(source_reasoning, "datatype_properties", "datatype_property")
        target_properties = semantic_entries(target_reasoning, "object_properties", "object_property") + semantic_entries(target_reasoning, "datatype_properties", "datatype_property")

        target_classes_by_norm = {entry["normalized"]: entry for entry in target_classes if entry["normalized"]}
        target_properties_by_norm = {entry["normalized"]: entry for entry in target_properties if entry["normalized"]}

        overlaps: List[Dict[str, Any]] = []
        additions: List[Dict[str, Any]] = []
        conflicts: List[Dict[str, Any]] = []

        for source_entry in [*source_classes, *source_properties]:
            target_entry = (
                target_classes_by_norm.get(source_entry["normalized"])
                if source_entry["type"] == "class"
                else target_properties_by_norm.get(source_entry["normalized"])
            )
            if not target_entry:
                additions.append({
                    "label": source_entry["label"],
                    "type": source_entry["type"],
                    "action": "add_candidate",
                })
                continue

            overlaps.append({
                "label": source_entry["label"],
                "type": source_entry["type"],
                "source_iri": source_entry["iri"],
                "target_iri": target_entry["iri"],
                "match_basis": "iri" if source_entry["iri"] and source_entry["iri"] == target_entry["iri"] else "label",
                "confidence": 1.0 if source_entry["iri"] and source_entry["iri"] == target_entry["iri"] else 0.82,
            })

            if source_entry["type"] != "class":
                if source_entry["domain"] != target_entry["domain"] or source_entry["range"] != target_entry["range"]:
                    conflicts.append({
                        "label": source_entry["label"],
                        "type": source_entry["type"],
                        "issue": "domain_range_mismatch",
                        "source_domain": source_entry["domain"],
                        "target_domain": target_entry["domain"],
                        "source_range": source_entry["range"],
                        "target_range": target_entry["range"],
                    })

        source_subclasses = {
            (
                normalized_label(edge.get("source_label") or edge.get("source") or ""),
                normalized_label(edge.get("target_label") or edge.get("target") or ""),
            )
            for edge in source_reasoning.get("subclass_edges", []) or []
            if edge.get("source_label") or edge.get("source")
        }
        target_subclasses = {
            (
                normalized_label(edge.get("source_label") or edge.get("source") or ""),
                normalized_label(edge.get("target_label") or edge.get("target") or ""),
            )
            for edge in target_reasoning.get("subclass_edges", []) or []
            if edge.get("source_label") or edge.get("source")
        }
        missing_subclasses = sorted(source_subclasses - target_subclasses)[:100]
        report = {
            "workflow_id": "ontology.merge",
            "source_ontology_id": source_id,
            "target_ontology_id": target_id,
            "generated_at": datetime.now().isoformat(),
            "overlaps": overlaps[:200],
            "additions": additions[:300],
            "conflicts": conflicts[:200],
            "subclass_gaps": [
                {"child": child, "parent": parent, "issue": "missing_in_target"}
                for child, parent in missing_subclasses
            ],
            "summary": {
                "overlap_count": len(overlaps),
                "addition_count": len(additions),
                "conflict_count": len(conflicts),
                "subclass_gap_count": len(source_subclasses - target_subclasses),
                "source_classes": len(source_classes),
                "target_classes": len(target_classes),
                "source_properties": len(source_properties),
                "target_properties": len(target_properties),
            },
        }
        WorkflowArtifactService.write_json(task_id, "reports", "merge_plan.json", report, "merge_plan")
        return {"task_id": task_id, "status": "completed", "result": report, "artifact_manifest": WorkflowArtifactService.get_manifest(task_id)}

    @classmethod
    def link_instances(cls, payload: Dict[str, Any]) -> Dict[str, Any]:
        ontology_id = cls._resolve_ontology_id(payload.get("ontology_id"))
        if not ontology_id:
            raise ValueError("ontology_id is required")
        meta = cls._ontology_metadata(ontology_id)
        import_manifest = payload.get("import_artifact_manifest") or {}
        import_task = cls._load_import_task(import_manifest)
        import_task_id = str(import_task.get("task_id") or import_manifest.get("task_id") or "")
        apply_links = payload.get("apply_links", True)
        task_id = cls._new_task("instance.link", meta.get("original_filename", ""))
        rows = import_task.get("parsed_rows") or []
        ontology_scope = meta.get("prefix") or meta.get("ontology_prefix") or ontology_id
        candidates = cls._build_link_candidates(rows, ontology_scope, import_task_id)
        approved_candidates = [candidate for candidate in candidates if candidate.get("selected_for_apply")]
        applied_links = cls._apply_instance_links(approved_candidates) if apply_links else 0
        report = {
            "workflow_id": "instance.link",
            "ontology_id": ontology_id,
            "ontology_scope": ontology_scope,
            "import_task_id": import_task_id,
            "generated_at": datetime.now().isoformat(),
            "candidates": sorted(candidates, key=lambda x: -x["confidence"])[:200],
            "summary": {
                "candidate_count": len(candidates),
                "selected_for_apply": len(approved_candidates),
                "high_confidence_candidates": sum(1 for candidate in candidates if candidate["confidence"] >= cls.AUTO_APPLY_CONFIDENCE),
                "ambiguous_candidates": sum(1 for candidate in candidates if candidate.get("ambiguous")),
                "generic_matches_filtered": sum(1 for candidate in candidates if candidate.get("generic_match") and not candidate.get("selected_for_apply")),
                "applied_links": applied_links,
                "committed": bool(apply_links and applied_links >= 0),
            },
        }
        WorkflowArtifactService.write_json(task_id, "reports", "link_candidates.json", report, "link_candidates")
        return {"task_id": task_id, "status": "completed", "result": report, "artifact_manifest": WorkflowArtifactService.get_manifest(task_id)}

    @classmethod
    def chunk_graph(cls, payload: Dict[str, Any]) -> Dict[str, Any]:
        ontology_id = cls._resolve_ontology_id(payload.get("ontology_id"))
        chunk_size = int(payload.get("chunk_size") or 80)
        if not ontology_id:
            raise ValueError("ontology_id is required")
        meta = cls._ontology_metadata(ontology_id)
        terms = cls._extract_terms(cls._read_ontology_file(meta))
        task_id = cls._new_task("graph.chunk", meta.get("original_filename", ""))
        chunks = []
        for idx in range(0, len(terms), chunk_size):
            subset = terms[idx:idx + chunk_size]
            chunks.append({
                "chunk_id": f"chunk_{idx // chunk_size + 1:04d}",
                "term_count": len(subset),
                "terms": [t["term"] for t in subset],
            })
        manifest = {
            "workflow_id": "graph.chunk",
            "ontology_id": ontology_id,
            "chunk_size": chunk_size,
            "generated_at": datetime.now().isoformat(),
            "chunks": chunks,
            "summary": {"chunk_count": len(chunks), "term_count": len(terms)},
        }
        WorkflowArtifactService.write_json(task_id, "reports", "chunk_manifest.json", manifest, "chunk_manifest")
        for chunk in chunks:
            WorkflowArtifactService.write_json(task_id, "reports", f"{chunk['chunk_id']}.json", chunk, "graph_chunk")
        return {"task_id": task_id, "status": "completed", "result": manifest, "artifact_manifest": WorkflowArtifactService.get_manifest(task_id)}
