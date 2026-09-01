"""Validated CSV/Excel parsing and Cypher planning owned by ingestion."""
from __future__ import annotations

import csv
import io
import re
from typing import Any

_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,127}$")
MAX_UPLOAD_BYTES = 25 * 1024 * 1024
MAX_IMPORT_ROWS = 100_000


def _identifier(value: str, field: str) -> str:
    candidate = str(value or "").strip()
    if not _IDENTIFIER.fullmatch(candidate):
        raise ValueError(f"Invalid {field}: use letters, digits and underscores, starting with a letter or underscore")
    return candidate


def _properties(values: list[str], field: str = "property") -> list[str]:
    if not isinstance(values, list) or not values:
        raise ValueError(f"At least one {field} is required")
    return [_identifier(value, field) for value in values]


def load_table(content: bytes, filename: str) -> list[dict[str, Any]]:
    """Read bounded CSV/XLSX records without pandas/numpy.

    CSV uses the standard library and XLSX uses openpyxl (pure Python).  The
    obsolete binary ``.xls`` format is intentionally excluded from the lean
    microservice image; convert it to XLSX before ingestion.
    """
    suffix = str(filename or "").lower()
    if suffix.endswith(".csv"):
        reader = csv.DictReader(io.TextIOWrapper(io.BytesIO(content), encoding="utf-8-sig", newline=""))
        rows = [{str(key or "").strip(): _clean(value) for key, value in row.items()} for row in reader]
    elif suffix.endswith(".xlsx"):
        from openpyxl import load_workbook
        workbook = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        sheet = workbook.active
        values = sheet.iter_rows(values_only=True)
        headers = [str(value or "").strip() for value in next(values, ())]
        if not headers or any(not header for header in headers):
            raise ValueError("XLSX requires a non-empty header row")
        rows = [{headers[index]: _clean(value) for index, value in enumerate(record)} for record in values]
        workbook.close()
    elif suffix.endswith(".xls"):
        raise ValueError("Legacy XLS is not supported by the lean runtime; convert it to XLSX")
    else:
        raise ValueError("Unsupported tabular file type; use CSV or XLSX")
    return [row for row in rows if any(value is not None for value in row.values())]


def _clean(value: Any) -> Any:
    if value is None or (isinstance(value, str) and value.strip().lower() in {"", "nan", "null"}):
        return None
    return value


def node_query(label: str, properties: list[str], merge_keys: list[str]) -> str:
    label = _identifier(label, "node label")
    properties = _properties(properties)
    merge_keys = [_identifier(key, "merge key") for key in (merge_keys or [])]
    if any(key not in properties for key in merge_keys):
        raise ValueError("Every merge key must also be included in properties")
    assignments = ", ".join(f"n.`{property_name}` = row.`{property_name}`" for property_name in properties)
    identity = ", ".join(f"`{key}`: row.`{key}`" for key in merge_keys)
    clause = f"MERGE (n:`{label}` {{{identity}}})" if merge_keys else f"CREATE (n:`{label}`)"
    return f"UNWIND $rows AS row\n{clause}\nSET {assignments}"


def relationship_query(relation_type: str, from_label: str, to_label: str, from_property: str, to_property: str) -> str:
    relation_type = _identifier(relation_type, "relationship type")
    from_label, to_label = _identifier(from_label, "source label"), _identifier(to_label, "target label")
    from_property, to_property = _identifier(from_property, "source property"), _identifier(to_property, "target property")
    return (
        "UNWIND $rows AS row\n"
        f"MATCH (a:`{from_label}` {{{from_property}: row.`{from_property}`}})\n"
        f"MATCH (b:`{to_label}` {{{to_property}: row.`{to_property}`}})\n"
        f"MERGE (a)-[r:`{relation_type}`]->(b)"
    )


def index_query(index_type: str, name: str, label: str, properties: list[str]) -> str:
    index_type, name, label = str(index_type or "").lower(), _identifier(name, "index name"), _identifier(label, "node label")
    properties = _properties(properties)
    property_list = ", ".join(f"n.`{property_name}`" for property_name in properties)
    if index_type == "range":
        return f"CREATE INDEX `{name}` IF NOT EXISTS FOR (n:`{label}`) ON ({property_list})"
    if index_type == "text":
        return f"CREATE TEXT INDEX `{name}` IF NOT EXISTS FOR (n:`{label}`) ON (n.`{properties[0]}`)"
    if index_type == "fulltext":
        return f"CREATE FULLTEXT INDEX `{name}` IF NOT EXISTS FOR (n:`{label}`) ON EACH [{property_list}]"
    if index_type == "vector":
        return f"CREATE VECTOR INDEX `{name}` IF NOT EXISTS FOR (n:`{label}`) ON (n.`{properties[0]}`) OPTIONS {{indexConfig: {{`vector.dimensions`: 128, `vector.similarity_function`: 'cosine'}}}}"
    return ""


def constraint_query(constraint_type: str, name: str, label: str, properties: list[str]) -> str:
    constraint_type, name, label = str(constraint_type or "").lower(), _identifier(name, "constraint name"), _identifier(label, "node label")
    properties = _properties(properties)
    property_list = ", ".join(f"n.`{property_name}`" for property_name in properties)
    if constraint_type == "unique":
        return f"CREATE CONSTRAINT `{name}` IF NOT EXISTS FOR (n:`{label}`) REQUIRE ({property_list}) IS UNIQUE"
    if constraint_type == "exists":
        return f"CREATE CONSTRAINT `{name}` IF NOT EXISTS FOR (n:`{label}`) REQUIRE n.`{properties[0]}` IS NOT NULL"
    if constraint_type == "node_key":
        return f"CREATE CONSTRAINT `{name}` IF NOT EXISTS FOR (n:`{label}`) REQUIRE ({property_list}) IS NODE KEY"
    return ""


def records(table: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return table
