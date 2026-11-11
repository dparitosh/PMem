"""Validated CSV/Excel parsing and Cypher planning owned by ingestion."""
from __future__ import annotations

import csv
import io
import re
import os
from typing import Any

_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,127}$")
def _positive_setting(name: str, default: int) -> int:
    raw = os.getenv(name, str(default)).strip()
    digits = raw.lstrip('+0') or '0'
    if not re.fullmatch(r'\+?[0-9]+', raw) or len(digits) > 19:
        raise RuntimeError(f"{name} must be an integer byte count without units or console commands")
    value = int(digits)
    if not 0 < value <= 9223372036854775807:
        raise RuntimeError(f"{name} must be positive and fit in a signed 64-bit integer")
    return value


# CAD/PLM instance files can be substantially larger than tabular imports.
# Keep one governed limit, configurable per deployment rather than hardcoded.
MAX_UPLOAD_BYTES = _positive_setting("DEPO_MAX_INGEST_BYTES", 500 * 1024 * 1024)
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


def _reject_duplicate_headers(headers: list[str]) -> None:
    # Duplicate column names would silently overwrite each other in the row dicts.
    named = [header for header in headers if header]
    if len(set(named)) != len(named):
        raise ValueError("Tabular header contains duplicate column names")
    # Several unnamed columns share the empty-string key and would overwrite each other.
    if len(headers) - len(named) > 1:
        raise ValueError("Tabular header has more than one unnamed column")


def load_table(content: bytes, filename: str) -> list[dict[str, Any]]:
    """Read bounded CSV/XLSX records without pandas/numpy.

    CSV uses the standard library and XLSX uses openpyxl (pure Python).  The
    obsolete binary ``.xls`` format is intentionally excluded from the lean
    microservice image; convert it to XLSX before ingestion.
    """
    suffix = str(filename or "").lower()
    if suffix.endswith(".csv"):
        reader = csv.DictReader(io.TextIOWrapper(io.BytesIO(content), encoding="utf-8-sig", newline=""))
        _reject_duplicate_headers([str(key or "").strip() for key in (reader.fieldnames or [])])
        rows = []
        for number, row in enumerate(reader, start=2):
            extra = row.pop(None, None)  # cells beyond the header; empty trailing cells are ignored
            if extra and any(str(value).strip() for value in extra):
                raise ValueError(f"CSV row {number} has more cells than the header")
            rows.append({str(key or "").strip(): _clean(value) for key, value in row.items()})
    elif suffix.endswith(".xlsx"):
        from openpyxl import load_workbook
        workbook = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        try:
            sheet = workbook.active
            # Do not trust producer-supplied dimensions: they can truncate data.
            sheet.reset_dimensions()
            values = sheet.iter_rows(values_only=True)
            headers = [str(value or "").strip() for value in next(values, ())]
            if not headers or any(not header for header in headers):
                raise ValueError("XLSX requires a non-empty header row")
            if len(set(headers)) != len(headers):
                raise ValueError("XLSX requires unique column headers")
            rows = []
            for row_number, record in enumerate(values, 2):
                if any(_clean(value) is not None for value in record[len(headers):]):
                    raise ValueError(f"XLSX row {row_number} contains values without column headers")
                rows.append({header: _clean(record[index]) if index < len(record) else None
                             for index, header in enumerate(headers)})
        finally:
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
