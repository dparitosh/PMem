"""Isolated integration seam for the Semantica ontology module.

Semantica is intentionally optional: deployments can operate QIF's
deterministic XSD-to-OWL path now, and enable its lifecycle, SHACL and ontology
evaluation capabilities simply by installing the `semantica` extra.
"""
from __future__ import annotations

import importlib.util
from typing import Any


class SemanticaAdapter:
    package_name = "semantica"

    def capabilities(self) -> dict[str, Any]:
        available = importlib.util.find_spec(self.package_name) is not None
        return {
            "provider": "Semantica",
            "available": available,
            "mode": "enabled" if available else "install_required",
            "capabilities": [
                "ontology_lifecycle",
                "knowledge_graph_to_ontology",
                "owl_rdf_export",
                "shacl_generation_and_validation",
                "namespace_management",
                "ontology_evaluation",
            ],
        }


semantica = SemanticaAdapter()
