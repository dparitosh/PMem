from __future__ import annotations

from pathlib import Path
from typing import Any

from rdflib import BNode, Graph, OWL, RDF, RDFS

try:
    from owlready2 import get_ontology  # type: ignore
    OWLREADY2_AVAILABLE = True
except Exception:  # pragma: no cover
    OWLREADY2_AVAILABLE = False
    get_ontology = None


SUPPORTED_EXTENSIONS = {".owl", ".rdf", ".ttl", ".xml", ".nt", ".n3"}


def ensure_path(path_value: str | Path) -> Path:
    path = Path(path_value)
    if not path.exists():
        raise FileNotFoundError(f"Path not found: {path}")
    return path


def inspect_ontology_artifact(path_value: str | Path) -> dict[str, Any]:
    path = ensure_path(path_value)
    if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
        raise ValueError(f"Unsupported ontology extension: {path.suffix}")

    summary = {
        "path": str(path),
        "format": path.suffix.lower().lstrip("."),
        "engine": "rdflib",
        "classes": 0,
        "object_properties": 0,
        "datatype_properties": 0,
        "annotation_like_properties": 0,
        "individuals": 0,
        "subclass_edges": 0,
        "domain_edges": 0,
        "range_edges": 0,
        "ontology_iris": [],
        "warnings": [],
    }

    owlready2_supported_suffixes = {".owl", ".rdf", ".xml"}
    if OWLREADY2_AVAILABLE and path.suffix.lower() in owlready2_supported_suffixes:
        owlready2_error = None
        for candidate in (str(path.resolve()), path.resolve().as_posix()):
            try:
                onto = get_ontology(candidate).load()
                summary["engine"] = "owlready2"
                summary["classes"] = len(list(onto.classes()))
                summary["object_properties"] = len(list(onto.object_properties()))
                summary["datatype_properties"] = len(list(onto.data_properties()))
                summary["individuals"] = len(list(onto.individuals()))
                summary["ontology_iris"] = [onto.base_iri] if onto.base_iri else []
                owlready2_error = None
                break
            except Exception as exc:
                owlready2_error = exc
        if owlready2_error is not None:
            summary["warnings"].append(f"owlready2_load_failed: {owlready2_error}")
    elif OWLREADY2_AVAILABLE:
        summary["warnings"].append(f"owlready2_skipped_for_format: {path.suffix.lower()}")

    graph = Graph()
    graph.parse(path)

    classes = set(graph.subjects(RDF.type, OWL.Class))
    object_props = set(graph.subjects(RDF.type, OWL.ObjectProperty))
    datatype_props = set(graph.subjects(RDF.type, OWL.DatatypeProperty))
    subclass_edges = list(graph.triples((None, RDFS.subClassOf, None)))
    domain_edges = list(graph.triples((None, RDFS.domain, None)))
    range_edges = list(graph.triples((None, RDFS.range, None)))
    ontology_iris = {str(s) for s in graph.subjects(RDF.type, OWL.Ontology)}

    individuals = set(graph.subjects(RDF.type, OWL.NamedIndividual))
    for subject, _, obj in graph.triples((None, RDF.type, None)):
        if (
            obj in classes
            and subject not in classes
            and subject not in object_props
            and subject not in datatype_props
            and not isinstance(subject, BNode)
        ):
            individuals.add(subject)

    annotation_like = set()
    for prop in graph.subjects(RDF.type, RDF.Property):
        if prop not in object_props and prop not in datatype_props:
            annotation_like.add(prop)

    summary.update(
        {
            "classes": max(summary["classes"], len(classes)),
            "object_properties": max(summary["object_properties"], len(object_props)),
            "datatype_properties": max(summary["datatype_properties"], len(datatype_props)),
            "annotation_like_properties": len(annotation_like),
            "individuals": max(summary["individuals"], len(individuals)),
            "subclass_edges": len(subclass_edges),
            "domain_edges": len(domain_edges),
            "range_edges": len(range_edges),
            "ontology_iris": sorted(set(summary["ontology_iris"]) | ontology_iris),
        }
    )

    if summary["domain_edges"] == 0 or summary["range_edges"] == 0:
        summary["warnings"].append("domain_or_range_edges_missing")
    if summary["subclass_edges"] == 0:
        summary["warnings"].append("subclass_edges_missing")

    return summary


def review_ontology_structure(path_value: str | Path) -> dict[str, Any]:
    summary = inspect_ontology_artifact(path_value)
    issues: list[dict[str, Any]] = []

    if summary["classes"] == 0:
        issues.append({"severity": "high", "code": "NO_CLASSES", "message": "No OWL classes were detected."})
    if summary["object_properties"] == 0 and summary["datatype_properties"] == 0:
        issues.append({"severity": "high", "code": "NO_PROPERTIES", "message": "No ontology properties were detected."})
    if summary["domain_edges"] == 0:
        issues.append({"severity": "medium", "code": "NO_DOMAIN", "message": "No domain relationships were detected."})
    if summary["range_edges"] == 0:
        issues.append({"severity": "medium", "code": "NO_RANGE", "message": "No range relationships were detected."})
    if summary["individuals"] == 0:
        issues.append({"severity": "low", "code": "NO_INDIVIDUALS", "message": "No individuals were detected in the ontology artifact."})

    return {
        "summary": summary,
        "issues": issues,
        "status": "ok" if not issues else "review_required",
    }


def plan_instance_alignment(ontology_path: str | Path, instance_metadata: dict[str, Any]) -> dict[str, Any]:
    summary = inspect_ontology_artifact(ontology_path)
    entity_count = len(instance_metadata.get("entities", []))
    attribute_count = len(instance_metadata.get("attributes", []))
    relationship_count = len(instance_metadata.get("relationships", []))
    metadata_count = len(instance_metadata.get("metadata", []))

    return {
        "ontology_summary": summary,
        "alignment_plan": {
            "entity_to_class": entity_count,
            "attribute_to_dataproperty": attribute_count,
            "relationship_to_objectproperty": relationship_count,
            "metadata_to_annotation_or_provenance": metadata_count,
        },
        "required_validations": [
            "class_existence_check",
            "datatype_compatibility_check",
            "domain_range_compatibility_check",
            "duplicate_mapping_check",
        ],
        "status": "ready_for_mapping",
    }


def export_ontology(path_value: str | Path, output_dir: str | Path, export_format: str) -> dict[str, Any]:
    path = ensure_path(path_value)
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    graph = Graph()
    graph.parse(path)

    normalized = export_format.lower()
    if normalized == "ttl":
        fmt = "turtle"
        suffix = ".ttl"
    elif normalized in {"rdf", "rdfxml", "xml"}:
        fmt = "xml"
        suffix = ".rdf"
    elif normalized == "nt":
        fmt = "nt"
        suffix = ".nt"
    elif normalized == "jsonld":
        fmt = "json-ld"
        suffix = ".jsonld"
    else:
        raise ValueError(f"Unsupported export format: {export_format}")

    target = out_dir / f"{path.stem}.exported{suffix}"
    graph.serialize(destination=target, format=fmt)

    return {
        "source_path": str(path),
        "output_path": str(target),
        "export_format": normalized,
        "status": "exported",
    }
