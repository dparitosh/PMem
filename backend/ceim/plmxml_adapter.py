"""Teamcenter PLMXML adapter for the governed CEIM batch contract.

PLMXML is retained as the source standard.  The adapter does not claim that a
Teamcenter export is an AP242 exchange; an approved AP242 mapping remains a
separate semantic crosswalk after CEIM normalization.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any

from backend.Services.data_import_service import DataImportService

from .contract import CEIMContract, contract


def _source_record(record: dict[str, Any]) -> dict[str, Any]:
    attributes = dict(record.get("attributes") or {})
    for key in ("name", "part_number", "revision"):
        value = record.get(key)
        if value not in (None, ""):
            attributes[key] = value
    return {
        "source_type": str(record.get("type") or ""),
        "source_id": str(record.get("id") or ""),
        "attributes": attributes,
    }


def plmxml_to_ceim_batch(content: bytes, *, ceim: CEIMContract | None = None) -> dict[str, Any]:
    """Parse a bounded PLMXML export into a non-persisted CEIM batch.

    The file is written only to an operating-system temporary path because the
    mature parser operates on paths.  It is deleted before the function returns.
    """
    if not content:
        raise ValueError("PLMXML content is empty")
    active_contract = ceim or contract
    temporary_path = ""
    try:
        with tempfile.NamedTemporaryFile(prefix="depo-plmxml-", suffix=".xml", delete=False) as handle:
            handle.write(content)
            temporary_path = handle.name
        parsed = DataImportService._parse_plmxml(temporary_path)
    finally:
        if temporary_path:
            Path(temporary_path).unlink(missing_ok=True)

    if parsed.get("error"):
        raise ValueError(f"PLMXML parsing failed: {parsed['error']}")
    raw_entities = list(parsed.get("entities") or [])
    normalized_entities = [
        active_contract.normalize_entity(standard="plmxml", record=_source_record(record))
        for record in raw_entities
        if str(record.get("type") or "") in {"Part", "ProductInstance", "ProductView", "Process", "Requirement", "ChangeNotice"}
    ]
    emitted_ids = {str(entity["id"]).split(":", 1)[-1] for entity in normalized_entities}
    relationship_records: list[dict[str, Any]] = []
    for relationship in list(parsed.get("relationships") or []):
        source = str(relationship.get("source") or "")
        target = str(relationship.get("target") or "")
        relation_type = str(relationship.get("type") or "")
        if not source or not target:
            continue
        if relation_type == "HAS_INSTANCE":
            # PLMXML parser reports Part -> occurrence.  CEIM's HAS_PART is
            # modeled from the occurrence/assembly to its referenced Part.
            source, target, source_type = target, source, "instance_part"
        elif relation_type == "CONTAINS":
            source_type = "assembly_child"
        else:
            continue
        if source not in emitted_ids or target not in emitted_ids:
            continue
        relationship_records.append(
            active_contract.normalize_relationship(
                standard="plmxml",
                record={"source_type": source_type, "source_id": source, "target_id": target},
            )
        )
    return {
        "standard": "plmxml",
        "entities": normalized_entities,
        "relationships": relationship_records,
        "source_summary": {
            "schema_version": parsed.get("schema_version"),
            "parts": int(parsed.get("total_parts") or 0),
            "product_instances": int(parsed.get("total_instances") or 0),
            "processes": int(parsed.get("total_processes") or 0),
            "requirements": int(parsed.get("total_requirements") or 0),
            "change_notices": int(parsed.get("total_changes") or 0),
        },
    }
