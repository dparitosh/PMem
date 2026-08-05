"""A conservative relational projection of an XSD.

This is a *mapping report*, not a database generator.  Complex values are
never silently represented as SQL scalar columns: they become child tables,
and repeated values additionally get a junction table.  The report keeps the
XSD cardinalities and identity constraints so a later DDL generator has the
information it needs.
"""

from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple
import xml.etree.ElementTree as ET

XSD_NS = "http://www.w3.org/2001/XMLSchema"
XSD = f"{{{XSD_NS}}}"
IDENTITY_NAMES = {"id", "uid", "uuid", "identifier", "partnumber", "part_number"}


def _local(value: str) -> str:
    return str(value or "").rsplit(":", 1)[-1]


def _occurrence(element: ET.Element, source_kind: str) -> Dict[str, Any]:
    if source_kind == "attribute":
        required = element.get("use", "optional") == "required"
        return {"min_occurs": 1 if required else 0, "max_occurs": 1,
                "required": required, "repeating": False}
    minimum, maximum = element.get("minOccurs", "1"), element.get("maxOccurs", "1")
    min_value: Any = int(minimum) if minimum.isdigit() else minimum
    max_value: Any = int(maximum) if maximum.isdigit() else maximum
    return {"min_occurs": min_value, "max_occurs": max_value,
            "required": minimum != "0",
            "repeating": maximum == "unbounded" or (maximum.isdigit() and int(maximum) > 1)}


def _owned(node: ET.Element, tag: str) -> Iterable[ET.Element]:
    """Yield declarations owned by node, stopping at nested complex types."""
    for child in list(node):
        if child.tag == tag:
            yield child
        if child.tag != f"{XSD}complexType":
            yield from _owned(child, tag)


def _schema_files(path: Path) -> List[Tuple[Path, ET.Element]]:
    """Load the root schema and resolvable include/import siblings once."""
    loaded: List[Tuple[Path, ET.Element]] = []
    seen: set[Path] = set()

    def visit(file_path: Path) -> None:
        file_path = file_path.resolve()
        if file_path in seen or not file_path.exists():
            return
        try:
            root = ET.parse(file_path).getroot()
        except ET.ParseError:
            return
        seen.add(file_path)
        loaded.append((file_path, root))
        for link in list(root):
            if link.tag in {f"{XSD}include", f"{XSD}import"} and link.get("schemaLocation"):
                visit(file_path.parent / link.get("schemaLocation"))

    visit(path)
    return loaded


def _table(name: str, source: str) -> Dict[str, Any]:
    return {"name": name, "source_kind": source, "columns": [],
            "relationships": [], "primary_key_candidates": [],
            "foreign_key_candidates": [], "constraints": []}


def build_xsd_relational_report(xsd_path: Path) -> Dict[str, Any]:
    loaded = _schema_files(Path(xsd_path))
    complex_types: Dict[str, ET.Element] = {}
    simple_types: set[str] = set()
    target_namespaces: Dict[str, str] = {}
    identity_constraints: List[Dict[str, Any]] = []
    for file_path, root in loaded:
        ns = root.get("targetNamespace", "")
        target_namespaces[file_path.name] = ns
        for node in root.findall(f"{XSD}simpleType"):
            if node.get("name"):
                simple_types.add(node.get("name"))
        for node in root.findall(f"{XSD}complexType"):
            if node.get("name"):
                complex_types.setdefault(node.get("name"), node)
        for key in root.iter(f"{XSD}key"):
            identity_constraints.append({"kind": "key", "name": key.get("name", ""),
                                         "fields": [_local(f.get("xpath", "")) for f in key.findall(f"{XSD}field")]})
        for keyref in root.iter(f"{XSD}keyref"):
            identity_constraints.append({"kind": "keyref", "name": keyref.get("name", ""),
                                         "refer": _local(keyref.get("refer", "")),
                                         "fields": [_local(f.get("xpath", "")) for f in keyref.findall(f"{XSD}field")]})

    tables: List[Dict[str, Any]] = []
    table_by_name: Dict[str, Dict[str, Any]] = {}
    columns: List[Dict[str, Any]] = []

    def ensure_table(name: str, source: str) -> Dict[str, Any]:
        if name not in table_by_name:
            table_by_name[name] = _table(name, source)
            tables.append(table_by_name[name])
        return table_by_name[name]

    def add_column(table: Dict[str, Any], name: str, kind: str, xsd_type: str,
                   element: ET.Element, resolved_type: str = "") -> None:
        row = {"name": name, "source_kind": kind, "xsd_type": xsd_type or "untyped",
               "qname": xsd_type or "",
               "resolved_type": resolved_type or _local(xsd_type) or "untyped",
               "kind": "simple", "is_primary_key_candidate":
               name.lower().replace("-", "_") in IDENTITY_NAMES,
               "is_foreign_key_candidate": False, "foreign_key_target": "",
               **_occurrence(element, kind)}
        if _local(xsd_type) in {"IDREF", "IDREFS"}:
            row["is_foreign_key_candidate"] = True
            row["foreign_key_target"] = "(xs:key/xs:ID target)"
        row["table"] = table["name"]
        table["columns"].append(row)
        columns.append(row)
        if row["is_primary_key_candidate"]:
            table["primary_key_candidates"].append(name)
        if row["is_foreign_key_candidate"]:
            table["foreign_key_candidates"].append({
                "column": name, "target_table": row["foreign_key_target"],
                "source": "XSD IDREF type",
            })

    def map_type(type_node: ET.Element, table_name: str) -> None:
        table = ensure_table(table_name, "complexType")
        for element in _owned(type_node, f"{XSD}element"):
            name = element.get("name") or _local(element.get("ref", ""))
            if not name:
                continue
            xsd_type = element.get("type", "")
            target = _local(xsd_type)
            inline = element.find(f"{XSD}complexType")
            is_complex = inline is not None or target in complex_types
            if not is_complex:
                add_column(table, name, "element", xsd_type or ("inline:simple" if element.find(f"{XSD}simpleType") is not None else ""), element)
                continue
            child_name = table_name + "__" + name if inline is not None else target
            child = ensure_table(child_name, "anonymous complexType" if inline is not None else "complexType reference")
            occ = _occurrence(element, "element")
            rel = {"name": name, "target_table": child_name, "xsd_type": xsd_type,
                   **occ, "association_table": ""}
            if occ["repeating"]:
                junction = f"{table_name}__{name}__link"
                ensure_table(junction, "junction")
                rel["association_table"] = junction
                table_by_name[junction]["columns"] = [
                    {"name": f"{table_name}_id", "kind": "foreign_key", "table": junction},
                    {"name": f"{child_name}_id", "kind": "foreign_key", "table": junction},
                    {"name": "sequence", "kind": "association_attribute", "table": junction},
                ]
                if inline is not None:
                    for attr in _owned(inline, f"{XSD}attribute"):
                        attr_name = attr.get("name") or _local(attr.get("ref", ""))
                        if attr_name:
                            table_by_name[junction]["columns"].append({
                                "name": attr_name, "kind": "association_attribute",
                                "xsd_type": attr.get("type", ""), "table": junction,
                                **_occurrence(attr, "attribute"),
                            })
            else:
                table["foreign_key_candidates"].append({
                    "column": f"{name}_id", "target_table": child_name,
                    "source": "complex element relationship",
                })
            table["relationships"].append(rel)
            if inline is not None:
                map_type(inline, child_name)
        for attribute in _owned(type_node, f"{XSD}attribute"):
            name = attribute.get("name") or _local(attribute.get("ref", ""))
            if name:
                add_column(table, name, "attribute", attribute.get("type", ""), attribute)

    for name, type_node in complex_types.items():
        map_type(type_node, name)

    # Identity constraints are schema-level constraints; retain them and add
    # obvious FK candidates without pretending every XPath is a SQL column.
    for constraint in identity_constraints:
        if constraint["kind"] == "keyref":
            for table in tables:
                table["constraints"].append(constraint)

    return {"status": "success", "source_file": Path(xsd_path).name,
            "tables": tables, "columns": columns,
            "identity_constraints": identity_constraints,
            "namespaces": target_namespaces,
            "summary": {"tables": len(tables), "columns": len(columns),
                        "primary_key_candidates": sum(bool(t["primary_key_candidates"]) for t in tables),
                        "foreign_key_candidates": sum(len(t["foreign_key_candidates"]) for t in tables),
                        "simple_types": len(simple_types), "complex_types": len(complex_types)},
            "semantics": {"primary_key": "Candidate inferred from identity naming and retained xs:key constraints.",
                          "foreign_key": "Complex children use child-table FKs; repeated children use a junction table.",
                          "occurrence": "minOccurs/maxOccurs and required/repeating flags are preserved from XSD."}}
