"""Canonical ontology reasoning facade.

This service centralizes Owlready2-backed ontology semantics so callers do not
reimplement class/property/individual lookup, bridge target validation, or
registered-ontology file resolution.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

from .ontology_upload_manager import OntologyUploadManager
from .owlready_runtime import OwlreadyOntologyRuntime


class OntologyReasoningService:
    """Single backend facade for ontology semantics.

    Owlready2 owns semantic inspection. RDFLib remains inside lower-level
    runtime/fallback helpers for parsing and serialization.
    """

    @staticmethod
    def _cache_key_for_path(file_path: Path) -> Tuple[str, float, int]:
        path = file_path.resolve()
        try:
            stat = path.stat()
            return (str(path), float(stat.st_mtime), int(stat.st_size))
        except Exception:
            return (str(path), 0.0, 0)

    @staticmethod
    def resolve_ontology_id(ontology_ref: str) -> str:
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

    @classmethod
    def semantic_context(cls, ontology_identifier: str) -> Dict[str, Any]:
        ontology_id = cls.resolve_ontology_id(ontology_identifier) or ontology_identifier
        result = OntologyUploadManager.get_ontology(ontology_id)
        if result.get("status") != "success":
            raise ValueError(result.get("error") or f"Ontology not found: {ontology_identifier}")

        meta = result["metadata"]
        source_file_path = Path(meta.get("file_path", ""))
        semantic_file_path = Path(meta.get("owl_file_path") or meta.get("file_path", ""))
        if not source_file_path.exists():
            raise ValueError(f"Ontology file is missing: {ontology_identifier}")
        if not semantic_file_path.exists():
            semantic_file_path = source_file_path

        prefix = str(
            meta.get("prefix")
            or meta.get("ontology_prefix")
            or meta.get("ontology_id")
            or ontology_id
            or ""
        ).strip()
        return {
            "meta": meta,
            "file_path": semantic_file_path,
            "source_file_path": source_file_path,
            "prefix": prefix,
        }

    @staticmethod
    @lru_cache(maxsize=32)
    def _cached_reasoning(file_path_str: str, mtime: float, size: int, prefix: str) -> Dict[str, Any]:
        return OwlreadyOntologyRuntime.inspect_ontology(Path(file_path_str), prefix)

    @classmethod
    def inspect_context(cls, context: Dict[str, Any]) -> Dict[str, Any]:
        meta = context["meta"]
        cache_key = cls._cache_key_for_path(context["file_path"])
        result = dict(cls._cached_reasoning(cache_key[0], cache_key[1], cache_key[2], context["prefix"]))
        result.update({
            "ontology_id": meta.get("ontology_id"),
            "ontology_name": meta.get("ontology_name"),
            "prefix": context["prefix"],
            "source_filename": meta.get("original_filename") or meta.get("stored_filename"),
        })
        return result

    @classmethod
    def get_reasoning(cls, ontology_identifier: str) -> Dict[str, Any]:
        return cls.inspect_context(cls.semantic_context(ontology_identifier))

    @staticmethod
    def _ref_key(ref: Any) -> str:
        if isinstance(ref, dict):
            return str(ref.get("iri") or ref.get("uri") or ref.get("term_id") or ref.get("label") or "").strip()
        return str(ref or "").strip()

    @staticmethod
    def _ref_label(ref: Any) -> str:
        if isinstance(ref, dict):
            return str(ref.get("label") or ref.get("name") or ref.get("term_id") or ref.get("iri") or ref.get("uri") or "").strip()
        text = str(ref or "").strip()
        return text.rsplit("#", 1)[-1].rsplit("/", 1)[-1] if text else ""

    @classmethod
    def preview_inferences(cls, ontology_identifier: str, options: Dict[str, Any] | None = None) -> Dict[str, Any]:
        """Return a non-mutating, user-configurable inference preview."""
        opts = options or {}
        rules = opts.get("rules") or {}
        try:
            max_results = int(opts.get("limit") or 250)
        except (TypeError, ValueError):
            max_results = 250
        max_results = max(25, min(max_results, 1000))

        context = cls.semantic_context(ontology_identifier)
        reasoning = cls.inspect_context(context)

        classes = reasoning.get("classes") or []
        object_props = reasoning.get("object_properties") or []
        datatype_props = reasoning.get("datatype_properties") or []
        individuals = reasoning.get("individuals") or []
        subclass_edges = reasoning.get("subclass_edges") or []

        parent_by_child: Dict[str, set[str]] = {}
        label_by_key: Dict[str, str] = {}
        for cls_row in classes:
            key = cls._ref_key(cls_row.get("iri") or cls_row.get("uri") or cls_row.get("term_id") or cls_row)
            if key:
                label_by_key[key] = cls._entry_label(cls_row) or cls._ref_label(cls_row)
        for edge in subclass_edges:
            child = cls._ref_key(edge.get("source") or edge.get("child") or edge.get("source_iri"))
            parent = cls._ref_key(edge.get("target") or edge.get("parent") or edge.get("target_iri"))
            if child and parent and child != parent:
                parent_by_child.setdefault(child, set()).add(parent)
                label_by_key.setdefault(child, cls._ref_label(edge.get("source_label") or child))
                label_by_key.setdefault(parent, cls._ref_label(edge.get("target_label") or parent))

        inferred: List[Dict[str, Any]] = []
        warnings: List[str] = []
        seen: set[tuple[str, str, str, str]] = set()

        def add(rule: str, subject: str, predicate: str, obj: str, evidence: str, confidence: float = 1.0) -> None:
            if not subject or not obj or len(inferred) >= max_results:
                return
            unique_key = (rule, subject, predicate, obj)
            if unique_key in seen:
                return
            seen.add(unique_key)
            inferred.append({
                "rule": rule,
                "subject": subject,
                "subject_label": label_by_key.get(subject) or cls._ref_label(subject),
                "predicate": predicate,
                "object": obj,
                "object_label": label_by_key.get(obj) or cls._ref_label(obj),
                "confidence": round(confidence, 3),
                "evidence": evidence,
            })

        if rules.get("transitive_subclass", True):
            for child, direct_parents in parent_by_child.items():
                visited = set(direct_parents)
                frontier = list(direct_parents)
                while frontier:
                    current = frontier.pop(0)
                    for ancestor in parent_by_child.get(current, set()):
                        if ancestor in visited or ancestor == child:
                            continue
                        visited.add(ancestor)
                        frontier.append(ancestor)
                        add("transitive_subclass", child, "rdfs:subClassOf+", ancestor, f"Indirect superclass via {cls._ref_label(current)}")

        if rules.get("domain_range_typing", True):
            for prop in object_props + datatype_props:
                prop_key = cls._ref_key(prop.get("iri") or prop.get("uri") or prop.get("term_id") or prop)
                prop_label = cls._entry_label(prop) or cls._ref_label(prop_key)
                for domain in prop.get("domain") or []:
                    add("domain_typing", prop_key, "rdfs:domain", cls._ref_key(domain), f"Property {prop_label} declares this domain", 0.9)
                for rng in prop.get("range") or []:
                    add("range_typing", prop_key, "rdfs:range", cls._ref_key(rng), f"Property {prop_label} declares this range", 0.9)

        rdf_edges: Dict[str, List[Dict[str, str]]] = {"equivalence": [], "disjointness": []}
        if rules.get("equivalence", True) or rules.get("disjointness", True):
            try:
                from rdflib import Graph, URIRef
                from rdflib.namespace import OWL
                from rdflib.namespace import SKOS

                rdf_graph = Graph()
                last_error: Exception | None = None
                for rdf_format in ("turtle", "xml", "json-ld", "nt"):
                    try:
                        rdf_graph.parse(str(context["file_path"]), format=rdf_format)
                        last_error = None
                        break
                    except Exception as exc:
                        last_error = exc
                if last_error is not None and len(rdf_graph) == 0:
                    raise last_error

                def edge_rows(predicate) -> List[Dict[str, str]]:
                    rows: List[Dict[str, str]] = []
                    for s, _, o in rdf_graph.triples((None, predicate, None)):
                        if isinstance(s, URIRef) and isinstance(o, URIRef):
                            rows.append({"source": str(s), "target": str(o)})
                    return rows

                rdf_edges["equivalence"].extend(edge_rows(OWL.equivalentClass))
                rdf_edges["equivalence"].extend(edge_rows(OWL.equivalentProperty))
                rdf_edges["equivalence"].extend(edge_rows(OWL.sameAs))
                rdf_edges["equivalence"].extend(edge_rows(SKOS.exactMatch))
                rdf_edges["disjointness"].extend(edge_rows(OWL.disjointWith))
            except Exception as exc:
                warnings.append(f"Equivalent/disjoint RDF scan skipped: {type(exc).__name__}: {exc}")

        if rules.get("equivalence", True):
            for key in ("equivalent_class_edges", "equivalent_property_edges", "same_as_edges", "skos_exact_match_edges"):
                for edge in reasoning.get(key) or []:
                    source = cls._ref_key(edge.get("source") or edge.get("from"))
                    target = cls._ref_key(edge.get("target") or edge.get("to"))
                    add("equivalence", source, "owl:equivalent/sameAs", target, f"Declared by {key}", 0.95)
            for edge in rdf_edges["equivalence"]:
                add("equivalence", edge["source"], "owl:equivalent/sameAs", edge["target"], "Declared in RDF/OWL graph", 0.95)

        if rules.get("disjointness", True):
            for edge in reasoning.get("disjoint_edges") or reasoning.get("disjoint_class_edges") or []:
                source = cls._ref_key(edge.get("source") or edge.get("from"))
                target = cls._ref_key(edge.get("target") or edge.get("to"))
                add("disjointness_check", source, "owl:disjointWith", target, "Declared disjointness should be checked against individual typing", 0.95)
            for edge in rdf_edges["disjointness"]:
                add("disjointness_check", edge["source"], "owl:disjointWith", edge["target"], "Declared disjointness should be checked against individual typing", 0.95)

        if rules.get("individual_type_closure", True):
            for individual in individuals:
                subject = cls._ref_key(individual.get("iri") or individual.get("uri") or individual.get("term_id") or individual)
                for type_ref in individual.get("types") or individual.get("class_refs") or []:
                    type_key = cls._ref_key(type_ref)
                    for parent in parent_by_child.get(type_key, set()):
                        add("individual_type_closure", subject, "rdf:type", parent, f"Individual type follows superclass of {cls._ref_label(type_key)}", 0.9)

        if not inferred:
            warnings.append("No inference candidates were generated for the selected rules and ontology slice.")

        return {
            "status": "success",
            "ontology_id": reasoning.get("ontology_id") or ontology_identifier,
            "ontology_name": reasoning.get("ontology_name"),
            "prefix": reasoning.get("prefix"),
            "engine": "owlready2-preview",
            "rules": {
                "transitive_subclass": bool(rules.get("transitive_subclass", True)),
                "domain_range_typing": bool(rules.get("domain_range_typing", True)),
                "equivalence": bool(rules.get("equivalence", True)),
                "disjointness": bool(rules.get("disjointness", True)),
                "individual_type_closure": bool(rules.get("individual_type_closure", True)),
            },
            "summary": {
                "classes": len(classes),
                "object_properties": len(object_props),
                "datatype_properties": len(datatype_props),
                "individuals": len(individuals),
                "inferred_candidates": len(inferred),
                "truncated": len(inferred) >= max_results,
            },
            "inferences": inferred,
            "warnings": warnings,
        }

    @staticmethod
    def _entry_label(item: Dict[str, Any]) -> str:
        return str(
            item.get("label")
            or item.get("name")
            or item.get("term_id")
            or item.get("iri")
            or item.get("uri")
            or ""
        ).strip()

    @classmethod
    def iter_semantic_terms(cls, reasoning: Dict[str, Any]) -> Iterable[Dict[str, Any]]:
        groups = (
            ("classes", "Class"),
            ("object_properties", "ObjectProperty"),
            ("datatype_properties", "DatatypeProperty"),
            ("annotation_properties", "AnnotationProperty"),
        )
        for key, target_type in groups:
            for item in reasoning.get(key) or []:
                label = cls._entry_label(item)
                if not label:
                    continue
                yield {
                    **item,
                    "label": label,
                    "target_ontology_type": target_type,
                    "element_id": item.get("iri") or item.get("uri") or item.get("term_id") or label,
                    "domain": item.get("domain") or [],
                    "range": item.get("range") or [],
                }

    @classmethod
    def build_term_lookup(cls, ontology_identifier: str, normalizer, tokenizer, generic_checker) -> Dict[str, List[Dict[str, Any]]]:
        reasoning = cls.get_reasoning(ontology_identifier)
        lookup: Dict[str, List[Dict[str, Any]]] = {}
        for item in cls.iter_semantic_terms(reasoning):
            label = item["label"]
            normalized = normalizer(label)
            if not normalized:
                continue
            entry = {
                "element_id": item["element_id"],
                "class_name": label,
                "term_name": label,
                "prefix": item.get("ontology_prefix") or reasoning.get("prefix") or ontology_identifier,
                "normalized": normalized,
                "tokens": tokenizer(label),
                "is_generic": generic_checker(label),
                "target_ontology_type": item["target_ontology_type"],
                "domain": item.get("domain") or [],
                "range": item.get("range") or [],
            }
            lookup.setdefault(normalized, []).append(entry)
        return lookup

    @staticmethod
    def validate_mapping(source_type: str, target_type: str, match: Dict[str, Any] | None = None, row: Dict[str, Any] | None = None) -> Dict[str, Any]:
        """Validate Semantic Bridge source-kind to ontology target-kind compatibility."""
        source_aliases = {
            "entity": "Entity",
            "class": "Entity",
            "attribute": "Attribute",
            "field": "Attribute",
            "data": "Attribute",
            "relationship": "Relationship",
            "relation": "Relationship",
            "edge": "Relationship",
            "metadata": "Metadata",
            "annotation": "Metadata",
            "provenance": "Metadata",
        }
        target_aliases = {
            "class": "Class",
            "owl:class": "Class",
            "dataproperty": "DatatypeProperty",
            "datatypeproperty": "DatatypeProperty",
            "owl:datatypeproperty": "DatatypeProperty",
            "objectproperty": "ObjectProperty",
            "owl:objectproperty": "ObjectProperty",
            "annotationproperty": "AnnotationProperty",
            "owl:annotationproperty": "AnnotationProperty",
        }
        source_raw = str(source_type or "Entity").strip()
        target_raw = str(target_type or "Class").strip()
        source = source_aliases.get(source_raw.replace(" ", "").lower(), source_raw or "Entity")
        target = target_aliases.get(target_raw.replace(" ", "").lower(), target_raw or "Class")
        errors: List[str] = []
        warnings: List[str] = []

        expected = {
            "Entity": {"Class"},
            "Attribute": {"DatatypeProperty"},
            "Relationship": {"ObjectProperty"},
            "Metadata": {"AnnotationProperty"},
        }
        allowed = expected.get(source, {"Class"})
        if target not in allowed:
            if source == "Metadata" and target == "Class":
                warnings.append("Metadata-to-class mapping is allowed only as a fallback; prefer annotation properties.")
            else:
                errors.append(f"{source} should map to {', '.join(sorted(allowed))}, not {target}.")

        match = match or {}
        row = row or {}
        if source == "Attribute" and target == "DatatypeProperty":
            expected_range = match.get("range") or []
            row_datatype = row.get("datatype") or row.get("data_type") or row.get("type")
            if expected_range and row_datatype:
                row_datatype_text = str(row_datatype).lower()
                range_text = " ".join(str(item).lower() for item in expected_range)
                if row_datatype_text not in range_text and range_text not in row_datatype_text:
                    warnings.append("Attribute datatype does not clearly match ontology property range.")

        return {
            "status": "invalid" if errors else ("warning" if warnings else "valid"),
            "errors": errors,
            "warnings": warnings,
        }
