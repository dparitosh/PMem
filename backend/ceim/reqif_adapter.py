"""Narrow, safe ReqIF instance adapter for the CEIM contract.

The adapter handles ReqIF business objects, specifications, and declared trace
relations.  It deliberately does not attempt to infer mappings from arbitrary
XML: unrecognised source structures must receive their own governed mapping
pack and adapter.
"""
from __future__ import annotations

from typing import Any
import json

from defusedxml import ElementTree as ET

from .contract import CEIMContract
from backend.Services.reqif_source import parse_reqif


def _local_name(tag: object) -> str:
    return str(tag or "").rsplit("}", 1)[-1].split(":")[-1]


def _first_text(element: Any, name: str) -> str:
    for child in element.iter():
        if _local_name(child.tag) == name:
            return "".join(child.itertext()).strip()
    return ""


def reqif_to_ceim_batch(content: bytes, *, ceim: CEIMContract | None = None) -> dict[str, Any]:
    """Extract standard ReqIF records into a CEIM-normalized, non-persisted batch."""
    if not content:
        raise ValueError("ReqIF content is empty")
    try:
        root = parse_reqif(content)
    except ET.ParseError as exc:
        raise ValueError("ReqIF XML is invalid") from exc
    if _local_name(root.tag) != "REQ-IF":
        raise ValueError("The supplied XML is not a ReqIF document")

    active_contract = ceim or CEIMContract()
    entities: list[dict[str, Any]] = []
    relationships: list[dict[str, Any]] = []
    known_ids: set[str] = set()
    requirement_ids: set[str] = set()
    counts = {"requirements": 0, "specifications": 0, "relations": 0, "unresolved_relations": 0}
    definitions = {element.get('IDENTIFIER'): element.get('LONG-NAME', '') for element in root.iter()
                   if _local_name(element.tag).startswith('ATTRIBUTE-DEFINITION-')}

    def description(element):
        text = str(element.get('DESC') or '').strip()
        if text:
            return text
        direct = next((child for child in element if _local_name(child.tag) == 'DESC'), None)
        if direct is not None:
            return ''.join(direct.itertext()).strip()
        values = next((child for child in element if _local_name(child.tag) == 'VALUES'), [])
        for value in values:
            definition = _first_text(value, 'DEFINITION')
            name = definitions.get(definition, definition).lower()
            if _local_name(value.tag) == 'ATTRIBUTE-VALUE-XHTML' or any(token in name for token in ('description', 'object_desc', 'text')):
                body = next((child for child in value if _local_name(child.tag) == 'THE-VALUE'), None)
                return ''.join(body.itertext()).strip() if body is not None else str(value.get('THE-VALUE') or '')
        return ''

    for element in root.iter():
        kind = _local_name(element.tag)
        source_id = str(element.attrib.get("IDENTIFIER") or "").strip()
        if kind in {'SPEC-OBJECT', 'SPECIFICATION', 'SPEC-RELATION', 'SPEC-HIERARCHY'} and not source_id:
            raise ValueError(f'ReqIF {kind} requires an IDENTIFIER')
        if kind == "SPEC-OBJECT" and source_id:
            if source_id in known_ids:
                raise ValueError(f"ReqIF document contains duplicate IDENTIFIER: {source_id}")
            entities.append(active_contract.normalize_entity(
                standard="reqif",
                record={"source_type": "SPEC-OBJECT", "source_id": source_id, "attributes": {
                    "LONG-NAME": str(element.attrib.get("LONG-NAME") or source_id),
                    "DESC": description(element),
                    "VALUES": json.dumps([ET.tostring(child, encoding="unicode") for child in element if _local_name(child.tag) == "VALUES"]),
                }},
            ))
            known_ids.add(source_id)
            requirement_ids.add(source_id)
            counts["requirements"] += 1
        elif kind == "SPECIFICATION" and source_id:
            if source_id in known_ids:
                raise ValueError(f"ReqIF document contains duplicate IDENTIFIER: {source_id}")
            entities.append(active_contract.normalize_entity(
                standard="reqif",
                record={"source_type": "SPECIFICATION", "source_id": source_id, "attributes": {
                    "LONG-NAME": str(element.attrib.get("LONG-NAME") or source_id),
                }},
            ))
            known_ids.add(source_id)
            counts["specifications"] += 1

    for element in root.iter():
        if _local_name(element.tag) == "SPECIFICATION":
            def visit(node, parent_id, depth=0):
                if depth > 128:
                    raise ValueError('ReqIF hierarchy exceeds the supported nesting limit')
                for ordinal, child in enumerate(node):
                    if _local_name(child.tag) == "SPEC-HIERARCHY":
                        object = next((item for item in child if _local_name(item.tag) == 'OBJECT'), None)
                        object_id = _first_text(object, 'SPEC-OBJECT-REF') if object is not None else ''
                        if object_id not in requirement_ids:
                            raise ValueError("ReqIF hierarchy refers to an unknown requirement")
                        relationships.append(active_contract.normalize_relationship(standard="reqif", record={"source_type": "CONTAINS", "source_id": parent_id, "target_id": object_id, "source_key": f"hierarchy:{child.get('IDENTIFIER')}:{ordinal}"}))
                        visit(child, object_id, depth + 1)
                    else:
                        visit(child, parent_id, depth + 1)
            visit(element, element.get("IDENTIFIER", ""))
        if _local_name(element.tag) != "SPEC-RELATION":
            continue
        source_id = _first_text(element, "SOURCE")
        target_id = _first_text(element, "TARGET")
        if source_id in requirement_ids and target_id in requirement_ids:
            relationships.append(active_contract.normalize_relationship(
                standard="reqif",
                record={"source_type": "SPEC-RELATION", "source_id": source_id, "target_id": target_id, "source_key": f"relation:{element.get('IDENTIFIER')}"},
            ))
            counts["relations"] += 1
        else:
            raise ValueError('ReqIF relation refers to a missing or non-requirement endpoint')

    if not entities:
        raise ValueError('ReqIF contains no requirements or specifications')
    return {
        "standard": "reqif",
        "entities": entities,
        "relationships": relationships,
        "source_summary": counts,
        "validation_scope": "structural_and_reference_checks; formal_ReqIF_XSD_validation_not_performed",
    }
