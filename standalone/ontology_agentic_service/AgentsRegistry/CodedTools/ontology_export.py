"""Self-contained IIF coded tool: ontology_export."""

from pathlib import Path
from typing import Any, Literal
from llama_index.core.tools import FunctionTool

_FORMATS = {".owl": "xml", ".rdf": "xml", ".xml": "xml", ".ttl": "turtle", ".nt": "nt", ".n3": "n3", ".jsonld": "json-ld"}


def _load(path_value: str):
    from rdflib import Graph
    path = Path(path_value).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"Ontology file not found: {path}")
    if path.suffix.lower() not in _FORMATS:
        raise ValueError(f"Unsupported ontology extension: {path.suffix}")
    formats = [_FORMATS[path.suffix.lower()]]
    if path.suffix.lower() in {".owl", ".rdf", ".xml"}:
        formats.extend(value for value in ("turtle", "n3", "nt", "json-ld") if value not in formats)
    errors = []
    for rdf_format in formats:
        graph = Graph()
        try:
            graph.parse(path, format=rdf_format)
            return path, graph
        except Exception as exc:
            errors.append(exc)
    raise ValueError(f"Could not parse {path.name}; attempted: {', '.join(formats)}") from errors[-1]


def run_ontology_export(path: str, output_dir: str, export_format: Literal["ttl", "rdf", "nt", "jsonld"] = "ttl") -> dict[str, Any]:
    """Serialize an ontology into a new local file through RDFLib."""
    ontology_path, graph = _load(path)
    formats = {"ttl": ("turtle", ".ttl"), "rdf": ("xml", ".rdf"), "nt": ("nt", ".nt"), "jsonld": ("json-ld", ".jsonld")}
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


ontology_export = FunctionTool.from_defaults(name="ontology_export", fn=run_ontology_export)
__all__ = ["ontology_export"]
