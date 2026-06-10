"""Shared helpers for canonical ontology identity and registry rows."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional


def _text(value: Any) -> str:
    return str(value or "").strip()


def _first(*values: Any) -> str:
    for value in values:
        text = _text(value)
        if text:
            return text
    return ""


def normalize_ontology_entry(row: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Return a canonical registry row with consistent ontology identity fields."""
    data = dict(row or {})

    ontology_id = _first(
        data.get("ontology_id"),
        data.get("id"),
        data.get("value"),
        data.get("prefix"),
        data.get("ontology_prefix"),
        data.get("name"),
    )
    prefix = _first(
        data.get("prefix"),
        data.get("ontology_prefix"),
        ontology_id,
    )
    ontology_name = _first(
        data.get("ontology_name"),
        data.get("name"),
        data.get("label"),
        ontology_id,
        prefix,
    )
    namespace = _first(
        data.get("namespace"),
        data.get("source_namespace"),
        data.get("target_namespace"),
    )
    source_namespace = _first(
        data.get("source_namespace"),
        namespace,
    )

    node_count = int(data.get("node_count") or data.get("neo4j_nodes_merged") or 0)
    relationship_count = int(data.get("relationship_count") or data.get("neo4j_relationships_merged") or 0)
    status = _first(data.get("status"), data.get("availability"), "uploaded")
    source = _first(data.get("source"), "registered")

    normalized = dict(data)
    normalized.update({
        "ontology_id": ontology_id or prefix,
        "id": ontology_id or prefix,
        "value": _first(data.get("value"), ontology_id or prefix),
        "name": ontology_name,
        "label": _first(data.get("label"), ontology_name),
        "ontology_name": ontology_name,
        "prefix": prefix,
        "ontology_prefix": _first(data.get("ontology_prefix"), prefix),
        "namespace": namespace,
        "source_namespace": source_namespace,
        "target_namespace": _first(data.get("target_namespace"), namespace),
        "source": source,
        "status": status,
        "availability": _first(data.get("availability"), "metadata_only"),
        "node_count": node_count,
        "relationship_count": relationship_count,
        "schema_type": _first(data.get("schema_type"), "schema"),
    })
    return normalized


def normalize_ontology_entries(rows: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [normalize_ontology_entry(row) for row in rows]

