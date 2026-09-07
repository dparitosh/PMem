"""AP242 STEP/Part-28 MBD adapter for the governed CEIM contract.

This adapter preserves AP242 as the source standard.  It turns the semantic
entities exposed by the conservative STEP parser into a CEIM batch; it does
not claim geometric-kernel reconstruction or Part-21-to-Part-28 conversion.
"""
from __future__ import annotations

from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

from backend.Services.step_parser import parse_step_with_pmi
from backend.parsers.ap242_identity import is_ap242

from .contract import CEIMContract, contract


def _record(source_type: str, item: Any) -> dict[str, Any]:
    source_id = str(getattr(item, "id", "") or "")
    attributes = {
        "name": str(getattr(item, "name", "") or ""),
        "description": str(getattr(item, "description", "") or ""),
    }
    if source_type == "dimension":
        attributes.update({
            "nominal_value": getattr(item, "nominal_value", None),
            "lower_limit": getattr(item, "lower_tolerance", None),
            "upper_limit": getattr(item, "upper_tolerance", None),
            "unit": str(getattr(item, "unit", "") or ""),
            "toleranced_feature_references": ",".join(str(value) for value in (getattr(item, "feature_refs", []) or [])),
        })
    elif source_type == "geometric_tolerance":
        attributes.update({
            "tolerance_value": getattr(item, "magnitude", None),
            "unit": str(getattr(item, "unit", "") or ""),
            "datum_references": ",".join(str(value) for value in (getattr(item, "datum_system_refs", []) or [])),
            "toleranced_feature_references": ",".join(str(value) for value in (getattr(item, "toleranced_feature_refs", []) or [])),
        })
    elif source_type == "datum":
        attributes["name"] = str(getattr(item, "name", "") or getattr(item, "label", "") or "datum")
    elif source_type == "annotation":
        attributes["text"] = str(getattr(item, "text", "") or "")
    return {"source_type": source_type, "source_id": source_id, "attributes": attributes}


def ap242_to_ceim_batch(content: bytes, *, filename: str = "source.stp", ceim: CEIMContract | None = None) -> dict[str, Any]:
    """Extract an identified AP242 MBD exchange into a non-persisted CEIM batch."""
    if not content:
        raise ValueError("AP242 STEP content is empty")
    suffix = Path(filename).suffix.lower() or ".stp"
    if suffix not in {".stp", ".step", ".stpx", ".xml"}:
        raise ValueError("AP242 MBD ingestion supports .stp, .step, .stpx, and AP242 XML files")
    with NamedTemporaryFile(suffix=suffix, delete=False) as handle:
        handle.write(content)
        temporary_path = Path(handle.name)
    try:
        document = parse_step_with_pmi(temporary_path)
    finally:
        temporary_path.unlink(missing_ok=True)
    if not is_ap242(document.metadata.file_schema, document.metadata.namespace, content):
        raise ValueError("The source does not identify an AP242 STEP or AP242 Domain Model representation")

    active_contract = ceim or contract
    typed_items: list[tuple[str, Any]] = []
    for item in document.cad_products:
        typed_items.append(("product_definition" if item.entity_type in {"PRODUCT", "PRODUCT_DEFINITION"} else "product_definition_formation", item))
    typed_items.extend(("shape_representation", item) for item in document.cad_representations)
    typed_items.extend(("topology_entity", item) for item in document.cad_topology)
    typed_items.extend(("geometry_body", item) for item in document.cad_geometry)
    typed_items.extend(("geometric_tolerance", item) for item in document.geometric_tolerances)
    typed_items.extend(("datum", item) for item in document.datums)
    typed_items.extend(("dimension", item) for item in document.dimensions)
    typed_items.extend(("annotation", item) for item in document.annotations)
    typed_items.extend(("graphic_presentation", item) for item in document.graphic_presentations)
    typed_items.extend(("saved_view", item) for item in document.saved_views)

    entities: list[dict[str, Any]] = []
    emitted: set[str] = set()
    for source_type, item in typed_items:
        source_id = str(getattr(item, "id", "") or "")
        if not source_id or source_id in emitted:
            continue
        entities.append(active_contract.normalize_entity(standard="ap242", record=_record(source_type, item)))
        emitted.add(source_id)

    # Assembly occurrences are explicit AP242 semantic relations.  Retain only
    # references to extracted semantic objects; raw context/style references
    # are not silently promoted to product structure.
    relationships: list[dict[str, Any]] = []
    for entity in document.entities:
        if entity.entity_type not in {"NEXT_ASSEMBLY_USAGE_OCCURRENCE", "ASSEMBLY_COMPONENT_USAGE"}:
            continue
        source_id = str(entity.step_id)
        if source_id not in emitted:
            occurrence = active_contract.normalize_entity(
                standard="ap242", record={"source_type": "next_assembly_usage_occurrence", "source_id": source_id, "attributes": {"name": entity.text_value}},
            )
            entities.append(occurrence); emitted.add(source_id)
        for reference in entity.ref_ids:
            target_id = str(reference)
            if target_id in emitted:
                relationships.append(active_contract.normalize_relationship(
                    standard="ap242", record={"source_type": "next_assembly_usage_occurrence", "source_id": source_id, "target_id": target_id},
                ))

    return {
        "standard": "ap242", "representation": "normalized-ceim-v1",
        "ceim_version": active_contract.version, "entities": entities, "relationships": relationships,
        "source_summary": {
            "part21_entities": len(document.entities), "products": len(document.cad_products),
            "representations": len(document.cad_representations), "topology": len(document.cad_topology),
            "geometry": len(document.cad_geometry), "geometric_tolerances": len(document.geometric_tolerances),
            "datums": len(document.datums), "dimensions": len(document.dimensions),
            "annotations": len(document.annotations), "presentations": len(document.graphic_presentations),
            "saved_views": len(document.saved_views),
        },
    }
