"""Optional Owlready2 analysis and reasoning isolated from the core RDFLib path."""

from __future__ import annotations

from pathlib import Path
from typing import Any


_SUPPORTED = {".owl", ".rdf", ".xml", ".nt"}


def owlready2_analyze(
    path: str | Path,
    run_reasoner: bool = False,
    reasoner: str = "hermit",
    infer_property_values: bool = False,
) -> dict[str, Any]:
    """Load an ontology in an isolated World and optionally run a reasoner.

    ``only_local=True`` prevents remote import retrieval. RDFLib remains the
    asserted-graph parser; this tool is the explicit Owlready2 boundary.
    """
    ontology_path = Path(path).expanduser().resolve()
    if not ontology_path.exists() or not ontology_path.is_file():
        raise FileNotFoundError(f"Ontology file not found: {ontology_path}")
    if ontology_path.suffix.lower() not in _SUPPORTED:
        raise ValueError("Owlready2 supports .owl, .rdf, .xml, or .nt in this service")
    normalized_reasoner = str(reasoner or "hermit").strip().lower()
    if normalized_reasoner not in {"hermit", "pellet"}:
        raise ValueError("reasoner must be 'hermit' or 'pellet'")

    try:
        from owlready2 import World, sync_reasoner, sync_reasoner_pellet
    except ImportError as exc:
        raise RuntimeError(
            "Owlready2 is not installed in the standalone ontology API. "
            "Install the 'reasoning' extra or use requirements.txt."
        ) from exc

    world = World()
    try:
        # Passing an explicit file object avoids Owlready2 0.48 converting a
        # Windows file:// IRI into the invalid local path /D:/....
        with ontology_path.open("rb") as source:
            ontology = world.get_ontology(ontology_path.as_uri()).load(
                fileobj=source,
                only_local=True,
            )
        before = {
            "classes": len(list(ontology.classes())),
            "object_properties": len(list(ontology.object_properties())),
            "datatype_properties": len(list(ontology.data_properties())),
            "annotation_properties": len(list(ontology.annotation_properties())),
            "individuals": len(list(ontology.individuals())),
        }
        if run_reasoner:
            if normalized_reasoner == "pellet":
                sync_reasoner_pellet(
                    world,
                    infer_property_values=bool(infer_property_values),
                    infer_data_property_values=bool(infer_property_values),
                    debug=0,
                )
            else:
                sync_reasoner(
                    world,
                    infer_property_values=bool(infer_property_values),
                    debug=0,
                )
        after = {
            "classes": len(list(ontology.classes())),
            "object_properties": len(list(ontology.object_properties())),
            "datatype_properties": len(list(ontology.data_properties())),
            "annotation_properties": len(list(ontology.annotation_properties())),
            "individuals": len(list(ontology.individuals())),
        }
        return {
            "path": str(ontology_path),
            "engine": "owlready2",
            "world_scope": "isolated",
            "remote_imports_allowed": False,
            "ontology_iri": ontology.base_iri,
            "imported_ontology_iris": sorted(item.base_iri for item in ontology.imported_ontologies),
            "reasoning_run": bool(run_reasoner),
            "reasoner": normalized_reasoner if run_reasoner else None,
            "infer_property_values": bool(infer_property_values) if run_reasoner else False,
            "before_reasoning": before,
            "after_reasoning": after,
            "inconsistent_classes": sorted(str(item.iri) for item in world.inconsistent_classes()),
        }
    finally:
        world.close()


__all__ = ["owlready2_analyze"]
