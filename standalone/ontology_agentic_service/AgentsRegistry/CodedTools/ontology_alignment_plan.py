"""Self-contained IIF coded tool: ontology_alignment_plan."""

from pathlib import Path
from typing import Any
from llama_index.core.tools import FunctionTool

_FORMATS = {".owl": "xml", ".rdf": "xml", ".xml": "xml", ".ttl": "turtle", ".nt": "nt", ".n3": "n3", ".jsonld": "json-ld"}


def _inspect(path_value: str) -> dict[str, Any]:
    from rdflib import Graph, OWL, RDF, RDFS
    path = Path(path_value).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"Ontology file not found: {path}")
    if path.suffix.lower() not in _FORMATS:
        raise ValueError(f"Unsupported ontology extension: {path.suffix}")
    formats = [_FORMATS[path.suffix.lower()]]
    if path.suffix.lower() in {".owl", ".rdf", ".xml"}:
        formats.extend(value for value in ("turtle", "n3", "nt", "json-ld") if value not in formats)
    graph = None
    errors = []
    for rdf_format in formats:
        candidate = Graph()
        try:
            candidate.parse(path, format=rdf_format)
            graph = candidate
            break
        except Exception as exc:
            errors.append(exc)
    if graph is None:
        raise ValueError(f"Could not parse {path.name}; attempted: {', '.join(formats)}") from errors[-1]
    return {
        "path": str(path), "engine": "rdflib", "scope": "asserted_graph", "triples": len(graph),
        "classes": len(set(graph.subjects(RDF.type, OWL.Class)) | set(graph.subjects(RDF.type, RDFS.Class))),
        "object_properties": len(set(graph.subjects(RDF.type, OWL.ObjectProperty))),
        "datatype_properties": len(set(graph.subjects(RDF.type, OWL.DatatypeProperty))),
        "individuals": len(set(graph.subjects(RDF.type, OWL.NamedIndividual))),
    }


def _array(metadata: dict[str, Any], name: str) -> list[Any]:
    value = metadata.get(name, [])
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError(f"instance_metadata.{name} must be an array")
    return value


def run_ontology_alignment_plan(path: str, instance_metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    """Plan instance mappings without writing ontology or graph data."""
    metadata = instance_metadata or {}
    if not isinstance(metadata, dict):
        raise ValueError("instance_metadata must be an object")
    return {
        "status": "draft_mapping_plan", "ontology_summary": _inspect(path),
        "mapping_targets": {
            "entity_to_class": len(_array(metadata, "entities")),
            "attribute_to_datatype_property": len(_array(metadata, "attributes")),
            "relationship_to_object_property": len(_array(metadata, "relationships")),
            "metadata_to_annotation": len(_array(metadata, "metadata")),
        },
        "required_validations": ["class_existence", "datatype_compatibility", "domain_range_compatibility", "duplicate_mapping", "ontology_scope"],
    }


ontology_alignment_plan = FunctionTool.from_defaults(name="ontology_alignment_plan", fn=run_ontology_alignment_plan)
__all__ = ["ontology_alignment_plan"]
