"""Narrow, safe ReqIF instance adapter for the CEIM contract.

The adapter handles ReqIF business objects, specifications, and declared trace
relations.  It deliberately does not attempt to infer mappings from arbitrary
XML: unrecognised source structures must receive their own governed mapping
pack and adapter.
"""
from __future__ import annotations

from typing import Any

from defusedxml import ElementTree as ET

from .contract import CEIMContract


def _local_name(tag: object) -> str:
    return str(tag or "").rsplit("}", 1)[-1].split(":")[-1]


def _first_text(element: Any, name: str) -> str:
    for child in element.iter():
        if _local_name(child.tag) == name and child.text:
            return child.text.strip()
    return ""


def reqif_to_ceim_batch(content: bytes, *, ceim: CEIMContract | None = None) -> dict[str, Any]:
    """Extract standard ReqIF records into a CEIM-normalized, non-persisted batch."""
    if not content:
        raise ValueError("ReqIF content is empty")
    try:
        root = ET.fromstring(content)
    except ET.ParseError as exc:
        raise ValueError("ReqIF XML is invalid") from exc
    if _local_name(root.tag) != "REQ-IF":
        raise ValueError("The supplied XML is not a ReqIF document")

    active_contract = ceim or CEIMContract()
    entities: list[dict[str, Any]] = []
    relationships: list[dict[str, Any]] = []
    known_ids: set[str] = set()
    counts = {"requirements": 0, "specifications": 0, "relations": 0, "unresolved_relations": 0}

    for element in root.iter():
        kind = _local_name(element.tag)
        source_id = str(element.attrib.get("IDENTIFIER") or "").strip()
        if kind == "SPEC-OBJECT" and source_id:
            entities.append(active_contract.normalize_entity(
                standard="reqif",
                record={"source_type": "SPEC-OBJECT", "source_id": source_id, "attributes": {
                    "LONG-NAME": str(element.attrib.get("LONG-NAME") or source_id),
                    "DESC": str(element.attrib.get("DESC") or ""),
                }},
            ))
            known_ids.add(source_id)
            counts["requirements"] += 1
        elif kind == "SPECIFICATION" and source_id:
            entities.append(active_contract.normalize_entity(
                standard="reqif",
                record={"source_type": "SPECIFICATION", "source_id": source_id, "attributes": {
                    "LONG-NAME": str(element.attrib.get("LONG-NAME") or source_id),
                }},
            ))
            known_ids.add(source_id)
            counts["specifications"] += 1

    for element in root.iter():
        if _local_name(element.tag) != "SPEC-RELATION":
            continue
        source_id = _first_text(element, "SOURCE")
        target_id = _first_text(element, "TARGET")
        if source_id in known_ids and target_id in known_ids:
            relationships.append(active_contract.normalize_relationship(
                standard="reqif",
                record={"source_type": "SPEC-RELATION", "source_id": source_id, "target_id": target_id},
            ))
            counts["relations"] += 1
        else:
            counts["unresolved_relations"] += 1

    return {
        "standard": "reqif",
        "entities": entities,
        "relationships": relationships,
        "source_summary": counts,
    }
