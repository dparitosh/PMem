"""Agentic proposal workflow for ontology modeling.

The agent layer never mutates Neo4j directly from a prompt. It stores proposal,
validation, approval/rejection, and audit state. Execution can later map approved
plans to explicit modeling CRUD calls.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Dict, List

from backend.core.graph import query_with_timeout
from backend.Services import modeling_service
from backend.Services.unstructured_agent_pipeline import build_unstructured_plan


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _proposal_id(payload: Dict[str, Any]) -> str:
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:16]
    return f"proposal:{digest}"



def _storage_props(proposal: Dict[str, Any]) -> Dict[str, Any]:
    props: Dict[str, Any] = {}
    for key, value in proposal.items():
        if isinstance(value, (dict, list)):
            props[key] = json.dumps(value, ensure_ascii=False, default=str)
        else:
            props[key] = value
    return props


def _decode_props(props: Dict[str, Any] | None) -> Dict[str, Any] | None:
    if not props:
        return props
    decoded = dict(props)
    for key in ("steps", "validation_summary", "unstructured_plan"):
        value = decoded.get(key)
        if isinstance(value, str) and value[:1] in {"[", "{"}:
            try:
                decoded[key] = json.loads(value)
            except Exception:
                pass
    return decoded
def _intent(prompt: str) -> str:
    text = (prompt or "").lower()
    if "impact" in text:
        return "impact_analysis"
    if "layout" in text or "cleanup" in text:
        return "layout_cleanup"
    if "missing" in text or "validate" in text:
        return "validation_review"
    if "diagram" in text or "create" in text:
        return "diagram_proposal"
    return "context_summary"


def create_proposal(payload: Dict[str, Any]) -> Dict[str, Any]:
    prompt = str(payload.get("prompt") or payload.get("message") or "").strip()
    project = str(payload.get("project") or modeling_service.DEFAULT_PROJECT).strip()
    context = payload.get("context") if isinstance(payload.get("context"), dict) else {}
    intent = _intent(prompt)
    validation = modeling_service.validate(project=project)
    unstructured_plan = build_unstructured_plan(payload.get("document") or payload.get("metadata") or {}) if intent in {"diagram_proposal", "context_summary"} else None
    proposal = {
        "id": _proposal_id({"prompt": prompt, "project": project, "context": context, "created_at": _now()}),
        "project": project,
        "intent": intent,
        "prompt": prompt,
        "status": "proposed",
        "created_at": _now(),
        "steps": [
            {"kind": "inspect_context", "description": "Review selected model context and ontology mapping."},
            {"kind": "validate", "description": "Check missing properties, orphan nodes, duplicates, and relationship rules."},
            {"kind": "recommend", "description": "Return candidate nodes, relationships, layout, or impact summary for user approval."},
        ],
        "validation_summary": validation.get("counts", {}),
        "requires_human_approval": True,
        "safe_execution": "No Neo4j mutation is executed by proposal creation.",
        "unstructured_plan": unstructured_plan,
    }
    query_with_timeout(
        """
        MERGE (p:AgentProposal {id: $id})
        SET p += $props, p.updated_at = datetime()
        ON CREATE SET p.created_at = datetime()
        RETURN p.id AS id
        """,
        {"id": proposal["id"], "props": _storage_props(proposal)},
        timeout=60,
    )
    return {"proposal": proposal}


def list_proposals(project: str = modeling_service.DEFAULT_PROJECT, limit: int = 50) -> Dict[str, Any]:
    rows = query_with_timeout(
        """
        MATCH (p:AgentProposal)
        WHERE coalesce(p.project, $project) = $project
        RETURN properties(p) AS proposal
        ORDER BY p.created_at DESC
        LIMIT $limit
        """,
        {"project": project or modeling_service.DEFAULT_PROJECT, "limit": max(1, min(int(limit or 50), 200))},
        timeout=60,
    ) or []
    return {"proposals": [_decode_props(row.get("proposal")) for row in rows if row.get("proposal")]}


def approve_proposal(proposal_id: str, approved_by: str = "user", comment: str = "") -> Dict[str, Any]:
    rows = query_with_timeout(
        """
        MATCH (p:AgentProposal {id: $id})
        SET p.status = 'approved', p.approved_by = $approved_by, p.approval_comment = $comment, p.approved_at = datetime(), p.updated_at = datetime()
        RETURN properties(p) AS proposal
        """,
        {"id": proposal_id, "approved_by": approved_by or "user", "comment": comment or ""},
        timeout=60,
    ) or []
    return {"proposal": _decode_props(rows[0].get("proposal")) if rows else None, "executed": False, "message": "Approved proposal recorded. Execute through explicit CRUD/import action."}


def reject_proposal(proposal_id: str, rejected_by: str = "user", comment: str = "") -> Dict[str, Any]:
    rows = query_with_timeout(
        """
        MATCH (p:AgentProposal {id: $id})
        SET p.status = 'rejected', p.rejected_by = $rejected_by, p.rejection_comment = $comment, p.rejected_at = datetime(), p.updated_at = datetime()
        RETURN properties(p) AS proposal
        """,
        {"id": proposal_id, "rejected_by": rejected_by or "user", "comment": comment or ""},
        timeout=60,
    ) or []
    return {"proposal": _decode_props(rows[0].get("proposal")) if rows else None}


