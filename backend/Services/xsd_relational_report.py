"""Derive a read-only relational projection report from an XSD."""

from pathlib import Path
from typing import Any, Dict, List
import xml.etree.ElementTree as ET

XSD_NS = "http://www.w3.org/2001/XMLSchema"
XSD = f"{{{XSD_NS}}}"
IDENTITY_NAMES = {"id", "uid", "uuid", "identifier", "partnumber", "part_number"}


def _local(value: str) -> str:
    return str(value or "").rsplit(":", 1)[-1]


def _occurrence(element: ET.Element) -> Dict[str, Any]:
    minimum = element.get("minOccurs", "1")
    maximum = element.get("maxOccurs", "1")
    return {
        "min_occurs": int(minimum) if minimum.isdigit() else minimum,
        "max_occurs": int(maximum) if maximum.isdigit() else maximum,
        "required": minimum not in {"0", "0.0"},
        "repeating": maximum == "unbounded" or (maximum.isdigit() and int(maximum) > 1),
    }


def _column(name: str, source_kind: str, xsd_type: str, element: ET.Element, complex_types: set[str], simple_types: set[str]) -> Dict[str, Any]:
    local_type = _local(xsd_type)
    lower_name = name.lower().replace("-", "_")
    is_simple = xsd_type.startswith(("xs:", "xsd:")) or local_type in simple_types
    is_fk = not is_simple and local_type in complex_types
    return {
        "name": name,
        "source_kind": source_kind,
        "xsd_type": xsd_type or "untyped",
        "resolved_type": local_type or "untyped",
        "kind": "simple" if is_simple else "reference" if is_fk else "complex",
        "is_primary_key_candidate": lower_name in IDENTITY_NAMES,
        "is_foreign_key_candidate": is_fk,
        "foreign_key_target": local_type if is_fk else "",
        **_occurrence(element),
    }


def build_xsd_relational_report(xsd_path: Path) -> Dict[str, Any]:
    root = ET.parse(xsd_path).getroot()
    simple_types = {node.get("name", "") for node in root.findall(f"{XSD}simpleType") if node.get("name")}
    complex_types = {node.get("name", "") for node in root.findall(f"{XSD}complexType") if node.get("name")}
    tables: List[Dict[str, Any]] = []
    columns: List[Dict[str, Any]] = []

    for complex_type in root.findall(f"{XSD}complexType"):
        table_name = complex_type.get("name")
        if not table_name:
            continue
        table_columns: List[Dict[str, Any]] = []
        for element in complex_type.iter(f"{XSD}element"):
            name = element.get("name") or _local(element.get("ref", ""))
            if name:
                row = _column(name, "element", element.get("type", ""), element, complex_types, simple_types)
                row["table"] = table_name
                table_columns.append(row)
                columns.append(row)
        for attribute in complex_type.iter(f"{XSD}attribute"):
            name = attribute.get("name") or _local(attribute.get("ref", ""))
            if name:
                row = _column(name, "attribute", attribute.get("type", ""), attribute, complex_types, simple_types)
                row["table"] = table_name
                table_columns.append(row)
                columns.append(row)
        tables.append({
            "name": table_name,
            "source_kind": "complexType",
            "columns": table_columns,
            "primary_key_candidates": [row["name"] for row in table_columns if row["is_primary_key_candidate"]],
            "foreign_key_candidates": [
                {"column": row["name"], "target_table": row["foreign_key_target"]}
                for row in table_columns if row["is_foreign_key_candidate"]
            ],
        })

    return {
        "status": "success",
        "source_file": xsd_path.name,
        "tables": tables,
        "columns": columns,
        "summary": {
            "tables": len(tables),
            "columns": len(columns),
            "primary_key_candidates": sum(row["is_primary_key_candidate"] for row in columns),
            "foreign_key_candidates": sum(row["is_foreign_key_candidate"] for row in columns),
            "simple_types": len(simple_types),
            "complex_types": len(complex_types),
        },
        "semantics": {
            "primary_key": "Candidate inferred from schema identity naming; verify against business rules.",
            "foreign_key": "Candidate inferred when an element type resolves to another complexType.",
            "occurrence": "minOccurs/maxOccurs and required/repeating flags are preserved from XSD.",
        },
    }
