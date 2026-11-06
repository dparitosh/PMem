"""Helper functions for import format sniffing and XML payload heuristics."""

from __future__ import annotations

import re
from typing import Any, Dict


_PLMXML_METADATA_KEYS = {
    "id",
    "uid",
    "name",
    "label",
    "description",
    "sub_type",
    "sub_class",
    "type",
    "value",
    "text",
    "title",
    "namespace",
    "ontology_prefix",
    "source_ontology",
    "import_id",
}


_PLMXML_STRUCTURAL_TAGS = {
    "AccessIntent",
    "AssociatedAttachment",
    "ApplicationRef",
    "Description",
    "PlainText",
    "Form",
    "UserValue",
}


def derive_prefix_from_namespace(namespace: str) -> str:
    """Derive a short lowercase ontology prefix from an XML namespace URI."""
    if not namespace:
        return "unknown"
    known = {
        "plmxml.org": "plmxml",
        "omg.org/XMI": "xmi",
        "omg.org/spec/XMI": "xmi",
        "XMLSchema": "xsd",
        "22-rdf-syntax-ns": "rdf",
        "/owl#": "owl",
        "/owl/": "owl",
        "mbse": "mbse",
        "step-": "step",
        "AP239": "ap239",
        "AP242": "ap242",
    }
    for pattern, prefix in known.items():
        if pattern in namespace:
            return prefix

    path_parts = [part for part in namespace.rstrip("/").split("/") if part]
    for part in reversed(path_parts):
        cleaned = re.sub(r"[^a-z0-9]", "", part.lower())
        if len(cleaned) >= 2:
            return cleaned[:20]

    try:
        host = namespace.split("/")[2]
        domain_parts = host.split(".")
        second_level_domain = domain_parts[-2] if len(domain_parts) >= 2 else domain_parts[0]
        cleaned = re.sub(r"[^a-z0-9]", "", second_level_domain.lower())
        if cleaned:
            return cleaned[:20]
    except Exception:
        pass
    return "unknown"


def plmxml_row_has_payload(row: Dict[str, Any], tag: str = "") -> bool:
    meaningful = 0
    for key, value in row.items():
        if key in {"element_type", "id", "name", "label", "description", "sub_type", "sub_class", "ontology_prefix", "source_ontology", "semantic_role"}:
            continue
        if value in (None, "", [], {}):
            continue
        key_norm = str(key).strip().lower()
        if key_norm in _PLMXML_METADATA_KEYS:
            continue
        if key_norm.endswith("ref") or key_norm.endswith("refs"):
            continue
        meaningful += 1
    if meaningful:
        return True
    return bool(tag and tag not in _PLMXML_STRUCTURAL_TAGS and any(str(value).strip() for value in row.values()))


def detect_xml_family(file_content: bytes) -> str:
    """Detect specialized XML families before falling back to generic XML."""
    try:
        from .archimate_service import looks_like_archimate_xml

        if looks_like_archimate_xml(file_content):
            return "archimate"
    except Exception:
        pass

    head = (file_content or b"")[:8192].lower()
    if b"<req-if" in head or b"reqif.xsd" in head or b"www.omg.org/spec/reqif" in head:
        return "reqif"
    if (
        b"3ds.com/xsd/3dxml" in head
        or b"vpmrepreference" in head
        or b"vpmrepinstance" in head
        or b"3dxml" in head and b"plmxml" not in head
    ):
        return "3dxml"
    if b"<plmxml" in head or b"plmxmlschema" in head or b"plmxml.org" in head:
        return "plmxml"
    return "xml"
