from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request

from backend.depo_platform.authorization import graph_read_identity
from .sparql_service import sparql


router = APIRouter(prefix="/api/v1/sparql", tags=["sparql"])


@router.post("", summary="Execute bounded read-only SPARQL over one ontology projection")
def query(payload: dict[str, Any], request: Request) -> dict[str, Any]:
    identity = graph_read_identity(request)
    try:
        return {**sparql.execute(ontology_id=str(payload.get("ontology_id") or ""), query=str(payload.get("query") or ""), limit=int(payload.get("limit") or 200)), "executed_by": identity}
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"SPARQL projection failed: {type(exc).__name__}: {exc}") from exc
