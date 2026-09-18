"""HTTP transport for the graph service's deliberately read-only GraphQL API."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request

from backend.depo_platform.authorization import graph_read_identity
from .graphql_schema import execute

router = APIRouter(prefix="/api/v1/graphql", tags=["graphql"])


@router.post("", summary="Execute a bounded read-only graph query")
def query(payload: dict[str, Any], request: Request) -> dict[str, Any]:
    graph_read_identity(request)
    document = str(payload.get("query") or "")
    if not document.strip() or len(document) > 10_000:
        raise HTTPException(422, "query is required and must be at most 10000 characters")
    result = execute(document, variables=payload.get("variables"), operation_name=payload.get("operationName"))
    if result.get("errors"):
        raise HTTPException(400, result)
    return result
