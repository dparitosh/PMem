"""Governed metadata registry endpoints, separate from ontology browsing."""

from datetime import datetime, timezone
from typing import Any, Dict, Optional
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

try:
    from ..core.graph import graph
except ImportError:
    from core.graph import graph

router = APIRouter(prefix="/metadata-registry", tags=["metadata-registry"])


class MetadataAssetRequest(BaseModel):
    asset_id: Optional[str] = Field(default=None, min_length=1, max_length=200)
    name: str = Field(min_length=1, max_length=300)
    definition: str = Field(default="", max_length=10000)
    asset_type: str = Field(default="DataElement", max_length=100)
    domain: str = Field(default="", max_length=200)
    owner: str = Field(default="", max_length=200)
    steward: str = Field(default="", max_length=200)
    source_system: str = Field(default="", max_length=200)
    lifecycle_status: str = Field(default="draft", max_length=50)
    version: str = Field(default="1.0.0", max_length=50)
    effective_from: str = Field(default="", max_length=50)
    effective_to: str = Field(default="", max_length=50)
    ontology_uri: str = Field(default="", max_length=2000)
    implementation_ref: str = Field(default="", max_length=2000)


class LifecycleTransitionRequest(BaseModel):
    status: str = Field(min_length=1, max_length=50)
    actor: str = Field(default="", max_length=200)
    comment: str = Field(default="", max_length=5000)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_asset(row: Dict[str, Any]) -> Dict[str, Any]:
    return dict(row.get("asset") or row)


@router.get("/assets")
def list_metadata_assets(
    status: Optional[str] = Query(default=None, max_length=50),
    domain: Optional[str] = Query(default=None, max_length=200),
    limit: int = Query(default=100, ge=1, le=1000),
):
    rows = graph.query(
        """
        MATCH (a:MetadataAsset)
        WHERE ($status IS NULL OR a.lifecycle_status = $status)
          AND ($domain IS NULL OR a.domain = $domain)
        RETURN properties(a) AS asset
        ORDER BY a.name, a.version DESC
        LIMIT $limit
        """,
        params={"status": status, "domain": domain, "limit": limit},
    ) or []
    return {"assets": [_row_asset(row) for row in rows], "count": len(rows)}


@router.get("/assets/{asset_id}")
def get_metadata_asset(asset_id: str):
    rows = graph.query(
        "MATCH (a:MetadataAsset {asset_id: $asset_id}) RETURN properties(a) AS asset LIMIT 1",
        params={"asset_id": asset_id},
    ) or []
    if not rows:
        raise HTTPException(status_code=404, detail="Metadata asset not found")
    return _row_asset(rows[0])


def _asset_mutation_query(action: str) -> str:
    return f"""
        MERGE (a:MetadataAsset {{asset_id: $asset_id}})
        ON CREATE SET a.created_at = $created_at
        SET a.name = $name, a.definition = $definition, a.asset_type = $asset_type,
            a.domain = $domain, a.owner = $owner, a.steward = $steward,
            a.source_system = $source_system, a.lifecycle_status = $lifecycle_status,
            a.version = $version, a.effective_from = $effective_from,
            a.effective_to = $effective_to, a.ontology_uri = $ontology_uri,
            a.implementation_ref = $implementation_ref, a.updated_at = $updated_at
        WITH a
        MERGE (e:MetadataAuditEvent {{event_id: $event_id}})
        SET e.action = '{action}', e.actor = $actor, e.comment = $comment, e.created_at = $updated_at
        MERGE (a)-[:HAS_AUDIT_EVENT]->(e)
        RETURN properties(a) AS asset
    """


@router.post("/assets", status_code=201)
def create_metadata_asset(request: MetadataAssetRequest):
    now = _now()
    payload = request.model_dump()
    payload.update({"asset_id": request.asset_id or str(uuid4()), "created_at": now, "updated_at": now, "event_id": str(uuid4()), "actor": request.owner, "comment": ""})
    rows = graph.query(_asset_mutation_query("created"), params=payload) or []
    if not rows:
        raise HTTPException(status_code=500, detail="Metadata asset could not be created")
    return _row_asset(rows[0])


@router.patch("/assets/{asset_id}")
def update_metadata_asset(asset_id: str, request: MetadataAssetRequest):
    now = _now()
    payload = request.model_dump()
    payload.update({"asset_id": asset_id, "created_at": now, "updated_at": now, "event_id": str(uuid4()), "actor": request.owner, "comment": ""})
    rows = graph.query(_asset_mutation_query("updated").replace("MERGE (a:MetadataAsset {asset_id: $asset_id})", "MATCH (a:MetadataAsset {asset_id: $asset_id})", 1), params=payload) or []
    if not rows:
        raise HTTPException(status_code=404, detail="Metadata asset not found")
    return _row_asset(rows[0])


@router.post("/assets/{asset_id}/transition")
def transition_metadata_asset(asset_id: str, request: LifecycleTransitionRequest):
    rows = graph.query(
        """
        MATCH (a:MetadataAsset {asset_id: $asset_id})
        SET a.lifecycle_status = $status, a.updated_at = $updated_at
        WITH a
        MERGE (e:MetadataAuditEvent {event_id: $event_id})
        SET e.action = 'lifecycle_transition', e.actor = $actor,
            e.comment = $comment, e.status = $status, e.created_at = $updated_at
        MERGE (a)-[:HAS_AUDIT_EVENT]->(e)
        RETURN properties(a) AS asset
        """,
        params={"asset_id": asset_id, "status": request.status, "actor": request.actor, "comment": request.comment, "event_id": str(uuid4()), "updated_at": _now()},
    ) or []
    if not rows:
        raise HTTPException(status_code=404, detail="Metadata asset not found")
    return _row_asset(rows[0])


@router.get("/assets/{asset_id}/history")
def metadata_asset_history(asset_id: str, limit: int = Query(default=100, ge=1, le=500)):
    rows = graph.query(
        """
        MATCH (a:MetadataAsset {asset_id: $asset_id})-[:HAS_AUDIT_EVENT]->(e:MetadataAuditEvent)
        RETURN properties(e) AS event ORDER BY e.created_at DESC LIMIT $limit
        """,
        params={"asset_id": asset_id, "limit": limit},
    ) or []
    return {"events": [dict(row.get("event") or row) for row in rows], "count": len(rows)}
