"""Validated CSV/Excel parsing and Cypher planning owned by ingestion."""
from __future__ import annotations

import io
import re
from typing import Any

import pandas as pd

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


def load_table(content: bytes, filename: str) -> pd.DataFrame:
    suffix = str(filename or "").lower()
    if suffix.endswith(".csv"):
        frame = pd.read_csv(io.BytesIO(content))
    elif suffix.endswith((".xlsx", ".xls")):
        frame = pd.read_excel(io.BytesIO(content))
    else:
        raise ValueError("Unsupported tabular file type; use CSV, XLS, or XLSX")
    frame.columns = [str(column).strip() for column in frame.columns]
    return frame.replace(["", "NaN", "nan", "null", "NULL"], pd.NA).dropna(how="all")


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


def records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    return frame.where(pd.notnull(frame), None).to_dict("records")
