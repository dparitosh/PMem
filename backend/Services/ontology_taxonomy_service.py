"""Ontology taxonomy extraction for Ontology Studio.

The service prefers RDF/OWL/SKOS hierarchy triples and falls back to lightweight
XML/schema term extraction for uploaded models that are not RDF serializations.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple
from xml.etree import ElementTree as ET

from rdflib import Graph, URIRef
from rdflib.namespace import OWL, RDF, RDFS, SKOS

from .owlready_runtime import OwlreadyOntologyRuntime
from .ontology_upload_manager import OntologyUploadManager


RDF_FORMAT_BY_EXT = {
    ".ttl": ["turtle", "xml", "n3"],
    ".nt": ["nt"],
    ".n3": ["n3", "turtle"],
    ".rdf": ["xml", "turtle"],
    ".owl": ["xml", "turtle", "n3", "nt"],
    ".xml": ["xml", "turtle"],
    ".jsonld": ["json-ld"],
}


def _local_name(value: Any) -> str:
    raw = str(value or "")
    if "#" in raw:
        raw = raw.rsplit("#", 1)[-1]
    elif "/" in raw:
        raw = raw.rstrip("/").rsplit("/", 1)[-1]
    return raw or str(value or "")


def _term_id(prefix: str, value: Any) -> str:
    local = _local_name(value)
    return f"{prefix}:{local}" if prefix and ":" not in local else local


def _label(graph: Graph, uri: URIRef) -> str:
    for predicate in (RDFS.label, SKOS.prefLabel):
        for value in graph.objects(uri, predicate):
            text = str(value).strip()
            if text:
                return text
    return _local_name(uri)


def _definition(graph: Graph, uri: URIRef) -> str:
    for predicate in (RDFS.comment, SKOS.definition, SKOS.scopeNote):
        for value in graph.objects(uri, predicate):
            text = str(value).strip()
            if text:
                return text
    return ""


class OntologyTaxonomyService:
    @staticmethod
    def _cache_key_for_path(file_path: Path) -> Tuple[str, float, int]:
        path = file_path.resolve()
        try:
            stat = path.stat()
            return (str(path), float(stat.st_mtime), int(stat.st_size))
        except Exception:
            return (str(path), 0.0, 0)

    @staticmethod
    @lru_cache(maxsize=32)
    def _cached_reasoning(file_path_str: str, mtime: float, size: int, prefix: str) -> Dict[str, Any]:
        return OwlreadyOntologyRuntime.inspect_ontology(Path(file_path_str), prefix)

    @staticmethod
    def _semantic_context(ontology_identifier: str) -> Dict[str, Any]:
        meta = OntologyTaxonomyService._resolve_metadata(ontology_identifier)
        source_file_path = Path(meta.get("file_path", ""))
        semantic_file_path = Path(meta.get("owl_file_path") or meta.get("file_path", ""))
        if not source_file_path.exists():
            raise ValueError(f"Ontology file is missing: {ontology_identifier}")
        if not semantic_file_path.exists():
            semantic_file_path = source_file_path

        prefix = str(meta.get("prefix") or meta.get("ontology_prefix") or meta.get("ontology_id") or "").strip()
        return {
            "meta": meta,
            "file_path": semantic_file_path,
            "source_file_path": source_file_path,
            "prefix": prefix,
        }

    @staticmethod
    def _resolve_metadata(identifier: str) -> Dict[str, Any]:
        direct = OntologyUploadManager.get_ontology(identifier)
        if direct.get("status") == "success":
            return direct["metadata"]

        listed = OntologyUploadManager.list_ontologies()
        if listed.get("status") != "success":
            raise ValueError(listed.get("error") or f"Ontology not found: {identifier}")

        lookup = str(identifier or "").strip().lower()
        for meta in listed.get("ontologies", []):
            candidates = {
                str(meta.get("ontology_id") or "").lower(),
                str(meta.get("prefix") or "").lower(),
                str(meta.get("ontology_prefix") or "").lower(),
            }
            if lookup in candidates:
                return meta
        raise ValueError(f"Ontology not found: {identifier}")

    @staticmethod
    def _parse_rdf(meta: Dict[str, Any], file_path: Path) -> Optional[Dict[str, Any]]:
        ext = file_path.suffix.lower()
        rdf_formats = RDF_FORMAT_BY_EXT.get(ext)
        if not rdf_formats:
            return None

        prefix = str(meta.get("prefix") or meta.get("ontology_prefix") or meta.get("ontology_id") or "").strip()
        owlready_result = OwlreadyOntologyRuntime.extract_taxonomy(file_path, prefix)
        if owlready_result and owlready_result.get("nodes"):
            return owlready_result

        graph = Graph()
        parsed_ok = False
        for rdf_format in rdf_formats:
            try:
                graph = Graph()
                graph.parse(str(file_path), format=rdf_format)
                parsed_ok = True
                break
            except Exception:
                continue
        if not parsed_ok:
            return None

        class_uris: Set[URIRef] = set()
        hierarchy_edges: List[Tuple[URIRef, URIRef, str]] = []

        for subject in graph.subjects(RDF.type, OWL.Class):
            if isinstance(subject, URIRef):
                class_uris.add(subject)
        for subject in graph.subjects(RDF.type, RDFS.Class):
            if isinstance(subject, URIRef):
                class_uris.add(subject)
        for subject in graph.subjects(RDF.type, SKOS.Concept):
            if isinstance(subject, URIRef):
                class_uris.add(subject)
        for subject in graph.subjects(RDF.type, OWL.ObjectProperty):
            if isinstance(subject, URIRef):
                class_uris.add(subject)
        for subject in graph.subjects(RDF.type, OWL.DatatypeProperty):
            if isinstance(subject, URIRef):
                class_uris.add(subject)
        for subject in graph.subjects(RDF.type, OWL.AnnotationProperty):
            if isinstance(subject, URIRef):
                class_uris.add(subject)
        for subject, parent in graph.subject_objects(RDFS.subClassOf):
            if isinstance(subject, URIRef) and isinstance(parent, URIRef):
                class_uris.add(subject)
                class_uris.add(parent)
                hierarchy_edges.append((subject, parent, "subClassOf"))
        for subject, parent in graph.subject_objects(SKOS.broader):
            if isinstance(subject, URIRef) and isinstance(parent, URIRef):
                class_uris.add(subject)
                class_uris.add(parent)
                hierarchy_edges.append((subject, parent, "broader"))
        for parent, subject in graph.subject_objects(SKOS.narrower):
            if isinstance(subject, URIRef) and isinstance(parent, URIRef):
                class_uris.add(subject)
                class_uris.add(parent)
                hierarchy_edges.append((subject, parent, "narrower"))

        nodes = [
            {
                "term_id": _term_id(prefix, uri),
                "uri": str(uri),
                "label": _label(graph, uri),
                "definition": _definition(graph, uri),
                "ontology_prefix": prefix,
                "source": "rdf",
            }
            for uri in sorted(class_uris, key=lambda item: str(item))
        ]
        node_by_uri = {node["uri"]: node for node in nodes}
        edges = [
            {
                "source_term": node_by_uri[str(child)]["term_id"],
                "source_label": node_by_uri[str(child)]["label"],
                "target_term": node_by_uri[str(parent)]["term_id"],
                "target_label": node_by_uri[str(parent)]["label"],
                "mapping_type": edge_type,
            }
            for child, parent, edge_type in hierarchy_edges
            if str(child) in node_by_uri and str(parent) in node_by_uri
        ]

        return {
            "source": "rdf",
            "nodes": nodes,
            "edges": edges,
            "triple_count": len(graph),
        }

    @staticmethod
    def _xml_terms(file_path: Path, prefix: str) -> Dict[str, Any]:
        try:
            root = ET.parse(file_path).getroot()
        except Exception:
            return {"source": "text", "nodes": [], "edges": []}

        raw_terms: List[Tuple[str, str]] = []
        parent_stack: List[str] = []
        edges: List[Dict[str, str]] = []

        def visit(element: ET.Element) -> None:
            name = element.attrib.get("name") or element.attrib.get("id") or element.attrib.get("xmi:id")
            type_name = element.attrib.get("type") or element.attrib.get("xmi:type") or ""
            local_tag = element.tag.rsplit("}", 1)[-1]
            current_id = ""
            if name:
                current_id = _term_id(prefix, name)
                raw_terms.append((name, local_tag))
                if parent_stack:
                    edges.append({
                        "source_term": current_id,
                        "source_label": name,
                        "target_term": parent_stack[-1],
                        "target_label": parent_stack[-1].split(":", 1)[-1],
                        "mapping_type": "containedBy",
                    })
            if type_name and ":" in type_name:
                raw_terms.append((type_name.split(":", 1)[-1], "type"))

            if current_id:
                parent_stack.append(current_id)
            for child in list(element):
                visit(child)
            if current_id:
                parent_stack.pop()

        visit(root)

        seen: Set[str] = set()
        nodes = []
        for name, source_type in raw_terms:
            key = _term_id(prefix, name)
            if key in seen:
                continue
            seen.add(key)
            nodes.append({
                "term_id": key,
                "uri": key,
                "label": name,
                "definition": "",
                "ontology_prefix": prefix,
                "source": source_type,
            })

        return {"source": "xml", "nodes": nodes[:1000], "edges": edges[:1500]}

    @staticmethod
    def _text_terms(meta: Dict[str, Any], file_path: Path) -> Dict[str, Any]:
        prefix = str(meta.get("prefix") or meta.get("ontology_prefix") or meta.get("ontology_id") or "").strip()
        try:
            text = file_path.read_text(encoding="utf-8-sig", errors="replace")
        except Exception:
            text = file_path.read_bytes().decode("utf-8", errors="replace")

        candidates = re.findall(r"\b[A-Z][A-Za-z0-9_]{2,}\b|\b[a-z][a-z0-9_]{3,}\b", text or "")
        seen: Set[str] = set()
        nodes = []
        for term in candidates:
            normalized = term.lower()
            if normalized in seen:
                continue
            seen.add(normalized)
            nodes.append({
                "term_id": _term_id(prefix, term),
                "uri": _term_id(prefix, term),
                "label": term,
                "definition": "",
                "ontology_prefix": prefix,
                "source": "text",
            })
            if len(nodes) >= 500:
                break
        return {"source": "text", "nodes": nodes, "edges": []}

    @classmethod
    def get_taxonomy(cls, ontology_identifier: str) -> Dict[str, Any]:
        context = cls._semantic_context(ontology_identifier)
        meta = context["meta"]
        file_path = context["file_path"]
        source_file_path = context.get("source_file_path") or file_path

        parsed = cls._parse_rdf(meta, file_path)
        if not parsed:
            parsed = cls._xml_terms(source_file_path, context["prefix"])
        if not parsed.get("nodes"):
            parsed = cls._text_terms(meta, source_file_path)

        return {
            "ontology_id": meta.get("ontology_id"),
            "ontology_name": meta.get("ontology_name"),
            "prefix": meta.get("prefix") or meta.get("ontology_prefix"),
            "source_filename": meta.get("original_filename") or meta.get("stored_filename"),
            "extraction_source": parsed.get("source"),
            "nodes": parsed.get("nodes", []),
            "edges": parsed.get("edges", []),
            "reasoning_summary": cls.get_reasoning(ontology_identifier).get("summary", {}),
            "summary": {
                "terms": len(parsed.get("nodes", [])),
                "taxonomy_links": len(parsed.get("edges", [])),
                "triple_count": parsed.get("triple_count", 0),
            },
        }

    @classmethod
    def get_reasoning(cls, ontology_identifier: str) -> Dict[str, Any]:
        """Return Owlready2-backed ontology semantics for the registered ontology."""
        context = cls._semantic_context(ontology_identifier)
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
