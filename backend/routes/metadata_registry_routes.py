"""Governed metadata registry endpoints, separate from ontology browsing."""

from datetime import datetime, timezone
from typing import Any, Dict, Optional
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field, field_validator, model_validator

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

    @field_validator("effective_from", "effective_to")
    @classmethod
    def validate_effective_date(cls, value: str) -> str:
        text = str(value or "").strip()
        if text:
            try:
                datetime.fromisoformat(text.replace("Z", "+00:00"))
            except ValueError as exc:
                raise ValueError("effective dates must use ISO-8601 format") from exc
        return text

    @model_validator(mode="after")
    def validate_effective_window(self):
        if self.effective_from and self.effective_to:
            start = datetime.fromisoformat(self.effective_from.replace("Z", "+00:00"))
            end = datetime.fromisoformat(self.effective_to.replace("Z", "+00:00"))
            if (start.tzinfo is None) != (end.tzinfo is None):
                raise ValueError("effective dates must use consistent timezone qualification")
            if end < start:
                raise ValueError("effective_to cannot precede effective_from")
        return self


class MetadataAssetUpdateRequest(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=300)
    definition: Optional[str] = Field(default=None, max_length=10000)
    asset_type: Optional[str] = Field(default=None, max_length=100)
    domain: Optional[str] = Field(default=None, max_length=200)
    owner: Optional[str] = Field(default=None, max_length=200)
    steward: Optional[str] = Field(default=None, max_length=200)
    source_system: Optional[str] = Field(default=None, max_length=200)
    lifecycle_status: Optional[str] = Field(default=None, max_length=50)
    version: Optional[str] = Field(default=None, max_length=50)
    effective_from: Optional[str] = Field(default=None, max_length=50)
    effective_to: Optional[str] = Field(default=None, max_length=50)
    ontology_uri: Optional[str] = Field(default=None, max_length=2000)
    implementation_ref: Optional[str] = Field(default=None, max_length=2000)

    @field_validator("effective_from", "effective_to")
    @classmethod
    def validate_effective_date(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        text = str(value).strip()
        if text:
            try:
                datetime.fromisoformat(text.replace("Z", "+00:00"))
            except ValueError as exc:
                raise ValueError("effective dates must use ISO-8601 format") from exc
        return text

    @model_validator(mode="after")
    def validate_effective_window(self):
        if self.effective_from and self.effective_to:
            start = datetime.fromisoformat(self.effective_from.replace("Z", "+00:00"))
            end = datetime.fromisoformat(self.effective_to.replace("Z", "+00:00"))
            if (start.tzinfo is None) != (end.tzinfo is None):
                raise ValueError("effective dates must use consistent timezone qualification")
            if end < start:
                raise ValueError("effective_to cannot precede effective_from")
        return self


class LifecycleTransitionRequest(BaseModel):
    status: str = Field(min_length=1, max_length=50)
    actor: str = Field(default="", max_length=200)
    comment: str = Field(default="", max_length=5000)

    @field_validator("status")
    @classmethod
    def validate_status(cls, value: str) -> str:
        status = str(value or "").strip().lower()
        if status not in {"draft", "in_review", "approved", "deprecated", "retired"}:
            raise ValueError("Unsupported lifecycle status")
        return status


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


def _ensure_metadata_constraints() -> None:
    graph.query(
        "CREATE CONSTRAINT metadata_asset_id IF NOT EXISTS "
        "FOR (a:MetadataAsset) REQUIRE a.asset_id IS UNIQUE"
    )


@router.post("/assets", status_code=201)
def create_metadata_asset(request: MetadataAssetRequest):
    now = _now()
    payload = request.model_dump()
    payload.update({"asset_id": request.asset_id or str(uuid4()), "created_at": now, "updated_at": now, "event_id": str(uuid4()), "actor": request.owner, "comment": ""})
    _ensure_metadata_constraints()
    create_query = _asset_mutation_query("created").replace(
        "MERGE (a:MetadataAsset {asset_id: $asset_id})\n        ON CREATE SET a.created_at = $created_at",
        "CREATE (a:MetadataAsset {asset_id: $asset_id})\n        SET a.created_at = $created_at",
        1,
    )
    try:
        rows = graph.query(create_query, params=payload) or []
    except Exception as exc:
        if "constraint" in str(exc).lower() or "already exists" in str(exc).lower():
            raise HTTPException(status_code=409, detail="Metadata asset already exists") from exc
        raise
    if not rows:
        raise HTTPException(status_code=500, detail="Metadata asset could not be created")
    return _row_asset(rows[0])


@router.patch("/assets/{asset_id}")
def update_metadata_asset(asset_id: str, request: MetadataAssetUpdateRequest):
    now = _now()
    updates = request.model_dump(exclude_unset=True, exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail="At least one metadata field is required")
    rows = graph.query(
        """
        MATCH (a:MetadataAsset {asset_id: $asset_id})
        WITH a, keys($updates) AS changed_fields,
             [key IN keys($updates) | coalesce(toString(a[key]), '')] AS before_values
        SET a += $updates, a.updated_at = $updated_at
        WITH a, changed_fields, before_values,
             [key IN changed_fields | coalesce(toString(a[key]), '')] AS after_values
        CREATE (e:MetadataAuditEvent {event_id: $event_id})
        SET e.action = 'updated', e.actor = $actor, e.comment = '',
            e.created_at = $updated_at, e.changed_fields = changed_fields,
            e.before_values = before_values, e.after_values = after_values
        CREATE (a)-[:HAS_AUDIT_EVENT]->(e)
        RETURN properties(a) AS asset
        """,
        params={
            "asset_id": asset_id,
            "updates": updates,
            "updated_at": now,
            "event_id": str(uuid4()),
            "actor": str(updates.get("owner") or ""),
        },
    ) or []
    if not rows:
        raise HTTPException(status_code=404, detail="Metadata asset not found")
    return _row_asset(rows[0])


@router.post("/assets/{asset_id}/transition")
def transition_metadata_asset(asset_id: str, request: LifecycleTransitionRequest):
    allowed_from = {
        "draft": ["draft", "in_review"],
        "in_review": ["in_review", "draft"],
        "approved": ["approved", "in_review"],
        "deprecated": ["deprecated", "approved"],
        "retired": ["retired", "draft", "in_review", "approved", "deprecated"],
    }[request.status]
    rows = graph.query(
        """
        MATCH (a:MetadataAsset {asset_id: $asset_id})
        WHERE coalesce(a.lifecycle_status, 'draft') IN $allowed_from
        WITH a, coalesce(a.lifecycle_status, 'draft') AS previous_status
        SET a.lifecycle_status = $status, a.updated_at = $updated_at
        WITH a
        MERGE (e:MetadataAuditEvent {event_id: $event_id})
        SET e.action = 'lifecycle_transition', e.actor = $actor,
            e.comment = $comment, e.status = $status, e.previous_status = previous_status,
            e.changed_fields = ['lifecycle_status'], e.before_values = [previous_status],
            e.after_values = [$status], e.created_at = $updated_at
        MERGE (a)-[:HAS_AUDIT_EVENT]->(e)
        RETURN properties(a) AS asset
        """,
        params={"asset_id": asset_id, "status": request.status, "allowed_from": allowed_from, "actor": request.actor, "comment": request.comment, "event_id": str(uuid4()), "updated_at": _now()},
    ) or []
    if not rows:
        existing = graph.query(
            "MATCH (a:MetadataAsset {asset_id: $asset_id}) RETURN a.lifecycle_status AS status LIMIT 1",
            params={"asset_id": asset_id},
        ) or []
        if existing:
            raise HTTPException(status_code=409, detail=f"Invalid lifecycle transition from {existing[0].get('status') or 'draft'} to {request.status}")
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
    if not rows:
        exists = graph.query(
            "MATCH (a:MetadataAsset {asset_id: $asset_id}) RETURN a.asset_id AS asset_id LIMIT 1",
            params={"asset_id": asset_id},
        ) or []
        if not exists:
            raise HTTPException(status_code=404, detail="Metadata asset not found")
    return {"events": [dict(row.get("event") or row) for row in rows], "count": len(rows)}
