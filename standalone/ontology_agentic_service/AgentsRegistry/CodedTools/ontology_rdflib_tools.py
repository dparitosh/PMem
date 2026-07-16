"""Local RDFLib tools for IIF ontology workflows."""

from pathlib import Path
from typing import Any, Literal

from llama_index.core.tools import FunctionTool


_EXTENSIONS = {".owl", ".rdf", ".ttl", ".xml", ".nt", ".n3", ".jsonld"}
_FORMATS = {
    ".owl": "xml",
    ".rdf": "xml",
    ".xml": "xml",
    ".ttl": "turtle",
    ".nt": "nt",
    ".n3": "n3",
    ".jsonld": "json-ld",
}


def _rdflib():
    try:
        from rdflib import BNode, Graph, OWL, RDF, RDFS
    except ImportError as exc:
        raise RuntimeError("Install rdflib>=7,<8 to use local ontology tools") from exc
    return BNode, Graph, OWL, RDF, RDFS


def _path(path_value: str) -> Path:
    path = Path(path_value).expanduser().resolve()
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(f"Ontology file not found: {path}")
    if path.suffix.lower() not in _EXTENSIONS:
        raise ValueError(f"Unsupported ontology extension: {path.suffix}")
    return path


def _graph(path_value: str):
    path = _path(path_value)
    _, Graph, _, _, _ = _rdflib()
    preferred = _FORMATS[path.suffix.lower()]
    candidates = [preferred]
    if path.suffix.lower() in {".owl", ".rdf", ".xml"}:
        candidates.extend(value for value in ("turtle", "n3", "nt", "json-ld") if value != preferred)
    errors = []
    for rdf_format in candidates:
        graph = Graph()
        try:
            graph.parse(path, format=rdf_format)
            return path, graph
        except Exception as exc:  # RDFLib parser exceptions differ by serialization plugin.
            errors.append(f"{rdf_format}: {exc}")
    attempted = ", ".join(candidates)
    raise ValueError(f"Could not parse {path.name}; attempted RDF formats: {attempted}") from errors[-1]


def ontology_inspect(path: str) -> dict[str, Any]:
    """Inspect asserted ontology structure with RDFLib."""
    ontology_path, graph = _graph(path)
    BNode, _, OWL, RDF, RDFS = _rdflib()
    classes = set(graph.subjects(RDF.type, OWL.Class)) | set(graph.subjects(RDF.type, RDFS.Class))
    object_properties = set(graph.subjects(RDF.type, OWL.ObjectProperty))
    datatype_properties = set(graph.subjects(RDF.type, OWL.DatatypeProperty))
    annotation_properties = set(graph.subjects(RDF.type, OWL.AnnotationProperty))
    individuals = set(graph.subjects(RDF.type, OWL.NamedIndividual))
    for subject, _, object_type in graph.triples((None, RDF.type, None)):
        if (
            object_type in classes
            and not isinstance(subject, BNode)
            and subject not in classes
            and subject not in object_properties
            and subject not in datatype_properties
            and subject not in annotation_properties
        ):
            individuals.add(subject)
    return {
        "path": str(ontology_path),
        "engine": "rdflib",
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
        "ontology_iris": sorted(str(value) for value in graph.subjects(RDF.type, OWL.Ontology)),
    }


def ontology_review(
    path: str,
    profile: Literal["schema", "schema_and_instances"] = "schema",
) -> dict[str, Any]:
    """Review asserted ontology structure under an explicit profile."""
    if profile not in {"schema", "schema_and_instances"}:
        raise ValueError("profile must be 'schema' or 'schema_and_instances'")
    summary = ontology_inspect(path)
    issues = []
    if summary["classes"] == 0:
        issues.append({"code": "NO_CLASSES", "severity": "high", "message": "No OWL classes were detected."})
    if summary["object_properties"] + summary["datatype_properties"] == 0:
        issues.append({"code": "NO_PROPERTIES", "severity": "high", "message": "No object or datatype properties were detected."})
    if profile == "schema_and_instances" and summary["individuals"] == 0:
        issues.append({"code": "NO_INDIVIDUALS", "severity": "low", "message": "No individuals were detected."})
    observations = []
    if summary["subclass_edges"] == 0:
        observations.append("No asserted subclass hierarchy was detected.")
    if summary["domain_edges"] == 0 or summary["range_edges"] == 0:
        observations.append("Some properties may not declare asserted domain/range axioms.")
    return {
        "status": "ok" if not issues else "review_required",
        "profile": profile,
        "summary": summary,
        "issues": issues,
        "observations": observations,
    }


def _array(metadata: dict[str, Any], name: str) -> list[Any]:
    value = metadata.get(name, [])
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError(f"instance_metadata.{name} must be an array")
    return value


def ontology_alignment_plan(path: str, instance_metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    """Plan instance mappings without writing ontology or graph data."""
    metadata = instance_metadata or {}
    if not isinstance(metadata, dict):
        raise ValueError("instance_metadata must be an object")
    return {
        "status": "draft_mapping_plan",
        "ontology_summary": ontology_inspect(path),
        "mapping_targets": {
            "entity_to_class": len(_array(metadata, "entities")),
            "attribute_to_datatype_property": len(_array(metadata, "attributes")),
            "relationship_to_object_property": len(_array(metadata, "relationships")),
            "metadata_to_annotation": len(_array(metadata, "metadata")),
        },
        "required_validations": [
            "class_existence",
            "datatype_compatibility",
            "domain_range_compatibility",
            "duplicate_mapping",
            "ontology_scope",
        ],
    }


def ontology_export(
    path: str,
    output_dir: str,
    export_format: Literal["ttl", "rdf", "nt", "jsonld"] = "ttl",
) -> dict[str, Any]:
    """Serialize an ontology locally through RDFLib."""
    ontology_path, graph = _graph(path)
    formats = {
        "ttl": ("turtle", ".ttl"),
        "rdf": ("xml", ".rdf"),
        "nt": ("nt", ".nt"),
        "jsonld": ("json-ld", ".jsonld"),
    }
    if export_format not in formats:
        raise ValueError("export_format must be ttl, rdf, nt, or jsonld")
    serialization, suffix = formats[export_format]
    destination = Path(output_dir).expanduser().resolve()
    destination.mkdir(parents=True, exist_ok=True)
    output_path = destination / f"{ontology_path.stem}.exported{suffix}"
    if output_path.exists():
        raise FileExistsError(f"Export target already exists: {output_path}")
    graph.serialize(destination=output_path, format=serialization)
    return {"status": "exported", "source_path": str(ontology_path), "output_path": str(output_path), "format": export_format}


ontology_inspect_tool = FunctionTool.from_defaults(name="ontology_inspect", fn=ontology_inspect)
ontology_review_tool = FunctionTool.from_defaults(name="ontology_review", fn=ontology_review)
ontology_alignment_plan_tool = FunctionTool.from_defaults(name="ontology_alignment_plan", fn=ontology_alignment_plan)
ontology_export_tool = FunctionTool.from_defaults(name="ontology_export", fn=ontology_export)


__all__ = [
    "ontology_inspect_tool",
    "ontology_review_tool",
    "ontology_alignment_plan_tool",
    "ontology_export_tool",
]
