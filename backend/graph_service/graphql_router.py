"""HTTP transport for the graph service's deliberately read-only GraphQL API."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from graphql import GraphQLError, parse

from backend.depo_platform.authorization import graph_read_identity
from .graphql_schema import execute

router = APIRouter(prefix="/api/v1/graphql", tags=["graphql"])
MAX_FIELDS = 25
MAX_DEPTH = 4


def _validate_complexity(document: str) -> None:
    """Reject alias fan-out before any resolver can reach Neo4j."""
    try:
        parsed = parse(document)
    except GraphQLError as exc:
        raise HTTPException(400, {"errors": [{"message": exc.message}]}) from exc
    fields = 0
    def visit(selection_set, depth: int) -> None:
        nonlocal fields
        if depth > MAX_DEPTH:
            raise HTTPException(422, f"GraphQL query depth must not exceed {MAX_DEPTH}")
        for selection in selection_set.selections:
            if getattr(selection, "selection_set", None):
                visit(selection.selection_set, depth + 1)
            if selection.__class__.__name__ == "FieldNode":
                fields += 1
                if fields > MAX_FIELDS:
                    raise HTTPException(422, f"GraphQL query must not select more than {MAX_FIELDS} fields")
    for definition in parsed.definitions:
        if getattr(definition, "selection_set", None): visit(definition.selection_set, 1)


@router.post("", summary="Execute a bounded read-only graph query")
def query(payload: dict[str, Any], request: Request) -> dict[str, Any]:
    graph_read_identity(request)
    document = str(payload.get("query") or "")
    if not document.strip() or len(document) > 10_000:
        raise HTTPException(422, "query is required and must be at most 10000 characters")
    _validate_complexity(document)
    result = execute(document, variables=payload.get("variables"), operation_name=payload.get("operationName"))
    if result.get("errors"):
        raise HTTPException(400, result)
    return result
