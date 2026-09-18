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
from defusedxml import ElementTree as ET

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


def _reference_values(value: Any) -> list[str]:
    """Normalize PLMXML scalar/list reference attributes without guessing links."""
    if isinstance(value, (list, tuple, set)):
        values = value
    else:
        values = str(value or "").replace(",", " ").split()
    return [str(item).strip().removeprefix("#") for item in values if str(item).strip()]


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
    known = {str(record.get("id")) for record in raw_entities}
    # Retain explicitly mapped extension resources without pretending they are
    # product Parts. The source type remains in canonical provenance.
    for element in ET.fromstring(content).iter():
        source_type = element.tag.removeprefix("{http://www.plmxml.org/Schemas/PLMXMLSchema}")
        identifier = element.get("id")
        if source_type in {"Terminal", "ConnectionRevision", "GDE"} and identifier and identifier not in known:
            raw_entities.append({"id": identifier, "type": source_type, "name": element.get("name"), "attributes": dict(element.attrib)})
            known.add(identifier)
    normalized_entities = [
        active_contract.normalize_entity(standard="plmxml", record=_source_record(record))
        for record in raw_entities
        if str(record.get("type") or "") in active_contract.mapping_pack("plmxml")["entities"]
    ]
    emitted_ids = {str(entity["id"]).split(":", 1)[-1] for entity in normalized_entities}
    resource_ids = {record["id"] for record in raw_entities if record["type"] in {"Terminal", "ConnectionRevision", "GDE"}}
    relationship_records: list[dict[str, Any]] = []
    relationship_keys: set[tuple[str, str, str]] = set()

    def add_relationship(*, source: str, target: str, source_type: str, source_key: str) -> None:
        if not source or not target or source not in emitted_ids or target not in emitted_ids:
            return
        # A ProductInstance can reference a mapped extension Resource instead
        # of a Part; preserve the relationship but never misclassify it.
        if source_type == "instance_part" and target in resource_ids:
            source_type = "instance_resource"
        key = (source, target, source_type)
        if key in relationship_keys:
            return
        relationship_keys.add(key)
        relationship_records.append(active_contract.normalize_relationship(
            standard="plmxml",
            record={"source_type": source_type, "source_id": source,
                    "target_id": target, "source_key": source_key},
        ))

    # Mapping-pack rules are the authoritative structural contract. They name
    # the XML/parser field that creates each edge, so attributes such as name
    # or revision cannot accidentally become relationships.
    for record in raw_entities:
        attributes = dict(record.get("attributes") or {})
        for rule in active_contract.mapping_pack("plmxml").get("reference_rules", []):
            if rule.get("source_type") != record.get("type"):
                continue
            source = str(record.get("id") or "")
            for target in _reference_values(attributes.get(str(rule.get("attribute") or ""))):
                if rule.get("reverse"):
                    source, target = target, source
                add_relationship(
                    source=source, target=target,
                    source_type=str(rule["relationship_source_type"]),
                    source_key=str(rule["attribute"]),
                )
                if rule.get("reverse"):
                    source, target = target, source

    # Keep parser-extracted edges only as a compatibility fallback for source
    # variants that do not expose a declared mapping field.
    for relationship in list(parsed.get("relationships") or []):
        # Same-document PLMXML references are URI fragments, while parser
        # entity identifiers are bare XML ids. Do not rewrite external URIs.
        source = str(relationship.get("source") or "").removeprefix("#")
        target = str(relationship.get("target") or "").removeprefix("#")
        relation_type = str(relationship.get("type") or "")
        if not source or not target:
            continue
        if relation_type == "HAS_INSTANCE":
            # PLMXML parser reports Part -> occurrence.  CEIM's HAS_PART is
            # modeled from the occurrence/assembly to its referenced Part.
            source, target, source_type = target, source, "instance_part"
            if target in resource_ids:
                source_type = "instance_resource"
        elif relation_type == "CONTAINS":
            source_type = "assembly_child"
        else:
            continue
        add_relationship(source=source, target=target, source_type=source_type, source_key=f"parser:{relation_type}")
    return {
        "standard": "plmxml",
        "entities": normalized_entities,
        "relationships": relationship_records,
        "source_summary": {
            "parsed_relationships": len(parsed.get("relationships") or []),
            "emitted_relationships": len(relationship_records),
            "declared_reference_rules": len(active_contract.mapping_pack("plmxml").get("reference_rules", [])),
            "emitted_structural_relationships": len(relationship_records),
            "unmapped_relationships": max(0, len(parsed.get("relationships") or []) - len(relationship_records)),
            "schema_version": parsed.get("schema_version"),
            "parts": int(parsed.get("total_parts") or 0),
            "product_instances": int(parsed.get("total_instances") or 0),
            "processes": int(parsed.get("total_processes") or 0),
            "requirements": int(parsed.get("total_requirements") or 0),
            "change_notices": int(parsed.get("total_changes") or 0),
        },
    }
