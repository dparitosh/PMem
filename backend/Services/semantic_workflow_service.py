"""
Semantic workflow execution service.

These workflows are intentionally artifact-first: each run writes reviewable
outputs to WorkflowArtifactService before any destructive or graph-mutating
operation is introduced.
"""

import json
import logging
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from .ontology_reasoning_service import OntologyReasoningService
from .ontology_upload_manager import OntologyUploadManager
from .unified_data_import import UnifiedDataImportService
from .workflow_artifact_service import WorkflowArtifactService

logger = logging.getLogger(__name__)


def _tokenize(value: str) -> List[str]:
    normalized = re.sub(r"([a-z])([A-Z])", r"\1 \2", str(value or ""))
    return [t for t in re.split(r"[^a-zA-Z0-9]+", normalized.lower()) if len(t) > 1]


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
    METADATA_FIELDS = (
        ("manifest.filename", "filename", 0.55),
        ("manifest.file_type", "file_type", 0.45),
        ("manifest.workflow_id", "workflow_id", 0.3),
        ("manifest.ontology_mapping", "stats.ontology_mapping", 0.4),
        ("manifest.ontology_prefix", "stats.ontology_prefix", 0.5),
        ("manifest.ontology_name", "stats.ontology_name", 0.45),
        ("manifest.namespace", "stats.namespace", 0.42),
        ("manifest.source_ontology", "stats.source_ontology", 0.35),
    )

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

    @classmethod
    def _semantic_terms_for_ontology(cls, ontology_id: str, meta: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Prefer Owlready2 semantic terms over raw ontology text scanning."""
        try:
            reasoning = OntologyReasoningService.get_reasoning(ontology_id)
            terms: List[Dict[str, Any]] = []
            seen: set[str] = set()
            for item in OntologyReasoningService.iter_semantic_terms(reasoning):
                term = str(item.get("label") or item.get("name") or "").strip()
                if not term:
                    continue
                normalized = cls._normalized_key(term)
                if not normalized or normalized in seen:
                    continue
                seen.add(normalized)
                terms.append({
                    "term": term,
                    "normalized": normalized,
                    "frequency": 1,
                    "tokens": _tokenize(term),
                    "semantic_type": item.get("target_ontology_type") or "OntologyTerm",
                    "iri": item.get("element_id") or item.get("iri") or item.get("uri"),
                    "domain": item.get("domain") or [],
                    "range": item.get("range") or [],
                    "source": "owlready2",
                })
            if terms:
                return sorted(terms, key=lambda item: (item.get("semantic_type", ""), item["term"].lower()))[:500]
        except Exception as exc:
            logger.info("Owlready2 term extraction fallback for %s: %s", ontology_id, exc)

        terms = cls._extract_terms(cls._read_ontology_file(meta))
        for term in terms:
            term.setdefault("semantic_type", "RawTerm")
            term.setdefault("source", "text_fallback")
        return terms
    @classmethod
    def _write_ontology_graph_exports(cls, task_id: str, source_id: str, target_id: str) -> None:
        """Pre-generate merged ontology export artifacts to avoid request-time serialization timeouts."""
        try:
            from rdflib import Graph as RDFGraph
            graph = RDFGraph()
            loaded = []
            for ontology_id in (source_id, target_id):
                context = OntologyReasoningService.semantic_context(ontology_id)
                path = Path(context.get("file_path") or context.get("source_file_path") or "")
                if not path.exists():
                    continue
                formats = ["turtle", "xml", "n3"] if path.suffix.lower() == ".ttl" else ["xml", "turtle", "n3"]
                for fmt in formats:
                    try:
                        graph.parse(str(path), format=fmt)
                        loaded.append(path.name)
                        break
                    except Exception:
                        continue
            if not graph:
                return
            for filename, fmt, artifact_type in (
                ("merged_ontology.ttl", "turtle", "ontology_export_ttl"),
                ("merged_ontology.rdf", "xml", "ontology_export_rdf"),
                ("merged_ontology.owl", "pretty-xml", "ontology_export_owl"),
                ("merged_ontology.jsonld", "json-ld", "ontology_export_jsonld"),
            ):
                WorkflowArtifactService.write_text(task_id, "ontology", filename, str(graph.serialize(format=fmt)), artifact_type, {"source_ontology_id": source_id, "target_ontology_id": target_id, "source_files": loaded})
        except Exception as exc:
            logger.warning("Merged ontology export generation failed: %s", exc)

    @classmethod
    def _write_bridge_mapping_exports(cls, task_id: str, report: Dict[str, Any]) -> None:
        """Write Semantic Bridge mapping exports as JSON-LD and Turtle artifacts."""
        try:
            candidates = report.get("candidate_mappings") or report.get("candidates") or []
            if not candidates:
                return
            graph_jsonld = {"@context": {"bridge": "http://depo-onto.local/semantic-bridge#", "skos": "http://www.w3.org/2004/02/skos/core#"}, "@graph": []}
            ttl_lines = ["@prefix bridge: <http://depo-onto.local/semantic-bridge#> .", "@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .", ""]
            for idx, row in enumerate(candidates[:5000], start=1):
                source = str(row.get("source_name") or row.get("source_field") or row.get("import_row_key") or "").replace('"', '\\"')
                target = str(row.get("ontology_term") or "").replace('"', '\\"')
                target_iri = str(row.get("target_ontology_iri") or row.get("ontology_class_element_id") or "").replace('"', '\\"')
                source_type = str(row.get("source_type") or "Entity")
                target_type = str(row.get("target_ontology_type") or "Class")
                confidence = float(row.get("confidence") or 0)
                validation = str(row.get("validation_status") or "unknown")
                mapping_type = str(row.get("mapping_type") or "relatedMatch")
                subject = f"bridge:mapping_{idx:06d}"
                graph_jsonld["@graph"].append({"@id": subject, "@type": "bridge:SemanticBridgeMapping", "bridge:sourceField": source, "bridge:targetOntologyIRI": target_iri, "bridge:targetOntologyType": target_type, "bridge:confidenceScore": confidence, "bridge:validationStatus": validation, "bridge:mappingType": mapping_type})
                ttl_lines.extend([f"{subject} a bridge:SemanticBridgeMapping ;", f"  bridge:sourceField \"{source}\" ;", f"  bridge:sourceType \"{source_type}\" ;", f"  bridge:targetOntologyIRI \"{target_iri}\" ;", f"  bridge:targetOntologyType \"{target_type}\" ;", f"  bridge:targetLabel \"{target}\" ;", f"  bridge:confidenceScore \"{confidence:.4f}\"^^xsd:decimal ;", f"  bridge:validationStatus \"{validation}\" ;", f"  bridge:mappingType \"{mapping_type}\" .", ""])
            WorkflowArtifactService.write_json(task_id, "ontology", "semantic_bridge_mappings.jsonld", graph_jsonld, "semantic_bridge_jsonld")
            WorkflowArtifactService.write_text(task_id, "ontology", "semantic_bridge_mappings.ttl", "\n".join(ttl_lines), "semantic_bridge_ttl")
        except Exception as exc:
            logger.warning("Semantic Bridge export generation failed: %s", exc)
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

    @classmethod
    def _classify_source_row(cls, row: Dict[str, Any]) -> str:
        """Infer a bridge source kind from the imported row shape."""
        keys = {str(key).lower() for key in (row or {}).keys()}
        values = [
            str(row.get(key) or "").strip().lower()
            for key in ("entity_type", "element_type", "type", "xsi:type", "class", "category", "part_type", "name")
            if row.get(key)
        ]
        relationship_markers = (
            "ref",
            "refs",
            "href",
            "idref",
            "instance",
            "related",
            "source",
            "target",
            "parent",
            "child",
        )
        metadata_markers = (
            "filename",
            "workflow_id",
            "namespace",
            "ontology_prefix",
            "ontology_name",
            "source_ontology",
            "manifest",
            "provenance",
        )
        attribute_markers = (
            "value",
            "text",
            "description",
            "comment",
            "label",
            "datatype",
        )

        if any(any(marker in key for marker in relationship_markers) for key in keys):
            return "Relationship"
        if any(any(marker in key for marker in metadata_markers) for key in keys):
            return "Metadata"
        if any(any(marker in key for marker in attribute_markers) for key in keys):
            return "Attribute"
        if any(value in {"relationship", "relations", "edge", "link"} for value in values):
            return "Relationship"
        if any(value in {"attribute", "datatype", "property", "value"} for value in values):
            return "Attribute"
        return "Entity"

    @classmethod
    def _load_ontology_term_lookup(cls, ontology_prefix: str) -> Dict[str, List[Dict[str, Any]]]:
        """Load ontology classes and properties into a bridge lookup table."""
        ontology_identifier = cls._resolve_ontology_id(ontology_prefix) or ontology_prefix
        try:
            lookup = OntologyReasoningService.build_term_lookup(
                ontology_identifier,
                normalizer=cls._normalized_key,
                tokenizer=_tokenize,
                generic_checker=cls._is_generic_term,
            )
            if lookup:
                return lookup
        except Exception as exc:
            logger.info(f"Ontology reasoning lookup fallback for '{ontology_prefix}': {exc}")

        try:
            reasoning = OntologyReasoningService.get_reasoning(ontology_identifier)
        except Exception as exc:
            logger.info(f"Ontology term lookup fallback for '{ontology_prefix}': {exc}")
            return {}

        lookup: Dict[str, List[Dict[str, Any]]] = {}
        for item in OntologyReasoningService.iter_semantic_terms(reasoning):
            label = str(item.get("label") or "").strip()
            normalized = cls._normalized_key(label)
            if not normalized:
                continue
            entry = {
                "element_id": item.get("element_id") or label,
                "class_name": label,
                "term_name": label,
                "prefix": item.get("ontology_prefix") or reasoning.get("prefix") or ontology_prefix,
                "normalized": normalized,
                "tokens": _tokenize(label),
                "is_generic": cls._is_generic_term(label),
                "target_ontology_type": item.get("target_ontology_type") or "Class",
                "domain": item.get("domain") or [],
                "range": item.get("range") or [],
            }
            lookup.setdefault(normalized, []).append(entry)
        return lookup

    @staticmethod
    def _read_nested_value(payload: Dict[str, Any], dotted_key: str) -> Any:
        current: Any = payload
        for part in dotted_key.split("."):
            if not isinstance(current, dict):
                return None
            current = current.get(part)
        return current

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
    def _collect_manifest_signals(cls, import_task: Dict[str, Any]) -> List[Dict[str, Any]]:
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
            if "/" in value or "\\" in value:
                stem = Path(value).stem
                if stem:
                    variants.append(stem)

            for variant in variants:
                normalized = cls._normalized_key(variant)
                if not normalized:
                    continue
                signature = (normalized, source_field)
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

        for source_field, dotted_key, weight in cls.METADATA_FIELDS:
            add_signal(cls._read_nested_value(import_task, dotted_key), source_field, "metadata", weight)

        source_filename = (import_task.get("filename") or import_task.get("source_filename") or "").strip()
        if source_filename:
            add_signal(Path(source_filename).stem, "manifest.filename_stem", "metadata", 0.6)

        preview = import_task.get("preview_data") or {}
        sample_rows = preview.get("sample_rows") or []
        if sample_rows:
            first_row = sample_rows[0] if isinstance(sample_rows[0], dict) else {}
            for key in cls.TYPE_FIELDS + cls.FALLBACK_FIELDS:
                add_signal(first_row.get(key), f"preview.{key}", "preview", 0.5)

        return signals

    @classmethod
    def _score_link_candidate(cls, signal: Dict[str, Any], match: Dict[str, Any], row: Dict[str, Any], source_type: str) -> float:
        score = 0.0
        signal_weight = float(signal.get("weight") or 0.0)
        signal_type = signal.get("signal_type")
        signal_tokens = signal.get("tokens") or []
        class_tokens = match.get("tokens") or []
        target_type = str(match.get("target_ontology_type") or "Class").strip()
        source_type = str(source_type or "Entity").strip()

        if signal.get("normalized") == match.get("normalized"):
            score += 0.72 * signal_weight

        overlap = _jaccard(signal_tokens, class_tokens)
        if overlap:
            score += 0.22 * overlap * signal_weight

        if signal_type == "type":
            score += 0.12
        elif signal_type == "metadata":
            score += 0.18
        else:
            score -= 0.08

        if source_type == "Attribute" and target_type in {"DatatypeProperty", "DataProperty"}:
            score += 0.2
        elif source_type == "Relationship" and target_type == "ObjectProperty":
            score += 0.2
        elif source_type == "Entity" and target_type == "Class":
            score += 0.16
        elif source_type == "Metadata" and target_type in {"AnnotationProperty", "Class"}:
            score += 0.1
        else:
            score -= 0.05

        row_name = str(row.get("name") or "").strip()
        class_name = str(match.get("class_name") or match.get("term_name") or "").strip()
        if row_name and class_name and row_name.lower() == class_name.lower():
            score += 0.08

        if match.get("is_generic"):
            score -= 0.28

        return max(0.0, min(1.0, round(score, 4)))

    @classmethod
    def _validate_candidate_pair(cls, source_type: str, target_type: str, match: Dict[str, Any], row: Dict[str, Any]) -> Dict[str, Any]:
        result = OntologyReasoningService.validate_mapping(source_type, target_type, match, row)
        return {
            "is_valid": result.get("status") != "invalid",
            "status": result.get("status", "valid"),
            "errors": result.get("errors", []),
            "warnings": result.get("warnings", []),
        }

    @classmethod
    def _build_link_candidates(
        cls,
        rows: List[Dict[str, Any]],
        ontology_prefix: str,
        import_task_id: str,
        import_task: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        class_lookup = UnifiedDataImportService._load_ontology_class_lookup(ontology_prefix)
        term_lookup = cls._load_ontology_term_lookup(ontology_prefix)
        for key, values in class_lookup.items():
            existing_values = term_lookup.setdefault(key, [])
            existing_ids = {str(item.get("element_id") or item.get("iri") or item.get("class_name") or "") for item in existing_values}
            for value in values:
                value_id = str(value.get("element_id") or value.get("iri") or value.get("class_name") or "")
                if value_id and value_id in existing_ids:
                    continue
                existing_values.append({**value, "target_ontology_type": value.get("target_ontology_type") or "Class"})
        candidates: List[Dict[str, Any]] = []
        metadata_signals = cls._collect_manifest_signals(import_task or {})

        for row in rows:
            row_key = row.get("import_row_key") or row.get("id")
            if not row_key:
                continue

            source_type = cls._classify_source_row(row)
            scored_matches: Dict[str, Dict[str, Any]] = {}
            for signal in [*cls._collect_row_signals(row), *metadata_signals]:
                matches = term_lookup.get(signal["normalized"], [])
                for match in matches:
                    target_type = match.get("target_ontology_type") or "Class"
                    validation = cls._validate_candidate_pair(source_type, target_type, match, row)
                    if not validation["is_valid"]:
                        continue
                    score = cls._score_link_candidate(signal, match, row, source_type)
                    if score < cls.REVIEW_CONFIDENCE:
                        continue
                    existing = scored_matches.get(match["element_id"])
                    if existing and existing["confidence"] >= score:
                        continue
                    scored_matches[match["element_id"]] = {
                        "import_id": import_task_id,
                        "import_row_key": row_key,
                        "source_term": cls._candidate_display_value(row),
                        "source_type": source_type,
                        "ontology_term": match["class_name"],
                        "ontology_class_element_id": match["element_id"],
                        "target_ontology_type": target_type,
                        "mapping_type": "closeMatch" if score < cls.AUTO_APPLY_CONFIDENCE else "exactMatch",
                        "validation_status": validation["status"],
                        "validation_errors": validation["errors"],
                        "validation_warnings": validation["warnings"],
                        "confidence": score,
                        "mapping": ontology_prefix,
                        "match_source": signal["source_field"],
                        "signal_type": signal["signal_type"],
                        "generic_match": bool(match.get("is_generic")),
                        "evidence": sorted({
                            *(existing.get("evidence", []) if existing else []),
                            signal["source_field"],
                        }),
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
                eligible_for_auto_apply = (
                    item.get("validation_status") in {"valid", "warning"}
                    and idx == 0
                    and not item["ambiguous"]
                    and not item["generic_match"]
                    and item["confidence"] >= cls.AUTO_APPLY_CONFIDENCE
                )
                item["validation_status"] = "auto_approved" if eligible_for_auto_apply else item.get("validation_status", "needs_review")
                item["selected_for_apply"] = eligible_for_auto_apply
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
            MATCH (target)
            WHERE elementId(target) = row.ontology_class_element_id
            MERGE (n)-[bridge:SEMANTICALLY_MAPPED_TO]->(target)
            SET bridge.mapping = row.mapping,
                bridge.ontology_term = row.ontology_term,
                bridge.target_ontology_type = row.target_ontology_type,
                bridge.source_type = row.source_type,
                bridge.confidence = row.confidence,
                bridge.mapping_type = row.mapping_type,
                bridge.validation_status = row.validation_status,
                bridge.import_id = row.import_id,
                bridge.linked_by = 'semantic_bridge'
            FOREACH (_ IN CASE WHEN row.target_ontology_type = 'Class' THEN [1] ELSE [] END |
                MERGE (n)-[inst:INSTANCE_OF]->(target)
                SET inst.mapping = row.mapping,
                    inst.class_name = row.ontology_term,
                    inst.import_id = row.import_id,
                    inst.linked_by = 'semantic_bridge'
            )
            RETURN count(bridge) AS linked
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
        task_id = cls._new_task("dictionary.generate", meta.get("original_filename", ""))
        terms = cls._semantic_terms_for_ontology(ontology_id, meta)
        dictionary = {
            "workflow_id": "dictionary.generate",
            "ontology_id": ontology_id,
            "prefix": meta.get("prefix"),
            "term_source": terms[0].get("source") if terms else "empty",
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
            f"{json.dumps(t['term'])},{t['frequency']},needs_review,{json.dumps(t.get('source') or meta.get('original_filename', ''))}"
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
        task_id = cls._new_task("taxonomy.generate", meta.get("original_filename", ""))
        terms = cls._semantic_terms_for_ontology(ontology_id, meta)
        groups: Dict[str, List[str]] = {}
        for item in terms:
            key = item.get("semantic_type") or item["normalized"][0].upper()
            groups.setdefault(key, []).append(item["term"])
        taxonomy = {
            "workflow_id": "taxonomy.generate",
            "ontology_id": ontology_id,
            "root": meta.get("ontology_name") or meta.get("prefix") or ontology_id,
            "term_source": terms[0].get("source") if terms else "empty",
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
        source_reasoning = OntologyReasoningService.get_reasoning(source_id)
        target_reasoning = OntologyReasoningService.get_reasoning(target_id)
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
        cls._write_ontology_graph_exports(task_id, source_id, target_id)
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
        candidates = cls._build_link_candidates(rows, ontology_scope, import_task_id, import_task=import_task)
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
                "validation_warning_candidates": sum(1 for candidate in candidates if candidate.get("validation_status") == "warning"),
                "auto_approved_candidates": sum(1 for candidate in candidates if candidate.get("validation_status") == "auto_approved"),
                "generic_matches_filtered": sum(1 for candidate in candidates if candidate.get("generic_match") and not candidate.get("selected_for_apply")),
                "metadata_signals_used": sum(1 for candidate in candidates for source in candidate.get("evidence", []) if str(source).startswith("manifest.") or str(source).startswith("preview.")),
                "source_kinds": {
                    kind: sum(1 for candidate in candidates if candidate.get("source_type") == kind)
                    for kind in ("Entity", "Attribute", "Relationship", "Metadata")
                },
                "target_kinds": {
                    kind: sum(1 for candidate in candidates if candidate.get("target_ontology_type") == kind)
                    for kind in ("Class", "ObjectProperty", "DatatypeProperty", "AnnotationProperty")
                },
                "applied_links": applied_links,
                "committed": bool(apply_links and applied_links >= 0),
            },
        }
        WorkflowArtifactService.write_json(task_id, "reports", "link_candidates.json", report, "link_candidates")
        cls._write_bridge_mapping_exports(task_id, report)
        return {"task_id": task_id, "status": "completed", "result": report, "artifact_manifest": WorkflowArtifactService.get_manifest(task_id)}

    @classmethod
    def chunk_graph(cls, payload: Dict[str, Any]) -> Dict[str, Any]:
        ontology_id = cls._resolve_ontology_id(payload.get("ontology_id"))
        chunk_size = int(payload.get("chunk_size") or 80)
        if not ontology_id:
            raise ValueError("ontology_id is required")
        meta = cls._ontology_metadata(ontology_id)
        terms = cls._semantic_terms_for_ontology(ontology_id, meta)
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
