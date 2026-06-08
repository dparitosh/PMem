"""Optional Owlready2-backed ontology runtime helpers.

This module centralizes the project's direct Owlready2 usage so the rest of the
ontology pipeline can benefit when the dependency is installed, while still
degrading cleanly when it is not available.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from owlready2 import DataPropertyClass, ObjectPropertyClass, ThingClass, World
    OWLREADY2_AVAILABLE = True
except Exception:  # pragma: no cover - optional dependency
    DataPropertyClass = ObjectPropertyClass = ThingClass = World = None
    OWLREADY2_AVAILABLE = False


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
        ontology = world.get_ontology(file_path.resolve().as_uri()).load()

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
                if isinstance(parent, ThingClass):
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
