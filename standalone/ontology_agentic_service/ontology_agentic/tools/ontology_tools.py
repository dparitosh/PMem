"""Canonical, dependency-light ontology workflow tools.

These functions are the single implementation used by both the standalone API
and IIF.  Agent-framework objects belong in the IIF adapter; this module only
depends on RDFLib and the Python standard library.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from rdflib import BNode, Graph, OWL, RDF, RDFS


SUPPORTED_EXTENSIONS = {".owl", ".rdf", ".ttl", ".xml", ".nt", ".n3", ".jsonld"}
_RDFLIB_FORMATS = {
    ".owl": "xml",
    ".rdf": "xml",
    ".xml": "xml",
    ".ttl": "turtle",
    ".nt": "nt",
    ".n3": "n3",
    ".jsonld": "json-ld",
}


def _ontology_path(path_value: str | Path) -> Path:
    path = Path(path_value).expanduser().resolve()
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(f"Ontology file not found: {path}")
    if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
        raise ValueError(f"Unsupported ontology extension: {path.suffix}")
    return path


def _parse_graph(path_value: str | Path) -> tuple[Path, Graph]:
    path = _ontology_path(path_value)
    graph = Graph()
    graph.parse(path, format=_RDFLIB_FORMATS[path.suffix.lower()])
    return path, graph


def ontology_inspect(path: str | Path) -> dict[str, Any]:
    """Inspect one ontology artifact and return deterministic asserted facts."""
    ontology_path, graph = _parse_graph(path)
    classes = set(graph.subjects(RDF.type, OWL.Class))
    object_properties = set(graph.subjects(RDF.type, OWL.ObjectProperty))
    datatype_properties = set(graph.subjects(RDF.type, OWL.DatatypeProperty))
    annotation_properties = set(graph.subjects(RDF.type, OWL.AnnotationProperty))
    individuals = set(graph.subjects(RDF.type, OWL.NamedIndividual))
    for subject, _, object_type in graph.triples((None, RDF.type, None)):
        if (
            object_type in classes
            and subject not in classes
            and subject not in object_properties
            and subject not in datatype_properties
            and not isinstance(subject, BNode)
        ):
            individuals.add(subject)

    return {
        "path": str(ontology_path),
        "format": ontology_path.suffix.lower().lstrip("."),
        "parser": "rdflib",
        "scope": "asserted_graph",
        "triples": len(graph),
        "classes": len(classes),
        "object_properties": len(object_properties),
        "datatype_properties": len(datatype_properties),
        "annotation_properties": len(annotation_properties),
        "individuals": len(individuals),
        "subclass_edges": sum(1 for _ in graph.triples((None, RDFS.subClassOf, None))),
        "domain_edges": sum(1 for _ in graph.triples((None, RDFS.domain, None))),
        "range_edges": sum(1 for _ in graph.triples((None, RDFS.range, None))),
        "ontology_iris": sorted(str(subject) for subject in graph.subjects(RDF.type, OWL.Ontology)),
    }


def ontology_review(path: str | Path, profile: str = "schema") -> dict[str, Any]:
    """Review asserted ontology structure using an explicit qualification profile."""
    normalized_profile = str(profile or "schema").strip().lower()
    if normalized_profile not in {"schema", "schema_and_instances"}:
        raise ValueError("profile must be 'schema' or 'schema_and_instances'")
    summary = ontology_inspect(path)
    checks = [
        ("NO_CLASSES", "high", summary["classes"] == 0, "No OWL classes were detected."),
        (
            "NO_PROPERTIES",
            "high",
            summary["object_properties"] + summary["datatype_properties"] == 0,
            "No object or datatype properties were detected.",
        ),
    ]
    if normalized_profile == "schema_and_instances":
        checks.append(
            ("NO_INDIVIDUALS", "low", summary["individuals"] == 0, "No individuals were detected.")
        )
    issues = [
        {"code": code, "severity": severity, "message": message}
        for code, severity, failed, message in checks
        if failed
    ]
    observations = []
    if summary["subclass_edges"] == 0:
        observations.append("No asserted subclass hierarchy was detected.")
    if summary["domain_edges"] == 0 or summary["range_edges"] == 0:
        observations.append("Some properties may not declare asserted domain/range axioms.")
    return {
        "status": "ok" if not issues else "review_required",
        "profile": normalized_profile,
        "summary": summary,
        "issues": issues,
        "observations": observations,
    }


def _list_field(metadata: dict[str, Any], name: str) -> list[Any]:
    value = metadata.get(name, [])
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError(f"instance_metadata.{name} must be an array")
    return value


def ontology_alignment_plan(
    path: str | Path,
    instance_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Plan instance linking without mutating either source or ontology."""
    metadata = instance_metadata or {}
    if not isinstance(metadata, dict):
        raise ValueError("instance_metadata must be an object")
    summary = ontology_inspect(path)
    return {
        "status": "ready_for_mapping",
        "ontology_summary": summary,
        "mapping_targets": {
            "entity_to_class": len(_list_field(metadata, "entities")),
            "attribute_to_datatype_property": len(_list_field(metadata, "attributes")),
            "relationship_to_object_property": len(_list_field(metadata, "relationships")),
            "metadata_to_annotation": len(_list_field(metadata, "metadata")),
        },
        "validations": [
            "class_existence",
            "datatype_compatibility",
            "domain_range_compatibility",
            "duplicate_mapping",
            "ontology_scope",
        ],
    }


def ontology_export(
    path: str | Path,
    output_dir: str | Path,
    export_format: str = "ttl",
) -> dict[str, Any]:
    """Export an ontology using one canonical format identifier."""
    ontology_path, graph = _parse_graph(path)
    formats = {
        "ttl": ("turtle", ".ttl"),
        "rdf": ("xml", ".rdf"),
        "nt": ("nt", ".nt"),
        "jsonld": ("json-ld", ".jsonld"),
    }
    normalized_format = str(export_format).strip().lower()
    try:
        serialization, suffix = formats[normalized_format]
    except KeyError as exc:
        raise ValueError(f"Unsupported export format: {export_format}") from exc
    destination = Path(output_dir).expanduser().resolve()
    destination.mkdir(parents=True, exist_ok=True)
    output_path = destination / f"{ontology_path.stem}.exported{suffix}"
    graph.serialize(destination=output_path, format=serialization)
    return {
        "status": "exported",
        "source_path": str(ontology_path),
        "output_path": str(output_path),
        "format": normalized_format,
    }


__all__ = [
    "ontology_inspect",
    "ontology_review",
    "ontology_alignment_plan",
    "ontology_export",
]
