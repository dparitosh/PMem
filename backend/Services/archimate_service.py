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
    "archimatetool.com/archimate",
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
        "model_name": _first_child_text(root, "name") or _attr(root, "name"),
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
        prop_ref = _ref_id(_attr(prop, "propertyDefinitionRef", "propertyDefinition", "identifierRef", "ref", "key"))
        value = _first_child_text(prop, "value") or _attr(prop, "value") or "".join(prop.itertext()).strip()
        if not prop_ref or not value:
            continue
        definition = property_definitions.get(prop_ref) or {}
        name = definition.get("name") or prop_ref
        safe_name = re.sub(r"[^A-Za-z0-9_]+", "_", name).strip("_").lower() or prop_ref
        properties[f"property_{safe_name}"] = value
    return properties


def _collect_xml_attributes(element: Any, excluded: set[str]) -> Dict[str, str]:
    """Preserve vendor and relationship attributes without duplicating core IDs."""
    properties: Dict[str, str] = {}
    excluded_names = {name.lower() for name in excluded}
    for key, value in (element.attrib or {}).items():
        local_key = _local_name(key)
        if local_key.lower() in excluded_names or not str(value).strip():
            continue
        snake_key = re.sub(r"(?<!^)(?=[A-Z])", "_", local_key)
        safe_key = re.sub(r"[^A-Za-z0-9_]+", "_", snake_key).strip("_").lower()
        if safe_key:
            properties[safe_key] = str(value).strip()
    return properties



def _folder_name(element: Any, fallback: str) -> str:
    return _first_child_text(element, "name") or _attr(element, "name") or fallback


def _folder_id(element: Any, index: int, parent_id: str = "") -> str:
    explicit = _ref_id(_attr(element, "identifier", "id"))
    if explicit:
        return explicit
    name = re.sub(r"[^A-Za-z0-9._-]+", "-", _folder_name(element, f"Folder {index}")).strip("-") or f"folder-{index}"
    prefix = parent_id or "root"
    return f"folder:{prefix}:{index}:{name}"


def _view_row(view: Dict[str, Any], namespace: str, model_metadata: Dict[str, str]) -> Dict[str, Any]:
    view_id = str(view.get("id") or "").strip()
    view_name = str(view.get("name") or view_id or "View").strip()
    view_type = str(view.get("type") or "View").split(":", 1)[-1]
    return {
        "import_row_key": f"archimate:view:{view_id}",
        "id": view_id,
        "archimate_id": view_id,
        "element_type": "View",
        "archimate_type": view_type,
        "name": view_name,
        "label": view_name,
        "description": "",
        "semantic_role": "view",
        "diagram_role": "view",
        "source_format": ARCHIMATE_PREFIX,
        "ontology_prefix": ARCHIMATE_PREFIX,
        "source_ontology": namespace or "ArchiMate Model Exchange",
        "model_identifier": model_metadata.get("model_identifier", ""),
        "model_name": model_metadata.get("model_name", ""),
    }

def _is_archimate_relationship_type(value: str) -> bool:
    type_name = str(value or "").split(":", 1)[-1].lower()
    return type_name.endswith("relationship") or type_name in {
        "access", "aggregation", "assignment", "association", "composition",
        "flow", "influence", "realization", "serving", "specialization",
        "triggering",
    }


def _is_archimate_view_type(value: str) -> bool:
    type_name = str(value or "").split(":", 1)[-1].lower()
    return type_name in {"archimatediagrammodel", "diagrammodel", "view"}


def looks_like_archimate_xml(file_content: bytes) -> bool:
    head = (file_content or b"")[:16384].decode("utf-8", errors="ignore").lower()
    normalized_head = head.replace("opengroup.org//xsd", "opengroup.org/xsd")
    has_model_root = bool(re.search(r"<\s*(?:[a-z_][\w.-]*:)?model(?:\s|>)", head))
    return any(hint in normalized_head for hint in ARCHIMATE_NAMESPACE_HINTS) and (
        has_model_root
        or "<elements" in head
        or "<relationships" in head
        or "archimatetool.com/archimate" in head
    )


def parse_archimate_model_exchange(file_content: bytes) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Parse ArchiMate Model Exchange XML into import rows and relationship payloads."""
    rows: List[Dict[str, Any]] = []
    relationships: List[Dict[str, Any]] = []
    views: List[Dict[str, Any]] = []
    view_refs: List[Dict[str, Any]] = []
    folder_relationships: List[Dict[str, Any]] = []
    folder_type_counts: Counter[str] = Counter()
    view_row_ids: set[str] = set()
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

    def add_folder_tree(folder: Any, parent_folder_id: str = "", folder_index: List[int] | None = None) -> None:
        if folder_index is None:
            folder_index = [0]
        folder_index[0] += 1
        folder_id = _folder_id(folder, folder_index[0], parent_folder_id)
        folder_name = _folder_name(folder, f"Folder {folder_index[0]}")
        folder_type = _attr(folder, "type", "xsi:type") or "Folder"
        row = {
            "import_row_key": f"archimate:folder:{folder_id}",
            "id": folder_id,
            "archimate_id": folder_id,
            "element_type": "Package",
            "archimate_type": "Folder",
            "name": folder_name,
            "label": folder_name,
            "description": _first_child_text(folder, "documentation"),
            "semantic_role": "folder",
            "folder_type": folder_type,
            "parent_folder_id": parent_folder_id,
            "source_format": ARCHIMATE_PREFIX,
            "ontology_prefix": ARCHIMATE_PREFIX,
            "source_ontology": namespace or "ArchiMate Model Exchange",
            "model_identifier": model_metadata.get("model_identifier", ""),
            "model_name": model_metadata.get("model_name", "") or _attr(root, "name"),
        }
        if folder_id not in element_index:
            rows.append(row)
            element_index[folder_id] = row
            element_type_counts["Package"] += 1
            folder_type_counts[str(folder_type or "Folder")] += 1
        if parent_folder_id:
            folder_relationships.append({
                "type": "CONTAINS",
                "from_props": {"id": parent_folder_id},
                "to_props": {"id": folder_id},
                "properties": {
                    "id": f"{parent_folder_id}->{folder_id}:CONTAINS",
                    "name": "Contains",
                    "label": "Contains",
                    "archimate_type": "FolderContainment",
                    "source_format": ARCHIMATE_PREFIX,
                    "ontology_prefix": ARCHIMATE_PREFIX,
                },
            })
        for child in list(folder):
            child_tag = _local_name(child.tag).lower()
            if child_tag == "folder":
                add_folder_tree(child, folder_id, folder_index)
                continue
            child_id = _ref_id(_attr(child, "identifier", "id"))
            child_type = _attr(child, "xsi:type", "type")
            if child_id and not _is_archimate_relationship_type(child_type):
                folder_relationships.append({
                    "type": "CONTAINS",
                    "from_props": {"id": folder_id},
                    "to_props": {"id": child_id},
                    "properties": {
                        "id": f"{folder_id}->{child_id}:CONTAINS",
                        "name": "Contains",
                        "label": "Contains",
                        "archimate_type": "FolderContainment",
                        "source_format": ARCHIMATE_PREFIX,
                        "ontology_prefix": ARCHIMATE_PREFIX,
                    },
                })

    folder_counter = [0]
    captured_folders: set[int] = set()
    def capture_top_folder(folder: Any) -> None:
        object_id = id(folder)
        if object_id in captured_folders:
            return
        captured_folders.add(object_id)
        for child in folder.iter():
            if child is not folder and _local_name(child.tag).lower() == "folder":
                captured_folders.add(id(child))
        add_folder_tree(folder, "", folder_counter)

    for folder in root.iter():
        if _local_name(folder.tag).lower() == "folder" and id(folder) not in captured_folders:
            capture_top_folder(folder)
    raw_relationship_elements: List[Any] = []
    for element in root.iter():
        local_tag = _local_name(element.tag).lower()
        if local_tag not in {"element", "relationship"}:
            continue
        archimate_id = _ref_id(_attr(element, "identifier", "id"))
        if not archimate_id:
            continue
        element_type_raw = _attr(element, "xsi:type", "type") or ("Relationship" if local_tag == "relationship" else "ArchimateElement")

        if local_tag == "relationship" or _is_archimate_relationship_type(element_type_raw):
            raw_relationship_elements.append(element)
            continue

        if _is_archimate_view_type(element_type_raw):
            views.append({
                "id": archimate_id,
                "name": _first_child_text(element, "name") or _attr(element, "name") or archimate_id,
                "type": element_type_raw.split(":", 1)[-1],
            })
            for child in element.iter():
                child_tag = _local_name(child.tag).lower()
                if child_tag in {"child", "node"}:
                    ref = _ref_id(_attr(child, "archimateElement", "elementRef", "element", "ref"))
                    if ref:
                        view_refs.append({"view_id": archimate_id, "kind": "element", "ref": ref})
                if child_tag in {"sourceconnection", "connection"}:
                    ref = _ref_id(_attr(child, "archimateRelationship", "relationshipRef", "relationship", "ref"))
                    if ref:
                        view_refs.append({"view_id": archimate_id, "kind": "relationship", "ref": ref})
            continue

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
            "model_name": model_metadata.get("model_name", "") or _attr(root, "name"),
            **_collect_xml_attributes(element, {"identifier", "id", "name", "type"}),
            **_collect_properties(element, property_definitions),
        }
        rows.append(row)
        element_index[archimate_id] = row
        element_type_counts[element_type] += 1

    for relationship in raw_relationship_elements:
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
                **_collect_xml_attributes(relationship, {"identifier", "id", "source", "target", "type", "name"}),
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


    view_relationships: List[Dict[str, Any]] = []
    for view in views:
        view_id = str(view.get("id") or "").strip()
        if not view_id or view_id in view_row_ids:
            continue
        view_row_ids.add(view_id)
        if view_id not in element_index:
            row = _view_row(view, namespace, model_metadata)
            rows.append(row)
            element_index[view_id] = row
            element_type_counts["View"] += 1

    for view_ref in view_refs:
        if view_ref.get("kind") != "element":
            continue
        view_id = str(view_ref.get("view_id") or "").strip()
        ref = str(view_ref.get("ref") or "").strip()
        if view_id and ref and view_id in element_index and ref in element_index:
            view_relationships.append({
                "type": "VIEW_CONTAINS",
                "from_props": {"id": view_id},
                "to_props": {"id": ref},
                "properties": {
                    "id": f"{view_id}->{ref}:VIEW_CONTAINS",
                    "name": "View Contains",
                    "label": "View Contains",
                    "archimate_type": "ViewMembership",
                    "source_format": ARCHIMATE_PREFIX,
                    "ontology_prefix": ARCHIMATE_PREFIX,
                },
            })

    relationships.extend(folder_relationships)
    relationships.extend(view_relationships)
    view_lookup = {view.get("id"): view for view in views if view.get("id")}
    element_views: Dict[str, List[str]] = {}
    relationship_views: Dict[str, List[str]] = {}
    for view_ref in view_refs:
        ref = view_ref.get("ref")
        view_id = view_ref.get("view_id")
        if not ref or not view_id:
            continue
        if view_ref.get("kind") == "relationship":
            relationship_views.setdefault(ref, []).append(view_id)
        else:
            element_views.setdefault(ref, []).append(view_id)

    for row in rows:
        view_ids = sorted(set(element_views.get(str(row.get("archimate_id") or row.get("id") or ""), [])))
        if view_ids:
            row["archimate_view_ids"] = view_ids
            row["primary_view_id"] = view_ids[0]
            row["primary_view_name"] = (view_lookup.get(view_ids[0]) or {}).get("name", "")
            row["diagram_role"] = "view-element"

    for rel in relationships:
        props = rel.get("properties") or {}
        rel_id = str(props.get("archimate_id") or props.get("id") or "")
        view_ids = sorted(set(relationship_views.get(rel_id, [])))
        if view_ids:
            props["archimate_view_ids"] = view_ids
            props["primary_view_id"] = view_ids[0]
            props["primary_view_name"] = (view_lookup.get(view_ids[0]) or {}).get("name", "")
            props["diagram_role"] = "view-relationship"
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
        "folder_count": sum(folder_type_counts.values()),
        "folder_types": dict(folder_type_counts),
        "folder_containment_count": len(folder_relationships),
        "view_containment_count": len(view_relationships),
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
