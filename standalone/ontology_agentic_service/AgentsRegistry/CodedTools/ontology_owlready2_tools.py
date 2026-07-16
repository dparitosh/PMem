"""Local optional Owlready2 analysis/reasoning tool for IIF."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from llama_index.core.tools import FunctionTool


def owlready2_analyze(
    path: str,
    run_reasoner: bool = False,
    reasoner: Literal["hermit", "pellet"] = "hermit",
    infer_property_values: bool = False,
) -> dict[str, Any]:
    """Load an ontology in an isolated World and optionally reason over it."""
    ontology_path = Path(path).expanduser().resolve()
    if not ontology_path.exists() or not ontology_path.is_file():
        raise FileNotFoundError(f"Ontology file not found: {ontology_path}")
    if ontology_path.suffix.lower() not in {".owl", ".rdf", ".xml", ".nt"}:
        raise ValueError("Owlready2 accepts .owl, .rdf, .xml, or .nt")
    if reasoner not in {"hermit", "pellet"}:
        raise ValueError("reasoner must be 'hermit' or 'pellet'")
    try:
        from owlready2 import World, sync_reasoner, sync_reasoner_pellet
    except ImportError as exc:
        raise RuntimeError("Install owlready2>=0.48 to use reasoning") from exc

    world = World()
    try:
        with ontology_path.open("rb") as source:
            ontology = world.get_ontology(ontology_path.as_uri()).load(fileobj=source, only_local=True)
        before = {
            "classes": len(list(ontology.classes())),
            "object_properties": len(list(ontology.object_properties())),
            "datatype_properties": len(list(ontology.data_properties())),
            "annotation_properties": len(list(ontology.annotation_properties())),
            "individuals": len(list(ontology.individuals())),
        }
        if run_reasoner:
            if reasoner == "pellet":
                sync_reasoner_pellet(
                    world,
                    infer_property_values=infer_property_values,
                    infer_data_property_values=infer_property_values,
                    debug=0,
                )
            else:
                sync_reasoner(world, infer_property_values=infer_property_values, debug=0)
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
            "reasoning_run": run_reasoner,
            "reasoner": reasoner if run_reasoner else None,
            "before_reasoning": before,
            "after_reasoning": after,
            "inconsistent_classes": sorted(str(value.iri) for value in world.inconsistent_classes()),
        }
    finally:
        world.close()


owlready2_analyze_tool = FunctionTool.from_defaults(name="owlready2_analyze", fn=owlready2_analyze)


__all__ = ["owlready2_analyze_tool"]
