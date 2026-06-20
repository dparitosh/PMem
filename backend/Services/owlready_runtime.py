"""Optional Owlready2-backed ontology runtime helpers.

This module centralizes the project's direct Owlready2 usage so the rest of the
ontology pipeline can benefit when the dependency is installed, while still
degrading cleanly when it is not available.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

try:
    from owlready2 import DataPropertyClass, ObjectPropertyClass, ThingClass, World
    OWLREADY2_AVAILABLE = True
except Exception:  # pragma: no cover - optional dependency
    DataPropertyClass = ObjectPropertyClass = ThingClass = World = None
    OWLREADY2_AVAILABLE = False

try:
    from rdflib import Graph, URIRef
    from rdflib.namespace import OWL, RDF, RDFS
    RDFLIB_AVAILABLE = True
except Exception:  # pragma: no cover - dependency guard
    Graph = URIRef = OWL = RDF = RDFS = None
    RDFLIB_AVAILABLE = False


def _first_text(values: Any) -> str:
    if values is None:
        return ""
    if isinstance(values, str):
        return values.strip()
    for value in values:
        text = str(value).strip()
        if text:
            return text
    return ""


def _fragment(value: Any) -> str:
    raw = str(value or "")
    if "#" in raw:
        return raw.rsplit("#", 1)[-1]
    if "/" in raw:
        return raw.rstrip("/").rsplit("/", 1)[-1]
    return raw


def _iri(value: Any) -> str:
    if value in {str, int, float, bool}:
        return {
            str: "http://www.w3.org/2001/XMLSchema#string",
            int: "http://www.w3.org/2001/XMLSchema#integer",
            float: "http://www.w3.org/2001/XMLSchema#decimal",
            bool: "http://www.w3.org/2001/XMLSchema#boolean",
        }[value]
    return str(getattr(value, "iri", value) or "")


def _entity_ref(entity: Any) -> Dict[str, str]:
    iri = _iri(entity)
    return {
        "iri": iri,
        "local_name": _fragment(iri),
        "label": _first_text(getattr(entity, "label", [])) or _fragment(iri),
    }


def _entity_refs(values: Iterable[Any]) -> List[Dict[str, str]]:
    refs: List[Dict[str, str]] = []
    seen: set[str] = set()
    for value in values or []:
        iri = _iri(value)
        if not iri or iri in seen:
            continue
        seen.add(iri)
        refs.append(_entity_ref(value))
    return refs


def _is_builtin_class(entity: Any) -> bool:
    iri = _iri(entity)
    return iri in {
        "http://www.w3.org/2002/07/owl#Thing",
        "http://www.w3.org/2002/07/owl#Nothing",
    }


def _rdflib_ref(value: Any, prefix: str = "") -> Dict[str, str]:
    iri = str(value or "")
    return {
        "iri": iri,
        "local_name": _fragment(iri),
        "label": _fragment(iri),
        "ontology_prefix": prefix,
    }


def _rdflib_semantic_fallback(file_path: Path, prefix: str) -> Dict[str, Any]:
    """Extract OWL/RDFS semantics when Owlready2 loads triples but no entities.

    Some generated Turtle files are valid RDF and validate as OWL vocabulary,
    yet Owlready2 does not expose their classes/properties through
    ontology.classes() / ontology.properties().  The UI still needs the actual
    class/property/domain/range rows, so fall back to RDFLib for structural
    extraction while keeping Owlready2 as the primary runtime.
    """
    if not RDFLIB_AVAILABLE:
        return {}

    graph = Graph()
    try:
        graph.parse(str(file_path))
    except Exception:
        return {}

    def refs_for(subject: Any, predicate: Any) -> List[Dict[str, str]]:
        subject_node = URIRef(str(subject))
        refs: List[Dict[str, str]] = []
        seen: set[str] = set()
        for obj in graph.objects(subject_node, predicate):
            iri = str(obj)
            if iri and iri not in seen:
                seen.add(iri)
                refs.append(_rdflib_ref(iri, prefix))
        return refs

    class_iris = {
        str(subject)
        for subject in graph.subjects(RDF.type, OWL.Class)
        if str(subject) not in {"http://www.w3.org/2002/07/owl#Thing", "http://www.w3.org/2002/07/owl#Nothing"}
    }
    object_property_iris = {str(subject) for subject in graph.subjects(RDF.type, OWL.ObjectProperty)}
    datatype_property_iris = {str(subject) for subject in graph.subjects(RDF.type, OWL.DatatypeProperty)}

    classes = [
        {
            **_rdflib_ref(iri, prefix),
            "parents": refs_for(iri, RDFS.subClassOf),
            "definition": _first_text(graph.objects(iri, RDFS.comment)),
        }
        for iri in sorted(class_iris, key=_fragment)
    ]

    subclass_edges: List[Dict[str, str]] = []
    child_iris: set[str] = set()
    parent_iris: set[str] = set()
    for child in sorted(class_iris):
        child_ref = _rdflib_ref(child, prefix)
        for parent_ref in refs_for(child, RDFS.subClassOf):
            if parent_ref["iri"] in class_iris:
                child_iris.add(child)
                parent_iris.add(parent_ref["iri"])
            subclass_edges.append({
                "source": child_ref["iri"],
                "source_label": child_ref["label"],
                "target": parent_ref["iri"],
                "target_label": parent_ref["label"],
                "type": "subClassOf",
            })

    def property_rows(iris: set[str]) -> List[Dict[str, Any]]:
        return [
            {
                **_rdflib_ref(iri, prefix),
                "domain": refs_for(iri, RDFS.domain),
                "range": refs_for(iri, RDFS.range),
                "definition": _first_text(graph.objects(iri, RDFS.comment)),
            }
            for iri in sorted(iris, key=_fragment)
        ]

    object_properties = property_rows(object_property_iris)
    datatype_properties = property_rows(datatype_property_iris)
    missing_domain_range = [
        {"iri": row["iri"], "label": row["label"], "issue": "missing_domain_or_range"}
        for row in [*object_properties, *datatype_properties]
        if not row["domain"] or not row["range"]
    ]
    orphan_classes = [
        cls for cls in classes
        if cls["iri"] not in child_iris and cls["iri"] not in parent_iris
    ]

    diagnostics: List[Dict[str, Any]] = [{
        "severity": "info",
        "category": "runtime",
        "message": "OWL entities were extracted with RDFLib fallback because Owlready2 exposed no class/property entities.",
        "items": [],
    }]
    if missing_domain_range:
        diagnostics.append({
            "severity": "warning",
            "category": "property",
            "message": "Some properties are missing explicit domain or range.",
            "items": missing_domain_range[:50],
        })

    return {
        "status": "success",
        "engine": "owlready2+rdflib",
        "available": OWLREADY2_AVAILABLE,
        "ontology_iri": "",
        "classes": classes,
        "object_properties": object_properties,
        "datatype_properties": datatype_properties,
        "individuals": [],
        "subclass_edges": subclass_edges,
        "diagnostics": diagnostics,
        "summary": {
            "classes": len(classes),
            "object_properties": len(object_properties),
            "datatype_properties": len(datatype_properties),
            "individuals": 0,
            "subclass_edges": len(subclass_edges),
            "orphan_classes": len(orphan_classes),
            "properties_missing_domain_or_range": len(missing_domain_range),
            "duplicate_class_labels": 0,
            "triple_count": len(graph),
        },
    }


def _load_ontology(world: Any, file_path: Path) -> Any:
    """Load a local ontology file in a Windows-safe way."""
    with file_path.open("rb") as file_obj:
        return world.get_ontology(file_path.resolve().as_uri()).load(fileobj=file_obj, only_local=True)


def _load_ontology_without_imports(world: Any, file_path: Path) -> Any:
    """Load local ontology content after removing external owl:imports links."""
    if not RDFLIB_AVAILABLE:
        raise RuntimeError("rdflib is required to strip owl:imports for local-only Owlready2 loading.")

    raw_text = file_path.read_text(encoding="utf-8-sig", errors="replace").lstrip()
    graph = Graph()
    parse_errors: List[str] = []
    for rdf_format in ("xml", "turtle", "n3", "nt"):
        try:
            graph.parse(data=raw_text, format=rdf_format)
            break
        except Exception as exc:
            parse_errors.append(f"{rdf_format}: {exc}")
            graph = Graph()
    if not graph:
        raise RuntimeError("Could not parse ontology locally: " + "; ".join(parse_errors[:3]))

    for triple in list(graph.triples((None, OWL.imports, None))):
        graph.remove(triple)

    with tempfile.NamedTemporaryFile("wb", suffix=".owl", delete=False) as temp_file:
        temp_path = Path(temp_file.name)
        temp_file.write(graph.serialize(format="xml").encode("utf-8"))

    try:
        with temp_path.open("rb") as file_obj:
            return world.get_ontology(temp_path.resolve().as_uri()).load(fileobj=file_obj, only_local=True)
    finally:
        try:
            temp_path.unlink(missing_ok=True)
        except Exception:
            pass


def _unsupported_load_result(exc: Exception, fallback_exc: Exception | None = None) -> Dict[str, Any]:
    message = f"Owlready2 could not load this ontology file: {exc}"
    if fallback_exc is not None:
        message = f"{message}; local import-stripped fallback also failed: {fallback_exc}"
    return {
        "status": "unsupported",
        "engine": "owlready2",
        "available": True,
        "message": message,
        "classes": [],
        "object_properties": [],
        "datatype_properties": [],
        "individuals": [],
        "subclass_edges": [],
        "diagnostics": [
            {
                "severity": "warning",
                "category": "load",
                "message": message,
            }
        ],
        "summary": {
            "classes": 0,
            "object_properties": 0,
            "datatype_properties": 0,
            "individuals": 0,
            "subclass_edges": 0,
            "orphan_classes": 0,
            "properties_missing_domain_or_range": 0,
            "duplicate_class_labels": 0,
            "triple_count": 0,
        },
    }


class OwlreadyOntologyRuntime:
    """Wrapper for lightweight ontology inspection via Owlready2."""

    @staticmethod
    def is_available() -> bool:
        return OWLREADY2_AVAILABLE

    @staticmethod
    def extract_taxonomy(file_path: Path, prefix: str) -> Optional[Dict[str, Any]]:
        """Return ontology nodes/edges when Owlready2 can load the file."""
        if not OWLREADY2_AVAILABLE:
            return None

        world = World()
        try:
            ontology = _load_ontology(world, file_path)
        except Exception as exc:
            try:
                world = World()
                ontology = _load_ontology_without_imports(world, file_path)
            except Exception as fallback_exc:
                unsupported = _unsupported_load_result(exc, fallback_exc)
                return {"source": "owlready2", "nodes": [], "edges": [], "triple_count": 0, **unsupported}

        nodes: List[Dict[str, Any]] = []
        node_ids: set[str] = set()
        edges: List[Dict[str, str]] = []

        def add_node(entity: Any, source: str) -> Optional[str]:
            label = _first_text(getattr(entity, "label", [])) or _fragment(entity)
            if not label:
                return None
            term_id = f"{prefix}:{_fragment(entity)}" if prefix else _fragment(entity)
            if term_id in node_ids:
                return term_id
            node_ids.add(term_id)
            nodes.append(
                {
                    "term_id": term_id,
                    "uri": getattr(entity, "iri", str(entity)),
                    "label": label,
                    "definition": _first_text(getattr(entity, "comment", [])),
                    "ontology_prefix": prefix,
                    "source": source,
                }
            )
            return term_id

        for cls in ontology.classes():
            if not isinstance(cls, ThingClass):
                continue
            child_id = add_node(cls, "owlready2")
            if not child_id:
                continue
            for parent in getattr(cls, "is_a", []):
                if isinstance(parent, ThingClass) and not _is_builtin_class(parent):
                    parent_id = add_node(parent, "owlready2")
                    if parent_id:
                        edges.append(
                            {
                                "source_term": child_id,
                                "source_label": _first_text(getattr(cls, "label", [])) or _fragment(cls),
                                "target_term": parent_id,
                                "target_label": _first_text(getattr(parent, "label", [])) or _fragment(parent),
                                "mapping_type": "subClassOf",
                            }
                        )

        # Surface properties as taxonomy nodes too so the dictionary view doesn't
        # collapse for ontologies that are property-heavy.
        for prop in ontology.properties():
            source = "owlready2-object-property" if isinstance(prop, ObjectPropertyClass) else "owlready2-datatype-property"
            add_node(prop, source)

        return {
            "source": "owlready2",
            "nodes": nodes,
            "edges": edges,
            "triple_count": len(list(world.as_rdflib_graph())) if hasattr(world, "as_rdflib_graph") else None,
        }

    @staticmethod
    def inspect_ontology(file_path: Path, prefix: str = "") -> Dict[str, Any]:
        """Inspect OWL semantics using Owlready2 and return API-safe structures."""
        if not OWLREADY2_AVAILABLE:
            return {
                "status": "unavailable",
                "engine": "owlready2",
                "available": False,
                "message": "owlready2 is not installed.",
                "classes": [],
                "object_properties": [],
                "datatype_properties": [],
                "individuals": [],
                "subclass_edges": [],
                "diagnostics": [],
                "summary": {},
            }

        world = World()
        try:
            ontology = _load_ontology(world, file_path)
        except Exception as exc:
            try:
                world = World()
                ontology = _load_ontology_without_imports(world, file_path)
            except Exception as fallback_exc:
                return _unsupported_load_result(exc, fallback_exc)

        classes: List[Dict[str, Any]] = []
        subclass_edges: List[Dict[str, str]] = []
        class_iris: set[str] = set()
        child_iris: set[str] = set()
        parent_iris: set[str] = set()

        for cls in ontology.classes():
            if not isinstance(cls, ThingClass):
                continue
            ref = _entity_ref(cls)
            class_iris.add(ref["iri"])
            parents = [
                parent for parent in getattr(cls, "is_a", [])
                if isinstance(parent, ThingClass) and not _is_builtin_class(parent)
            ]
            classes.append({
                **ref,
                "ontology_prefix": prefix,
                "parents": _entity_refs(parents),
                "definition": _first_text(getattr(cls, "comment", [])),
            })
            for parent in parents:
                parent_ref = _entity_ref(parent)
                child_iris.add(ref["iri"])
                parent_iris.add(parent_ref["iri"])
                subclass_edges.append({
                    "source": ref["iri"],
                    "source_label": ref["label"],
                    "target": parent_ref["iri"],
                    "target_label": parent_ref["label"],
                    "type": "subClassOf",
                })

        object_properties: List[Dict[str, Any]] = []
        datatype_properties: List[Dict[str, Any]] = []
        annotation_properties: List[Dict[str, Any]] = []
        missing_domain_range: List[Dict[str, str]] = []

        for prop in ontology.properties():
            ref = _entity_ref(prop)
            domains = _entity_refs(getattr(prop, "domain", []))
            ranges = _entity_refs(getattr(prop, "range", []))
            row = {
                **ref,
                "ontology_prefix": prefix,
                "domain": domains,
                "range": ranges,
                "definition": _first_text(getattr(prop, "comment", [])),
            }
            if not domains or not ranges:
                missing_domain_range.append({
                    "iri": ref["iri"],
                    "label": ref["label"],
                    "issue": "missing_domain_or_range",
                })
            if isinstance(prop, ObjectPropertyClass):
                object_properties.append(row)
            elif isinstance(prop, DataPropertyClass):
                datatype_properties.append(row)
            else:
                annotation_properties.append(row)

        individuals: List[Dict[str, Any]] = []
        for individual in ontology.individuals():
            ref = _entity_ref(individual)
            type_refs = _entity_refs(
                cls for cls in getattr(individual, "is_a", [])
                if isinstance(cls, ThingClass)
            )
            individuals.append({
                **ref,
                "ontology_prefix": prefix,
                "types": type_refs,
                "definition": _first_text(getattr(individual, "comment", [])),
            })

        orphan_classes = [
            cls for cls in classes
            if cls["iri"] not in child_iris and cls["iri"] not in parent_iris
        ]
        duplicate_labels: List[Dict[str, Any]] = []
        by_label: Dict[str, List[str]] = {}
        for cls in classes:
            by_label.setdefault(cls["label"].lower(), []).append(cls["iri"])
        for label, iris in by_label.items():
            if label and len(iris) > 1:
                duplicate_labels.append({"label": label, "iris": iris})

        diagnostics: List[Dict[str, Any]] = []
        if missing_domain_range:
            diagnostics.append({
                "severity": "warning",
                "category": "property",
                "message": "Some properties are missing explicit domain or range.",
                "items": missing_domain_range[:50],
            })
        if orphan_classes:
            diagnostics.append({
                "severity": "info",
                "category": "class",
                "message": "Some classes have no subclass link and are not parents of another class.",
                "items": [
                    {"iri": cls["iri"], "label": cls["label"]}
                    for cls in orphan_classes[:50]
                ],
            })
        if duplicate_labels:
            diagnostics.append({
                "severity": "warning",
                "category": "class",
                "message": "Duplicate class labels detected.",
                "items": duplicate_labels[:50],
            })

        triple_count = len(list(world.as_rdflib_graph())) if hasattr(world, "as_rdflib_graph") else 0
        if not classes and not object_properties and not datatype_properties and not annotation_properties and triple_count:
            fallback = _rdflib_semantic_fallback(file_path, prefix)
            if fallback.get("summary", {}).get("classes") or fallback.get("summary", {}).get("object_properties") or fallback.get("summary", {}).get("datatype_properties"):
                return fallback
        return {
            "status": "success",
            "engine": "owlready2",
            "available": True,
            "ontology_iri": getattr(ontology, "base_iri", ""),
            "classes": classes,
            "object_properties": object_properties,
            "datatype_properties": datatype_properties,
            "annotation_properties": annotation_properties,
            "individuals": individuals,
            "subclass_edges": subclass_edges,
            "diagnostics": diagnostics,
            "summary": {
                "classes": len(classes),
                "object_properties": len(object_properties),
                "datatype_properties": len(datatype_properties),
                "annotation_properties": len(annotation_properties),
                "individuals": len(individuals),
                "subclass_edges": len(subclass_edges),
                "orphan_classes": len(orphan_classes),
                "properties_missing_domain_or_range": len(missing_domain_range),
                "duplicate_class_labels": len(duplicate_labels),
                "triple_count": triple_count,
            },
        }
