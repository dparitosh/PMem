"""Bounded structural checks for uploaded XML Schema documents.

The standard library can safely inspect an XSD but cannot perform W3C XML
Schema instance validation.  This report deliberately distinguishes those
checks so callers never mistake a successful upload inspection for formal
AP242 conformance validation.
"""
from __future__ import annotations

from typing import Any

from defusedxml import ElementTree as ET


_XSD_NAMESPACE = "http://www.w3.org/2001/XMLSchema"
_SCHEMA_TAG = f"{{{_XSD_NAMESPACE}}}schema"
_LINK_TAGS = {f"{{{_XSD_NAMESPACE}}}{name}" for name in ("include", "import", "redefine")}


def inspect_xsd_structure(content: bytes) -> dict[str, Any]:
    """Return safe structural facts; raise ValueError for malformed/non-XSD input."""
    if b"<!DOCTYPE" in content.upper():
        raise ValueError("DOCTYPE declarations are not allowed in XML Schema uploads")
    try:
        root = ET.fromstring(content)
    except ET.ParseError as exc:
        raise ValueError(f"Malformed XML Schema: {exc}") from exc
    if root.tag != _SCHEMA_TAG:
        raise ValueError("The XML document root is not xsd:schema")
    dependencies = [
        {
            "kind": child.tag.rsplit("}", 1)[-1],
            "namespace": child.get("namespace", ""),
            "schema_location": child.get("schemaLocation", ""),
            "remote": child.get("schemaLocation", "").startswith(("http://", "https://")),
        }
        for child in root
        if child.tag in _LINK_TAGS
    ]
    return {
        "status": "structurally_valid",
        "checks": {
            "well_formed_xml": True,
            "xsd_schema_root": True,
            "doctype_rejected": True,
        },
        "target_namespace": root.get("targetNamespace", ""),
        "dependencies": dependencies,
        "formal_xsd_instance_validation": "not_performed",
        "schematron_validation": "not_performed",
    }
