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
