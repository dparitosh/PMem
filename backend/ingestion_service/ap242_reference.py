"""Validation boundary for an externally managed AP242 reference repository."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path

from rdflib import Graph
from rdflib.namespace import OWL, RDF, RDFS

from .schema_conversion import EngineeringSchemaConverter


_REQUIRED = {
    "mim_long_form": "data/modules/ap242_managed_model_based_3d_engineering/mim_lf.exp",
    "mim": "data/modules/ap242_managed_model_based_3d_engineering/mim.exp",
    "arm": "data/modules/ap242_managed_model_based_3d_engineering/arm.exp",
    "bom_express": "data/business_object_models/managed_model_based_3d_engineering/bom.exp",
    "bom_xsd": "data/business_object_models/managed_model_based_3d_engineering/bom.xsd",
    "domain_express": "data/domain_models/managed_model_based_3d_engineering_domain/DomainModel.exp",
    "domain_xsd": "data/domain_models/managed_model_based_3d_engineering_domain/DomainModel.xsd",
}


def _digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _semantic_summary(turtle: str) -> dict[str, int]:
    """Measure RDF structures needed for a navigable AP242 ontology.

    Entity counts alone prove an EXPRESS parser ran; they do not prove that the
    output retained hierarchy or property semantics.  These checks are kept at
    the reference boundary so regression tests cover the supplied standard.
    """
    graph = Graph().parse(data=turtle, format="turtle")
    classes = set(graph.subjects(RDF.type, OWL.Class)) | set(graph.subjects(RDF.type, RDFS.Class))
    properties = set(graph.subjects(RDF.type, OWL.ObjectProperty)) | set(graph.subjects(RDF.type, OWL.DatatypeProperty))
    return {
        "triple_count": len(graph),
        "class_count": len(classes),
        "property_count": len(properties),
        "subclass_axiom_count": len(list(graph.triples((None, RDFS.subClassOf, None)))),
        "domain_axiom_count": len(list(graph.triples((None, RDFS.domain, None)))),
        "range_axiom_count": len(list(graph.triples((None, RDFS.range, None)))),
    }


class AP242ReferenceValidator:
    def __init__(self, root: Path | None = None, converter: EngineeringSchemaConverter | None = None) -> None:
        configured = os.getenv("AP242_REFERENCE_ROOT", "")
        self.root = root or (Path(configured) if configured else Path("D:/Githuv_repo/smrlv12"))
        self.converter = converter or EngineeringSchemaConverter()

    def validate(self, *, convert_mim: bool = True, convert_xsd: bool = True) -> dict:
        assets = {name: self.root / relative for name, relative in _REQUIRED.items()}
        missing = [name for name, path in assets.items() if not path.is_file()]
        if missing:
            raise ValueError(f"AP242 reference repository is incomplete: missing {', '.join(missing)}")
        manifest = {name: {"relative_path": str(path.relative_to(self.root)).replace("\\", "/"), "sha256": _digest(path), "size": path.stat().st_size} for name, path in assets.items()}
        result = {"reference_root": str(self.root.resolve()), "valid": True, "assets": manifest}
        if convert_mim:
            conversion = self.converter.convert(filename=assets["mim_long_form"].name, content=assets["mim_long_form"].read_bytes())
            result["conversion"] = {"format": conversion["format"], "ontology_name": conversion["ontology"]["name"], "prefix": conversion["ontology"]["prefix"], "turtle_bytes": len(conversion["ontology"]["turtle"].encode("utf-8")), "statistics": conversion["statistics"], "semantic_summary": _semantic_summary(conversion["ontology"]["turtle"])}
        if convert_xsd:
            xsd_conversions = {}
            for asset_name in ("bom_xsd", "domain_xsd"):
                conversion = self.converter.convert(filename=assets[asset_name].name, content=assets[asset_name].read_bytes())
                xsd_conversions[asset_name] = {
                    "format": conversion["format"],
                    "adapter": conversion.get("adapter"),
                    "ontology_name": conversion["ontology"]["name"],
                    "prefix": conversion["ontology"]["prefix"],
                    "turtle_bytes": len(conversion["ontology"]["turtle"].encode("utf-8")),
                    "statistics": conversion["statistics"],
                    "semantic_summary": _semantic_summary(conversion["ontology"]["turtle"]),
                }
            result["xsd_conversions"] = xsd_conversions
        return result
