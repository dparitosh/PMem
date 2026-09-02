"""Standalone API boundary for the governed modeling workbench."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from backend.Services import agentic_modeling_service, modeling_service

router = APIRouter(prefix="/modeling", tags=["modeling"])


def _call(operation, *args, **kwargs):
    try:
        return operation(*args, **kwargs)
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/metamodel")
def metamodel() -> dict: return _call(modeling_service.metamodel)

@router.post("/indexes")
def ensure_indexes() -> dict: return _call(modeling_service.ensure_indexes)

@router.get("/graph")
def graph(project: str = "Digital Engineering Model", search: str = "", limit: int = Query(500, ge=1, le=2000)) -> dict:
    return _call(modeling_service.list_graph, project=project, search=search, limit=limit)

@router.get("/tree")
def tree(project: str = "Digital Engineering Model") -> dict: return _call(modeling_service.tree, project=project)

@router.get("/search")
def search(q: str, project: str = "Digital Engineering Model", limit: int = Query(50, ge=1, le=200)) -> dict:
    return _call(modeling_service.search, query=q, project=project, limit=limit)

@router.get("/context/{element_id}")
def context(element_id: str, depth: int = Query(1, ge=1, le=2), limit: int = Query(300, ge=1, le=1000)) -> dict:
    return _call(modeling_service.context, element_id=element_id, depth=depth, limit=limit)

@router.post("/nodes")
def create_node(payload: dict[str, Any]) -> dict: return _call(modeling_service.create_node, payload)

@router.put("/nodes/{element_id}")
def update_node(element_id: str, payload: dict[str, Any]) -> dict: return _call(modeling_service.update_node, element_id, payload)

@router.delete("/nodes/{element_id}")
def delete_node(element_id: str) -> dict: return _call(modeling_service.delete_node, element_id)

@router.post("/links")
def create_link(payload: dict[str, Any]) -> dict: return _call(modeling_service.create_link, payload)

@router.put("/links/{element_id}")
def update_link(element_id: str, payload: dict[str, Any]) -> dict: return _call(modeling_service.update_link, element_id, payload)

@router.delete("/links/{element_id}")
def delete_link(element_id: str) -> dict: return _call(modeling_service.delete_link, element_id)

@router.get("/validation")
def validation(project: str = "Digital Engineering Model") -> dict: return _call(modeling_service.validate, project=project)

@router.post("/seed")
def seed(payload: dict[str, Any] | None = None) -> dict:
    return _call(modeling_service.seed_sample, project=(payload or {}).get("project") or "Digital Engineering Model")

@router.post("/agent/proposals")
def create_proposal(payload: dict[str, Any]) -> dict: return _call(agentic_modeling_service.create_proposal, payload)

@router.get("/agent/proposals")
def list_proposals(project: str = "Digital Engineering Model", limit: int = Query(50, ge=1, le=200)) -> dict:
    return _call(agentic_modeling_service.list_proposals, project=project, limit=limit)

@router.post("/agent/proposals/{proposal_id}/approve")
def approve_proposal(proposal_id: str, payload: dict[str, Any] | None = None) -> dict:
    data = payload or {}
    return _call(agentic_modeling_service.approve_proposal, proposal_id, approved_by=data.get("approved_by") or "user", comment=data.get("comment") or "")

@router.post("/agent/proposals/{proposal_id}/reject")
def reject_proposal(proposal_id: str, payload: dict[str, Any] | None = None) -> dict:
    data = payload or {}
    return _call(agentic_modeling_service.reject_proposal, proposal_id, rejected_by=data.get("rejected_by") or "user", comment=data.get("comment") or "")
