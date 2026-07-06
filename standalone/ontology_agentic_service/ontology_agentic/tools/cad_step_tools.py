from __future__ import annotations

from pathlib import Path
from typing import Any

SUPPORTED_STEP_EXTENSIONS = {".stp", ".step", ".stpx"}


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _ensure_step_path(path_value: str | Path) -> Path:
    path = Path(path_value)
    if not path.exists():
        raise FileNotFoundError(f"STEP file not found: {path}")
    if path.suffix.lower() not in SUPPORTED_STEP_EXTENSIONS:
        raise ValueError(f"Unsupported STEP extension: {path.suffix}")
    return path


def _load_backend_step_modules() -> tuple[Any, Any]:
    try:
        from backend.Services import owl_step_engine, step_parser
        return step_parser, owl_step_engine
    except Exception as exc:
        raise RuntimeError(
            "STEP tools require the main DEPO backend modules to be available on PYTHONPATH. "
            "Run from the repository root or use the DEPO API workflow adapter."
        ) from exc


def inspect_step_file(path_value: str | Path, include_entity_sample: bool = True, sample_size: int = 20) -> dict[str, Any]:
    path = _ensure_step_path(path_value)
    step_parser, _ = _load_backend_step_modules()

    metadata = step_parser.parse_step_metadata(path)
    doc = step_parser.parse_step_with_pmi(path)
    pmi_summary = step_parser.get_pmi_summary(doc)
    sample_limit = max(0, min(int(sample_size), 100))

    entity_types: dict[str, int] = {}
    for entity in doc.entities:
        entity_types[entity.entity_type] = entity_types.get(entity.entity_type, 0) + 1

    payload: dict[str, Any] = {
        "path": str(path),
        "format": metadata.format,
        "file_schema": metadata.file_schema,
        "file_name": metadata.file_name,
        "namespace": getattr(metadata, "namespace", ""),
        "schema_location": getattr(metadata, "schema_location", ""),
        "schema_version": getattr(metadata, "schema_version", ""),
        "entity_count": len(doc.entities),
        "unique_entity_types": len(entity_types),
        "top_entity_types": sorted(entity_types.items(), key=lambda item: item[1], reverse=True)[:20],
        "pmi_summary": pmi_summary,
        "cad_summary": {
            "products": len(doc.cad_products),
            "representations": len(doc.cad_representations),
            "topology": len(doc.cad_topology),
            "geometry": len(doc.cad_geometry),
            "dimensions": len(doc.dimensions),
            "datums": len(doc.datums),
            "geometric_tolerances": len(doc.geometric_tolerances),
            "annotations": len(doc.annotations),
            "surface_finishes": len(doc.surface_finishes),
        },
        "status": "parsed",
    }

    if include_entity_sample and sample_limit:
        payload["entity_sample"] = [
            {
                "step_id": entity.step_id,
                "entity_type": entity.entity_type,
                "name": entity.attributes.get("name", ""),
                "external_id": entity.attributes.get("external_id", ""),
                "ref_ids": entity.ref_ids[:20],
            }
            for entity in doc.entities[:sample_limit]
        ]

    return payload


def export_step_to_ttl(
    path_value: str | Path,
    output_path: str | Path | None = None,
    base_uri: str = "http://depo-onto.local/step#",
    namespace_prefix: str = "step",
    include_pmi: bool = True,
) -> dict[str, Any]:
    path = _ensure_step_path(path_value)
    _, owl_step_engine = _load_backend_step_modules()
    resolved_output = Path(output_path) if output_path else None
    result = owl_step_engine.convert_step_to_ttl(
        file_path=path,
        output_path=resolved_output,
        base_uri=base_uri,
        namespace_prefix=namespace_prefix,
        include_pmi=include_pmi,
    )
    return result
