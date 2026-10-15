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
import threading
import time
from backend.depo_platform import agent_memory_config
from datetime import datetime, timezone
from typing import Any, ClassVar, Dict, Iterable, List, Optional

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_json(value: Any, limit: int = 12000) -> str:
    try:
        text = json.dumps(value or {}, default=str, ensure_ascii=False)
    except Exception:
        text = str(value or "")
    return text[:limit]


def _stable_id(*parts: Any) -> str:
    payload = json.dumps([str(part or '') for part in parts], ensure_ascii=True, separators=(',', ':'))
    return 'v2-' + hashlib.sha256(payload.encode('utf-8')).hexdigest()[:32]


def _legacy_id(*parts: Any) -> str:
    return hashlib.sha256('|'.join(str(part or '') for part in parts).encode('utf-8', errors='ignore')).hexdigest()[:32]


class AgentMemoryService:
    """Best-effort graph memory for chat, reasoning traces, and bridge facts."""

    _schema_attempted: ClassVar[bool] = False
    _schema_target = None
    _schema_time = 0.0
    _schema_cache = {}
    _schema_lock = threading.RLock()
    _health = {}
    SCHEMA_CONSTRAINTS = {
        'agent_memory_session_key': ('AgentMemorySession', 'memory_key'),
        'agent_memory_message_id': ('AgentMemoryMessage', 'message_id'),
        'agent_memory_trace_id': ('AgentMemoryTrace', 'trace_id'),
        'agent_memory_fact_id': ('AgentMemoryFact', 'fact_id'),
    }

    @classmethod
    def _verify_schema(cls, database=None):
        query = ('SHOW CONSTRAINTS YIELD name, type, entityType, labelsOrTypes, properties '
                 'WHERE name IN $names RETURN name, type, entityType, labelsOrTypes, properties')
        params = {'names': list(cls.SCHEMA_CONSTRAINTS)}
        rows = cls._query(query, params, database=database) if database else cls._query(query, params)
        definitions = {row.get('name'): row for row in (rows or [])}
        return all(definitions.get(name, {}).get('type') in {'UNIQUENESS', 'NODE_PROPERTY_UNIQUENESS'}
                   and definitions[name].get('entityType') == 'NODE'
                   and definitions[name].get('labelsOrTypes') == [label]
                   and definitions[name].get('properties') == [prop]
                   for name, (label, prop) in cls.SCHEMA_CONSTRAINTS.items())

    @classmethod
    def enabled(cls) -> bool:
        return agent_memory_config.enabled()

    @classmethod
    def scope(cls) -> str:
        """Return the mandatory isolation boundary used by every memory query."""
        return agent_memory_config.scope()

    @classmethod
    def _memory_key(cls, session_id: str) -> str:
        return _stable_id(cls.scope(), session_id)

    @classmethod
    def sdk_available(cls) -> bool:
        try:
            import neo4j_agent_memory  # noqa: F401

            return True
        except Exception:
            return False

    @classmethod
    def status(cls, probe=False) -> Dict[str, Any]:
        try:
            active = cls.enabled()
            scope = cls.scope() if active else ''
            agent_memory_config.query_timeout()
        except ValueError as exc:
            return {'enabled': False, 'status': 'configuration_invalid', 'invalid_setting': str(exc)}
        database = os.getenv('AGENT_MEMORY_NEO4J_DATABASE') or os.getenv('NEO4J_DATABASE', 'neo4j')
        if active and probe:
            cls._query('RETURN 1 AS ok')
            if database != os.getenv('NEO4J_DATABASE', 'neo4j'):
                cls._query('RETURN 1 AS ok', database=os.getenv('NEO4J_DATABASE', 'neo4j'))
        return {
            "enabled": active,
            'status': 'disabled' if not active else ('unavailable' if cls._health.get(database, {}).get('schema_status') == 'unavailable'
                      else cls._health.get(database, {}).get('status', 'not_verified')),
            'schema_status': cls._health.get(database, {}).get('schema_status', 'not_verified'),
            'write_status': 'disabled' if not active else cls._health.get(database, {}).get('write_status', 'not_verified'),
            "mode": "local_neo4j_adapter",
            "sdk_available": cls.sdk_available(),
            "scope": scope,
            "database": database,
            'facts_database': os.getenv('NEO4J_DATABASE', 'neo4j'),
            'facts_status': cls._health.get(os.getenv('NEO4J_DATABASE', 'neo4j'), {}).get('status', 'not_verified'),
            "memory_layers": ["short_term", "long_term", "reasoning"],
            "best_effort": True,
        }

    @classmethod
    def _query(cls, cypher: str, params: Optional[Dict[str, Any]] = None, *, database=None) -> Optional[List[Dict[str, Any]]]:
        if not cls.enabled():
            return []
        try:
            from backend.depo_platform.operations import current_operation
            from backend.depo_platform.execution_guard import ensure_execution_allowed
            ensure_execution_allowed()
            operation = current_operation()
            timeout = agent_memory_config.query_timeout()
            if operation:
                timeout = operation.timeout(timeout)
            cls.scope()
            memory_database = str(database or os.getenv("AGENT_MEMORY_NEO4J_DATABASE") or os.getenv('NEO4J_DATABASE', 'neo4j')).strip()
            if not memory_database:
                raise ValueError('AGENT_MEMORY_NEO4J_DATABASE/NEO4J_DATABASE')
            from backend.core.db_config import get_driver
            from neo4j import Query
            driver = get_driver()
            with driver.session(database=memory_database) as session:
                if operation:
                    timeout = operation.timeout(timeout)
                rows = session.run(Query(cypher, timeout=float(timeout)), params or {}).data()
            target = memory_database or os.getenv('NEO4J_DATABASE', 'neo4j')
            health = {**cls._health.get(target, {}), 'status': 'available', 'checked_at': _now_iso()}
            if any(word in cypher.upper().split() for word in ('MERGE', 'DELETE')):
                health['write_status'] = 'available'
            cls._health[target] = health
            return rows
        except Exception as exc:
            target = database or os.getenv('AGENT_MEMORY_NEO4J_DATABASE') or os.getenv('NEO4J_DATABASE', 'neo4j')
            cls._health[target] = {'status': 'unavailable', 'write_status': 'unverified', 'error_type': type(exc).__name__}
            logger.warning("Agent memory operation unavailable error_type=%s", type(exc).__name__)
            return None

    @classmethod
    def ensure_schema(cls, database=None) -> Dict[str, Any]:
        with cls._schema_lock:
            return cls._ensure_schema(database)

    @classmethod
    def _ensure_schema(cls, database=None) -> Dict[str, Any]:
        """Create lightweight constraints/indexes for memory nodes."""
        if not cls.enabled():
            return {"enabled": False, "ensured": False}
        target = (os.getenv('NEO4J_URI') or os.getenv('NEO4J_URL'),
                  database or os.getenv('AGENT_MEMORY_NEO4J_DATABASE') or os.getenv('NEO4J_DATABASE', 'neo4j'))
        if cls._schema_attempted and time.monotonic() - cls._schema_cache.get(target, float('-inf')) < 60:
            if cls._verify_schema(database):
                return {"enabled": True, "ensured": True, "cached": True}

        statements = [
            "CREATE CONSTRAINT agent_memory_session_key IF NOT EXISTS FOR (s:AgentMemorySession) REQUIRE s.memory_key IS UNIQUE",
            "CREATE CONSTRAINT agent_memory_message_id IF NOT EXISTS FOR (m:AgentMemoryMessage) REQUIRE m.message_id IS UNIQUE",
            "CREATE CONSTRAINT agent_memory_trace_id IF NOT EXISTS FOR (t:AgentMemoryTrace) REQUIRE t.trace_id IS UNIQUE",
            "CREATE CONSTRAINT agent_memory_fact_id IF NOT EXISTS FOR (f:AgentMemoryFact) REQUIRE f.fact_id IS UNIQUE",
            "CREATE INDEX agent_memory_message_text IF NOT EXISTS FOR (m:AgentMemoryMessage) ON (m.text)",
            "CREATE INDEX agent_memory_fact_kind IF NOT EXISTS FOR (f:AgentMemoryFact) ON (f.kind)",
        ]
        for statement in statements:
            result = cls._query(statement, database=database) if database else cls._query(statement)
            if result is None:
                cls._schema_attempted = False
                cls._health[target[1]] = {**cls._health.get(target[1], {}), 'schema_status': 'unavailable'}
                return {"enabled": True, "ensured": False, "error": "Neo4j memory schema initialization failed"}
        if not cls._verify_schema(database):
            cls._schema_attempted = False
            cls._health[target[1]] = {**cls._health.get(target[1], {}), 'schema_status': 'unavailable'}
            return {'enabled': True, 'ensured': False, 'error': 'Memory constraints are missing, incompatible or unavailable'}
        cls._schema_attempted = True
        cls._schema_target, cls._schema_time = target, time.monotonic()
        cls._schema_cache[target] = cls._schema_time
        cls._health[target[1]] = {**cls._health.get(target[1], {}), 'schema_status': 'available'}
        return {"enabled": True, "ensured": True, "statement_count": len(statements)}

    @classmethod
    def record_chat_turn(
        cls,
        *,
        session_id: str,
        user_message: str,
        assistant_response: str,
        graph_context: Optional[Dict[str, Any]] = None,
        generation: Optional[Dict[str, Any]] = None,
        status: str = "completed",
    ) -> None:
        """Persist one chat turn and optional graph context as short-term memory."""
        if not cls.enabled():
            return
        if not cls.ensure_schema().get('ensured'):
            return
        turn_id = _stable_id(cls.scope(), session_id, user_message, assistant_response, _now_iso())
        user_id = f"{turn_id}:user"
        assistant_id = f"{turn_id}:assistant"
        touched_nodes = cls._extract_touched_nodes(graph_context)
        cls._query(
            """
            OPTIONAL MATCH (legacy:AgentMemorySession {memory_key:$legacy_key, scope:$scope})
            WHERE coalesce(legacy.session_ref, legacy.session_id)=$session_id
              AND NOT EXISTS { MATCH (:AgentMemorySession {memory_key:$memory_key}) }
            FOREACH (old IN CASE WHEN legacy IS NULL THEN [] ELSE [legacy] END | SET old.memory_key=$memory_key)
            MERGE (s:AgentMemorySession {memory_key: $memory_key})
            ON CREATE SET s.created_at = $now
            SET s.updated_at = $now,
                s.session_id = $memory_key, s.session_ref = $session_id,
                s.scope = $scope
            MERGE (u:AgentMemoryMessage {message_id: $user_id})
            SET u.role = 'user',
                u.text = $user_message,
                u.created_at = $now,
                u.status = $status
            MERGE (a:AgentMemoryMessage {message_id: $assistant_id})
            SET a.role = 'assistant',
                a.text = $assistant_response,
                a.generation_json = $generation_json,
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
                "memory_key": cls._memory_key(session_id),
                'legacy_key': _legacy_id(cls.scope(), session_id),
                "user_id": user_id,
                "assistant_id": assistant_id,
                "user_message": str(user_message or "")[:4000],
                "assistant_response": str(assistant_response or "")[:12000],
                "generation_json": json.dumps(generation or {}),
                "status": status,
                "scope": cls.scope(),
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
        if not cls.ensure_schema().get('ensured'):
            return
        trace_id = _stable_id(cls.scope(), session_id, task, tool_name, _safe_json(input_payload), _now_iso())
        cls._query(
            """
            OPTIONAL MATCH (legacy:AgentMemorySession {memory_key:$legacy_key, scope:$scope})
            WHERE coalesce(legacy.session_ref, legacy.session_id)=$session_id
              AND NOT EXISTS { MATCH (:AgentMemorySession {memory_key:$memory_key}) }
            FOREACH (old IN CASE WHEN legacy IS NULL THEN [] ELSE [legacy] END | SET old.memory_key=$memory_key)
            MERGE (s:AgentMemorySession {memory_key: $memory_key})
            ON CREATE SET s.created_at = $now
            SET s.updated_at = $now, s.session_id = $memory_key, s.session_ref = $session_id, s.scope = $scope
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
                "memory_key": cls._memory_key(session_id),
                'legacy_key': _legacy_id(cls.scope(), session_id),
                "scope": cls.scope(),
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
        database = os.getenv('NEO4J_DATABASE', 'neo4j')
        if not cls.ensure_schema(database=database).get('ensured'):
            return
        cls._query(
            """
            UNWIND $rows AS row
            MERGE (f:AgentMemoryFact {fact_id: row.fact_id})
            ON CREATE SET f.created_at = $now
            SET f.kind = 'semantic_bridge_mapping',
                f.scope = row.scope,
                f.source = row.source,
                f.source_type = row.source_type,
                f.target = row.target,
                f.target_iri = row.target_iri,
                f.generic_match = row.generic_match,
                f.target_type = row.target_type,
                f.ontology_id = row.ontology_id,
                f.import_task_id = row.import_task_id,
                f.confidence = row.confidence,
                f.mapping_type = row.mapping_type,
                f.task_id = row.task_id,
                f.updated_at = $now
            RETURN count(f) AS stored
            """,
            {"rows": rows[:5000], "now": _now_iso()}, database=database,
        )

    @classmethod
    def recent_context(cls, session_id: str, limit: int = 6) -> Dict[str, Any]:
        """Return compact memory context for future prompt augmentation."""
        if not cls.enabled():
            return {"enabled": False, "messages": [], "facts": []}
        rows = cls._query(
            """
            MATCH (s:AgentMemorySession {scope: $scope})-[:HAS_MESSAGE]->(m:AgentMemoryMessage)
            WHERE s.memory_key IN [$memory_key, $legacy_key] AND coalesce(s.session_ref, s.session_id) = $session_id
            AND datetime(m.created_at) >= datetime() - duration({seconds: $max_age})
            RETURN m.role AS role, m.text AS text, m.created_at AS created_at
            ORDER BY m.created_at DESC
            LIMIT toInteger($limit)
            """,
            {
                "memory_key": cls._memory_key(session_id),
                'legacy_key': _legacy_id(cls.scope(), session_id),
                'session_id': session_id,
                "scope": cls.scope(),
                "limit": max(1, min(int(limit or 6), 20)),
                'max_age': max(1, int(os.getenv('AGENT_SESSION_MAX_SECONDS', '86400'))),
            },
        )
        return {"enabled": True, "messages": rows or [], "facts": []}

    @classmethod
    def semantic_bridge_facts(cls, ontology_id: str = "", limit: int = 1000) -> List[Dict[str, Any]]:
        """Return approved Semantic Bridge facts for mapping reuse."""
        if not cls.enabled():
            return []
        rows = cls._query(
            """
            MATCH (f:AgentMemoryFact {kind: 'semantic_bridge_mapping'})
            WHERE f.scope = $scope AND ($ontology_id = '' OR f.ontology_id = $ontology_id)
            WITH f ORDER BY f.updated_at DESC
            WITH f.source AS source, f.target AS target, f.target_iri AS target_iri, f.ontology_id AS ontology_id,
                 f.source_type AS source_type, f.target_type AS target_type, collect(f)[0] AS f
            RETURN f.source AS source,
                   f.source_type AS source_type,
                   f.target AS target,
                   f.target_type AS target_type,
                   f.ontology_id AS ontology_id,
                   f.confidence AS confidence,
                   f.mapping_type AS mapping_type,
                   f.target_iri AS target_iri,
                   f.generic_match AS generic_match,
                   f.updated_at AS updated_at
            ORDER BY f.updated_at DESC
            LIMIT toInteger($limit)
            """,
            {
                "ontology_id": str(ontology_id or "").strip(),
                "scope": cls.scope(),
                "limit": max(1, min(int(limit or 1000), 5000)),
            }, database=os.getenv('NEO4J_DATABASE', 'neo4j'),
        )
        return rows or []

    @classmethod
    def delete_session(cls, session_id: str) -> bool:
        """Delete one conversation and its traces inside the active scope."""
        if not cls.enabled():
            return False
        result = cls._query(
            """
            MATCH (s:AgentMemorySession {scope: $scope})
            WHERE s.memory_key IN [$memory_key, $legacy_key] AND coalesce(s.session_ref, s.session_id) = $session_id
            OPTIONAL MATCH (s)-[:HAS_MESSAGE|HAS_REASONING_TRACE]->(item)
            DETACH DELETE item, s
            RETURN count(*) AS deleted
            """,
            {"memory_key": cls._memory_key(session_id), "scope": cls.scope(),
             'legacy_key': _legacy_id(cls.scope(), session_id), 'session_id': session_id},
        )
        return result is not None

    @classmethod
    def prune_expired_sessions(cls, retention_days: Optional[int] = None) -> int:
        """Remove scoped conversation memory older than the configured retention."""
        if not cls.enabled():
            return 0
        configured = retention_days if retention_days is not None else os.getenv("AGENT_MEMORY_RETENTION_DAYS", "30")
        days = max(1, min(int(configured), 3650))
        rows = cls._query(
            """
            MATCH (s:AgentMemorySession {scope: $scope})
            WHERE datetime(s.updated_at) < datetime() - duration({days: $days})
            OPTIONAL MATCH (s)-[:HAS_MESSAGE|HAS_REASONING_TRACE]->(item)
            WITH s, collect(item) AS items
            FOREACH (item IN items | DETACH DELETE item)
            DETACH DELETE s
            RETURN count(*) AS deleted
            """,
            {"scope": cls.scope(), "days": days},
        )
        return int((rows or [{}])[0].get("deleted", 0)) if rows else 0

    @classmethod
    def _mapping_fact_row(cls, ontology_id: str, import_task_id: str, mapping: Dict[str, Any], task_id: str) -> Dict[str, Any]:
        source = str(mapping.get("source_term") or mapping.get("source_label") or mapping.get("import_row_key") or "").strip()
        target = str(mapping.get("ontology_term") or mapping.get("target_term") or mapping.get("target_ontology_iri") or "").strip()
        return {
            "fact_id": _stable_id("semantic_bridge", cls.scope(), ontology_id, import_task_id, source, target, mapping.get('target_ontology_iri'), mapping.get('source_type'), mapping.get("target_ontology_type")),
            "scope": cls.scope(),
            "source": source,
            "source_type": str(mapping.get("source_type") or "")[:80],
            "target": target,
            "target_iri": str(mapping.get('target_ontology_iri') or ''),
            "generic_match": bool(mapping.get('generic_match')),
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
        for key in ("visibleGraph", "visible_graph", "searchResults", "search_results"):
            section = context.get(key)
            if isinstance(section, dict):
                values = section.get("nodes")
                if isinstance(values, list):
                    candidates.extend(item for item in values if isinstance(item, dict))

        seen = set()
        touched = []
        for node in candidates:
            element_id = str(node.get("elementId") or node.get("element_id") or node.get("id") or "").strip()
            if not element_id or element_id in seen:
                continue
            seen.add(element_id)
            props = node.get("properties") if isinstance(node.get("properties"), dict) else {}
            touched.append({
                "element_id": element_id,
                "label": str(
                    node.get("label") or node.get("name") or node.get("type")
                    or props.get("label") or props.get("name") or props.get("type") or ""
                )[:300],
            })
        return touched
