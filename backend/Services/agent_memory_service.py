"""Graph-native agent memory adapter.

This module adds the practical parts of Neo4j Labs Agent Memory to this app
without making the release depend on an experimental SDK.  It records durable
short-term chat turns, reasoning traces, and long-term semantic bridge facts in
Neo4j using the app's existing official Neo4j driver.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, ClassVar, Dict, Iterable, List, Optional

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _truthy(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on", "enabled"}


def _safe_json(value: Any, limit: int = 12000) -> str:
    try:
        text = json.dumps(value or {}, default=str, ensure_ascii=False)
    except Exception:
        text = str(value or "")
    return text[:limit]


def _stable_id(*parts: Any) -> str:
    payload = "|".join(str(part or "") for part in parts)
    return hashlib.sha256(payload.encode("utf-8", errors="ignore")).hexdigest()[:32]


class AgentMemoryService:
    """Best-effort graph memory for chat, reasoning traces, and bridge facts."""

    _schema_attempted: ClassVar[bool] = False

    @classmethod
    def enabled(cls) -> bool:
        return _truthy(os.getenv("AGENT_MEMORY_ENABLED", "false"))

    @classmethod
    def sdk_available(cls) -> bool:
        try:
            import neo4j_agent_memory  # noqa: F401

            return True
        except Exception:
            return False

    @classmethod
    def status(cls) -> Dict[str, Any]:
        return {
            "enabled": cls.enabled(),
            "mode": "local_neo4j_adapter",
            "sdk_available": cls.sdk_available(),
            "scope": os.getenv("AGENT_MEMORY_SCOPE", "project"),
            "database": os.getenv("AGENT_MEMORY_NEO4J_DATABASE") or os.getenv("NEO4J_DATABASE", "neo4j"),
            "memory_layers": ["short_term", "long_term", "reasoning"],
            "best_effort": True,
        }

    @classmethod
    def _query(cls, cypher: str, params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        if not cls.enabled():
            return []
        try:
            try:
                timeout = max(1, min(int(os.getenv("AGENT_MEMORY_QUERY_TIMEOUT", "5")), 30))
            except Exception:
                timeout = 5
            memory_database = str(os.getenv("AGENT_MEMORY_NEO4J_DATABASE") or "").strip()
            if memory_database:
                try:
                    from backend.core.db_config import get_driver
                except ModuleNotFoundError:
                    from core.db_config import get_driver
                from neo4j import Query

                driver = get_driver()
                with driver.session(database=memory_database) as session:
                    return session.run(Query(cypher, timeout=float(timeout)), params or {}).data()

            try:
                from backend.core.graph import query_with_timeout
            except ModuleNotFoundError:
                from core.graph import query_with_timeout
            return query_with_timeout(cypher, params or {}, timeout=timeout) or []
        except Exception as exc:
            logger.warning("Agent memory write skipped: %s", exc)
            return []

    @classmethod
    def ensure_schema(cls) -> Dict[str, Any]:
        """Create lightweight constraints/indexes for memory nodes."""
        if not cls.enabled():
            return {"enabled": False, "ensured": False}
        if cls._schema_attempted:
            return {"enabled": True, "ensured": True, "cached": True}

        statements = [
            "CREATE CONSTRAINT agent_memory_session_id IF NOT EXISTS FOR (s:AgentMemorySession) REQUIRE s.session_id IS UNIQUE",
            "CREATE CONSTRAINT agent_memory_message_id IF NOT EXISTS FOR (m:AgentMemoryMessage) REQUIRE m.message_id IS UNIQUE",
            "CREATE CONSTRAINT agent_memory_trace_id IF NOT EXISTS FOR (t:AgentMemoryTrace) REQUIRE t.trace_id IS UNIQUE",
            "CREATE CONSTRAINT agent_memory_fact_id IF NOT EXISTS FOR (f:AgentMemoryFact) REQUIRE f.fact_id IS UNIQUE",
            "CREATE INDEX agent_memory_message_text IF NOT EXISTS FOR (m:AgentMemoryMessage) ON (m.text)",
            "CREATE INDEX agent_memory_fact_kind IF NOT EXISTS FOR (f:AgentMemoryFact) ON (f.kind)",
        ]
        for statement in statements:
            cls._query(statement)
        cls._schema_attempted = True
        return {"enabled": True, "ensured": True, "statement_count": len(statements)}

    @classmethod
    def record_chat_turn(
        cls,
        *,
        session_id: str,
        user_message: str,
        assistant_response: str,
        graph_context: Optional[Dict[str, Any]] = None,
        status: str = "completed",
    ) -> None:
        """Persist one chat turn and optional graph context as short-term memory."""
        if not cls.enabled():
            return
        cls.ensure_schema()
        turn_id = _stable_id(session_id, user_message, assistant_response, _now_iso())
        user_id = f"{turn_id}:user"
        assistant_id = f"{turn_id}:assistant"
        touched_nodes = cls._extract_touched_nodes(graph_context)
        cls._query(
            """
            MERGE (s:AgentMemorySession {session_id: $session_id})
            ON CREATE SET s.created_at = $now
            SET s.updated_at = $now,
                s.scope = $scope
            MERGE (u:AgentMemoryMessage {message_id: $user_id})
            SET u.role = 'user',
                u.text = $user_message,
                u.created_at = $now,
                u.status = $status
            MERGE (a:AgentMemoryMessage {message_id: $assistant_id})
            SET a.role = 'assistant',
                a.text = $assistant_response,
                a.created_at = $now,
                a.status = $status
            MERGE (s)-[:HAS_MESSAGE]->(u)
            MERGE (s)-[:HAS_MESSAGE]->(a)
            MERGE (u)-[:FOLLOWED_BY]->(a)
            WITH a
            UNWIND $touched_nodes AS touched
            MATCH (n)
            WHERE elementId(n) = touched.element_id
            MERGE (a)-[r:TOUCHED]->(n)
            SET r.label = touched.label,
                r.touched_at = $now
            RETURN count(*) AS touched_count
            """,
            {
                "session_id": session_id,
                "user_id": user_id,
                "assistant_id": assistant_id,
                "user_message": str(user_message or "")[:4000],
                "assistant_response": str(assistant_response or "")[:12000],
                "status": status,
                "scope": os.getenv("AGENT_MEMORY_SCOPE", "project"),
                "touched_nodes": touched_nodes[:100],
                "now": _now_iso(),
            },
        )

    @classmethod
    def record_reasoning_trace(
        cls,
        *,
        session_id: str,
        task: str,
        tool_name: str,
        input_payload: Optional[Dict[str, Any]] = None,
        result_summary: Optional[Dict[str, Any]] = None,
        success: bool = True,
    ) -> None:
        """Persist a reasoning/tool trace with compact provenance."""
        if not cls.enabled():
            return
        cls.ensure_schema()
        trace_id = _stable_id(session_id, task, tool_name, _safe_json(input_payload), _now_iso())
        cls._query(
            """
            MERGE (s:AgentMemorySession {session_id: $session_id})
            ON CREATE SET s.created_at = $now
            SET s.updated_at = $now
            MERGE (t:AgentMemoryTrace {trace_id: $trace_id})
            SET t.task = $task,
                t.tool_name = $tool_name,
                t.input_payload = $input_payload,
                t.result_summary = $result_summary,
                t.success = $success,
                t.created_at = $now
            MERGE (s)-[:HAS_REASONING_TRACE]->(t)
            RETURN t.trace_id AS trace_id
            """,
            {
                "session_id": session_id,
                "trace_id": trace_id,
                "task": str(task or "")[:500],
                "tool_name": str(tool_name or "")[:120],
                "input_payload": _safe_json(input_payload),
                "result_summary": _safe_json(result_summary),
                "success": bool(success),
                "now": _now_iso(),
            },
        )

    @classmethod
    def record_semantic_bridge_mappings(
        cls,
        *,
        ontology_id: str,
        import_task_id: str,
        mappings: Iterable[Dict[str, Any]],
        task_id: str = "",
    ) -> None:
        """Store approved semantic bridge mappings as reusable long-term facts."""
        rows = [
            cls._mapping_fact_row(ontology_id, import_task_id, mapping, task_id)
            for mapping in mappings
            if mapping and (mapping.get("selected_for_apply") or mapping.get("approvedByUser"))
        ]
        rows = [row for row in rows if row.get("source") and row.get("target")]
        if not rows or not cls.enabled():
            return
        cls.ensure_schema()
        cls._query(
            """
            UNWIND $rows AS row
            MERGE (f:AgentMemoryFact {fact_id: row.fact_id})
            SET f.kind = 'semantic_bridge_mapping',
                f.source = row.source,
                f.source_type = row.source_type,
                f.target = row.target,
                f.target_type = row.target_type,
                f.ontology_id = row.ontology_id,
                f.import_task_id = row.import_task_id,
                f.confidence = row.confidence,
                f.mapping_type = row.mapping_type,
                f.task_id = row.task_id,
                f.updated_at = $now
            ON CREATE SET f.created_at = $now
            RETURN count(f) AS stored
            """,
            {"rows": rows[:5000], "now": _now_iso()},
        )

    @classmethod
    def recent_context(cls, session_id: str, limit: int = 6) -> Dict[str, Any]:
        """Return compact memory context for future prompt augmentation."""
        if not cls.enabled():
            return {"enabled": False, "messages": [], "facts": []}
        rows = cls._query(
            """
            MATCH (:AgentMemorySession {session_id: $session_id})-[:HAS_MESSAGE]->(m:AgentMemoryMessage)
            RETURN m.role AS role, m.text AS text, m.created_at AS created_at
            ORDER BY m.created_at DESC
            LIMIT toInteger($limit)
            """,
            {"session_id": session_id, "limit": max(1, min(int(limit or 6), 20))},
        )
        return {"enabled": True, "messages": rows, "facts": []}

    @classmethod
    def semantic_bridge_facts(cls, ontology_id: str = "", limit: int = 1000) -> List[Dict[str, Any]]:
        """Return approved Semantic Bridge facts for mapping reuse."""
        if not cls.enabled():
            return []
        rows = cls._query(
            """
            MATCH (f:AgentMemoryFact {kind: 'semantic_bridge_mapping'})
            WHERE $ontology_id = '' OR f.ontology_id = $ontology_id
            RETURN f.source AS source,
                   f.source_type AS source_type,
                   f.target AS target,
                   f.target_type AS target_type,
                   f.ontology_id AS ontology_id,
                   f.confidence AS confidence,
                   f.mapping_type AS mapping_type,
                   f.updated_at AS updated_at
            ORDER BY f.updated_at DESC
            LIMIT toInteger($limit)
            """,
            {
                "ontology_id": str(ontology_id or "").strip(),
                "limit": max(1, min(int(limit or 1000), 5000)),
            },
        )
        return rows or []

    @classmethod
    def _mapping_fact_row(cls, ontology_id: str, import_task_id: str, mapping: Dict[str, Any], task_id: str) -> Dict[str, Any]:
        source = str(mapping.get("source_term") or mapping.get("source_label") or mapping.get("import_row_key") or "").strip()
        target = str(mapping.get("ontology_term") or mapping.get("target_term") or mapping.get("target_ontology_iri") or "").strip()
        return {
            "fact_id": _stable_id("semantic_bridge", ontology_id, import_task_id, source, target, mapping.get("target_ontology_type")),
            "source": source[:500],
            "source_type": str(mapping.get("source_type") or "")[:80],
            "target": target[:500],
            "target_type": str(mapping.get("target_ontology_type") or "")[:80],
            "ontology_id": str(ontology_id or "")[:256],
            "import_task_id": str(import_task_id or "")[:256],
            "confidence": float(mapping.get("confidence") or 0.0),
            "mapping_type": str(mapping.get("mapping_type") or "")[:80],
            "task_id": str(task_id or "")[:256],
        }

    @classmethod
    def _extract_touched_nodes(cls, graph_context: Optional[Dict[str, Any]]) -> List[Dict[str, str]]:
        context = graph_context or {}
        candidates: List[Dict[str, Any]] = []
        for key in ("selectedNode", "selected_node", "rootNode", "root_node"):
            node = context.get(key)
            if isinstance(node, dict):
                candidates.append(node)
        for key in ("nodes", "visibleNodes", "contextNodes"):
            values = context.get(key)
            if isinstance(values, list):
                candidates.extend(item for item in values if isinstance(item, dict))

        seen = set()
        touched = []
        for node in candidates:
            element_id = str(node.get("elementId") or node.get("element_id") or node.get("id") or "").strip()
            if not element_id or element_id in seen:
                continue
            seen.add(element_id)
            touched.append({
                "element_id": element_id,
                "label": str(node.get("label") or node.get("name") or node.get("type") or "")[:300],
            })
        return touched
