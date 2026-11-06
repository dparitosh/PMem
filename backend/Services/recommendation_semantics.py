"""Semantic ranking helpers for recommendation source selection."""

from __future__ import annotations

from difflib import SequenceMatcher
from typing import Mapping, Any


PART_LIKE_TERMS = (
    "part",
    "product",
    "item",
    "assembly",
    "component",
    "physical",
    "material",
    "design",
)

PROCESS_LIKE_TERMS = (
    "process",
    "operation",
    "activity",
    "manufacturing",
    "maintenance",
)

DEMOTED_TERMS = (
    "requirement",
    "function",
    "logical",
    "document",
    "dataset",
    "accessintent",
    "generalrelation",
    "relationshipcarrier",
    "attributecontext",
    "metadatawrapper",
)


def semantic_source_score(query: str, row: Mapping[str, Any], *, prefer: str = "part") -> float:
    """Score candidate source rows using lexical fit plus ontology/business type.

    This keeps recommendation source selection data-driven: labels, ontology class,
    and instance properties decide the preference rather than a single hardcoded DB.
    """
    query_l = (query or "").strip().lower()
    name = str(row.get("name") or "").strip()
    name_l = name.lower()
    labels = " ".join(str(item) for item in (row.get("labels") or [])).lower()
    source_tag = str(row.get("source_tag") or row.get("class_name") or "").lower()
    element_type = str(row.get("element_type") or row.get("type") or row.get("sub_type") or "").lower()
    haystack = " ".join([name_l, labels, source_tag, element_type])

    score = SequenceMatcher(None, query_l, name_l).ratio() * 100.0
    if query_l and name_l == query_l:
        score += 70.0
    elif query_l and name_l.startswith(query_l):
        score += 45.0
    elif query_l and query_l in name_l:
        score += 25.0

    preferred_terms = PROCESS_LIKE_TERMS if prefer == "process" else PART_LIKE_TERMS
    if any(term in haystack for term in preferred_terms):
        score += 80.0
    if any(term in haystack for term in DEMOTED_TERMS):
        score -= 70.0
    if name_l.startswith("id"):
        score -= 90.0
    return score


def pick_semantic_source(query: str, rows: list[Mapping[str, Any]], *, prefer: str = "part") -> Mapping[str, Any] | None:
    """Return the best source candidate while preserving the original row shape."""
    if not rows:
        return None
    return max(rows, key=lambda row: semantic_source_score(query, row, prefer=prefer))
