from __future__ import annotations

from typing import Any
from fastapi import APIRouter, HTTPException, Request
from backend.platform.authorization import approval_identity, graph_read_identity
from . import federation_service

router = APIRouter(prefix="/api/v1/sparql/federation", tags=["sparql-federation"])

@router.get("/peers")
def peers() -> dict[str, Any]: return {"peers": federation_service.all_peers()}

@router.post("/peers", status_code=201)
def register(payload: dict[str, Any], request: Request) -> dict[str, Any]:
    actor = approval_identity(request, payload, token_env="SPARQL_FEDERATION_APPROVAL_TOKEN")
    try: return federation_service.register(payload, actor)
    except FileExistsError as exc: raise HTTPException(409, str(exc)) from exc
    except ValueError as exc: raise HTTPException(422, str(exc)) from exc

@router.post("/peers/{peer_id}/approve")
def approve(peer_id: str, payload: dict[str, Any], request: Request) -> dict[str, Any]:
    actor = approval_identity(request, payload, token_env="SPARQL_FEDERATION_APPROVAL_TOKEN")
    try: return federation_service.approve(peer_id, actor)
    except LookupError as exc: raise HTTPException(404, str(exc)) from exc

@router.post("/peers/{peer_id}/query")
async def query(peer_id: str, payload: dict[str, Any], request: Request) -> dict[str, Any]:
    actor = graph_read_identity(request)
    try: return await federation_service.query(peer_id, payload, actor)
    except LookupError as exc: raise HTTPException(404, str(exc)) from exc
    except ValueError as exc: raise HTTPException(422, str(exc)) from exc
    except RuntimeError as exc: raise HTTPException(503, str(exc)) from exc
