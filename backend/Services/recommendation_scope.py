"""Helpers for scoping recommendation queries to one or more ontologies."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any, Dict, List, Optional, Tuple


def _normalize_values(values: Any) -> List[str]:
    if values is None:
        return []
    if isinstance(values, str):
        return [values.strip()] if values.strip() else []
    if isinstance(values, dict):
        return _extract_scope_values(values)
    result: List[str] = []
    for value in values if isinstance(values, Iterable) else []:
        text = str(value or "").strip()
        if text:
            result.append(text)
    return result


def _extract_scope_values(scope: Dict[str, Any]) -> List[str]:
    values: List[str] = []
    for key in (
        "ontology_id",
        "ontology_ids",
        "prefix",
        "prefixes",
        "ontology_prefix",
        "ontology_prefixes",
        "namespace",
        "namespaces",
        "source_namespace",
        "source_namespaces",
        "target_namespace",
        "target_namespaces",
        "scope",
        "scope_ids",
    ):
        values.extend(_normalize_values(scope.get(key)))
    seen = set()
    ordered: List[str] = []
    for value in values:
        lowered = value.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        ordered.append(value)
    return ordered


def scope_values(scope: Optional[Dict[str, Any]]) -> List[str]:
    """Return the list of ontology ids / prefixes to use as a scope filter."""
    if not scope:
        return []
    return _extract_scope_values(scope)


def cypher_scope_filter(alias: str, scope: Optional[Dict[str, Any]]) -> Tuple[str, Dict[str, Any]]:
    """Build a Cypher WHERE fragment for ontology-scoped queries."""
    values = scope_values(scope)
    if not values:
        return "", {}
    return (
        f" AND coalesce({alias}.ontology_id, {alias}.source_ontology, {alias}.prefix, {alias}.ontology_prefix, '') IN $ontology_scope_values",
        {"ontology_scope_values": values},
    )
