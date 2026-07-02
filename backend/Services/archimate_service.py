"""ArchiMate Model Exchange XML parsing helpers.

The parser intentionally keeps ArchiMate as an architecture/process model layer:
elements become business/application/technology architecture nodes, while
ArchiMate relationships become typed Neo4j relationships through the existing
import relationship writer.
"""

from __future__ import annotations

import re
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Tuple

from defusedxml import ElementTree as ET


ARCHIMATE_PREFIX = "archimate"
ARCHIMATE_NAMESPACE_HINTS = (
    "archimate",
    "opengroup.org/xsd/archimate",
    "opengroup.org//xsd/archimate",
    "archimate/3",
    "archimate/3.1",
)


def _local_name(value: str) -> str:
    text = str(value or "")
    if "}" in text:
        return text.rsplit("}", 1)[-1]
    return text


def _clean_label(value: str) -> str:
    raw = str(value or "").strip()
    raw = raw.split(":", 1)[-1] if ":" in raw else raw
    raw = raw.replace("-", " ").replace("_", " ")
    if not raw:
        return "ArchimateElement"
    return "".join(part[:1].upper() + part[1:] for part in raw.split())


def _safe_rel_type(value: str) -> str:
    raw = str(value or "RELATED").strip()
    raw = raw.split(":", 1)[-1] if ":" in raw else raw
    raw = re.sub(r"Relationship$", "", raw, flags=re.IGNORECASE)
    safe = re.sub(r"[^A-Za-z0-9]+", "_", raw).strip("_").upper()
    return safe or "RELATED"


def _ref_id(value: str) -> str:
    text = str(value or "").strip()
    if "#" in text:
        return text.rsplit("#", 1)[-1]
    if "/" in text and not text.startswith(("http://", "https://")):
        return text.rsplit("/", 1)[-1]
    return text


def _first_child_text(element: Any, child_name: str) -> str:
    for child in list(element):
        if _local_name(child.tag).lower() == child_name.lower():
            text = "".join(child.itertext()).strip()
            if text:
                return text
    return ""


def _attr(element: Any, *names: str) -> str:
    attrs = element.attrib or {}
    for name in names:
        if name in attrs and str(attrs[name]).strip():
            return str(attrs[name]).strip()
    wanted = {str(name) for name in names}
    for key, value in attrs.items():
        if _local_name(key) in wanted and str(value).strip():
            return str(value).strip()
    return ""


def _collect_model_metadata(root: Any) -> Dict[str, str]:
    return {
        "model_name": _first_child_text(root, "name"),
        "model_documentation": _first_child_text(root, "documentation"),
        "model_identifier": _attr(root, "identifier", "id"),
    }


def _collect_property_definitions(root: Any) -> Dict[str, Dict[str, str]]:
    definitions: Dict[str, Dict[str, str]] = {}
    for prop_def in root.iter():
        tag = _local_name(prop_def.tag).lower()
        if tag not in {"propertydefinition", "propertydefinitionref"}:
            continue
        prop_id = _ref_id(_attr(prop_def, "identifier", "id"))
        if not prop_id:
            continue
        definitions[prop_id] = {
            "id": prop_id,
            "name": _first_child_text(prop_def, "name") or _attr(prop_def, "name") or prop_id,
            "type": _attr(prop_def, "type", "xsi:type"),
        }
    return definitions


def _collect_properties(element: Any, property_definitions: Dict[str, Dict[str, str]]) -> Dict[str, str]:
    properties: Dict[str, str] = {}
    for prop in element.iter():
        if _local_name(prop.tag).lower() != "property":
            continue
        prop_ref = _ref_id(_attr(prop, "propertyDefinitionRef", "propertyDefinition", "identifierRef", "ref"))
        value = _first_child_text(prop, "value") or "".join(prop.itertext()).strip()
        if not prop_ref or not value:
            continue
        definition = property_definitions.get(prop_ref) or {}
        name = definition.get("name") or prop_ref
        safe_name = re.sub(r"[^A-Za-z0-9_]+", "_", name).strip("_").lower() or prop_ref
        properties[f"property_{safe_name}"] = value
    return properties


def looks_like_archimate_xml(file_content: bytes) -> bool:
    head = (file_content or b"")[:16384].decode("utf-8", errors="ignore").lower()
    normalized_head = head.replace("opengroup.org//xsd", "opengroup.org/xsd")
    return any(hint in normalized_head for hint in ARCHIMATE_NAMESPACE_HINTS) and (
        "<model" in head or "<elements" in head or "<relationships" in head
    )


def parse_archimate_model_exchange(file_content: bytes) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Parse ArchiMate Model Exchange XML into import rows and relationship payloads."""
    rows: List[Dict[str, Any]] = []
    relationships: List[Dict[str, Any]] = []
    views: List[Dict[str, Any]] = []
    view_refs: List[Dict[str, Any]] = []
    element_index: Dict[str, Dict[str, Any]] = {}
    relationship_type_counts: Counter[str] = Counter()
    element_type_counts: Counter[str] = Counter()
    unresolved_relationships: List[Dict[str, str]] = []

    with tempfile.NamedTemporaryFile(delete=False, suffix=".archimate.xml") as tmp:
        tmp.write(file_content)
        tmp_path = Path(tmp.name)

    try:
        tree = ET.parse(tmp_path)
        root = tree.getroot()
    finally:
        tmp_path.unlink(missing_ok=True)

    namespace = root.tag[1: root.tag.index("}")] if str(root.tag).startswith("{") else ""
    model_metadata = _collect_model_metadata(root)
    property_definitions = _collect_property_definitions(root)

    for element in root.iter():
        if _local_name(element.tag).lower() != "element":
            continue
        archimate_id = _ref_id(_attr(element, "identifier", "id"))
        if not archimate_id:
            continue
        element_type_raw = _attr(element, "xsi:type", "type") or "ArchimateElement"
        element_type = _clean_label(element_type_raw)
        name = _first_child_text(element, "name") or _attr(element, "name") or archimate_id
        documentation = _first_child_text(element, "documentation")
        row = {
            "import_row_key": f"archimate:{archimate_id}",
            "id": archimate_id,
            "archimate_id": archimate_id,
            "element_type": element_type,
            "archimate_type": element_type_raw.split(":", 1)[-1],
            "name": name,
            "label": name,
            "description": documentation,
            "semantic_role": "entity",
            "source_format": ARCHIMATE_PREFIX,
            "ontology_prefix": ARCHIMATE_PREFIX,
            "source_ontology": namespace or "ArchiMate Model Exchange",
            "model_identifier": model_metadata.get("model_identifier", ""),
            "model_name": model_metadata.get("model_name", ""),
            **_collect_properties(element, property_definitions),
        }
        rows.append(row)
        element_index[archimate_id] = row
        element_type_counts[element_type] += 1

    for relationship in root.iter():
        if _local_name(relationship.tag).lower() != "relationship":
            continue
        rel_id = _ref_id(_attr(relationship, "identifier", "id"))
        source_id = _ref_id(_attr(relationship, "source"))
        target_id = _ref_id(_attr(relationship, "target"))
        rel_type_raw = _attr(relationship, "xsi:type", "type") or "Relationship"
        if not source_id or not target_id:
            unresolved_relationships.append({"id": rel_id, "source": source_id, "target": target_id, "type": rel_type_raw})
            continue
        if source_id not in element_index or target_id not in element_index:
            unresolved_relationships.append({"id": rel_id, "source": source_id, "target": target_id, "type": rel_type_raw})
            continue
        rel_type = _safe_rel_type(rel_type_raw)
        name = _first_child_text(relationship, "name") or _attr(relationship, "name") or rel_type
        relationships.append({
            "type": rel_type,
            "from_props": {"id": source_id},
            "to_props": {"id": target_id},
            "properties": {
                "id": rel_id or f"{source_id}->{target_id}:{rel_type}",
                "archimate_id": rel_id,
                "name": name,
                "label": name,
                "archimate_type": rel_type_raw.split(":", 1)[-1],
                "source_format": ARCHIMATE_PREFIX,
                "ontology_prefix": ARCHIMATE_PREFIX,
                "source_ontology": namespace or "ArchiMate Model Exchange",
                **_collect_properties(relationship, property_definitions),
            },
        })
        relationship_type_counts[rel_type] += 1

    for view in root.iter():
        if _local_name(view.tag).lower() != "view":
            continue
        view_id = _ref_id(_attr(view, "identifier", "id"))
        if not view_id:
            continue
        views.append({
            "id": view_id,
            "name": _first_child_text(view, "name") or _attr(view, "name") or view_id,
            "type": _attr(view, "xsi:type", "type") or "View",
        })
        for child in view.iter():
            child_tag = _local_name(child.tag).lower()
            if child_tag == "node":
                ref = _ref_id(_attr(child, "elementRef", "element", "ref"))
                if ref:
                    view_refs.append({"view_id": view_id, "kind": "element", "ref": ref})
            elif child_tag == "connection":
                ref = _ref_id(_attr(child, "relationshipRef", "relationship", "ref"))
                if ref:
                    view_refs.append({"view_id": view_id, "kind": "relationship", "ref": ref})

    stats = {
        "file_format": "ArchiMate",
        "source_format": ARCHIMATE_PREFIX,
        "namespace": namespace,
        "ontology_prefix": ARCHIMATE_PREFIX,
        "ontology_name": "ArchiMate Process Reference Model",
        **model_metadata,
        "row_count": len(rows),
        "element_count": len(rows),
        "relationship_count": len(relationships),
        "unresolved_relationship_count": len(unresolved_relationships),
        "view_count": len(views),
        "view_reference_count": len(view_refs),
        "property_definition_count": len(property_definitions),
        "element_types": dict(element_type_counts),
        "relationship_types": dict(relationship_type_counts),
        "views": views[:50],
        "view_refs": view_refs[:200],
        "unresolved_relationships": unresolved_relationships[:100],
        "_xmi_relationships": relationships,
        "columns": sorted({key for row in rows for key in row.keys()}),
    }
    return rows, stats
