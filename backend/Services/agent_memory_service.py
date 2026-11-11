"""PostgreSQL-backed agent memory.

Three memory layers are stored durably in PostgreSQL (the registry table
``depo_registry``), each in its own namespace:

- short-term: chat turns for a session (``agent_memory_short``)
- long-term: approved semantic bridge facts (``agent_memory_fact``)
- context: reasoning and tool traces that feed later recall (``agent_memory_trace``)

A session index (``agent_memory_session``) records each conversation's scope and
retention timestamps. Every key is scoped by the configured memory scope, so one
deployment's memory never leaks into another's. The service is best-effort for
callers: a failed write returns False or None and never breaks the chat path.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional

from backend.depo_platform import agent_memory_config

logger = logging.getLogger(__name__)

SESSION_NS = 'agent_memory_session'
SHORT_NS = 'agent_memory_short'
TRACE_NS = 'agent_memory_trace'
FACT_NS = 'agent_memory_fact'
PROBE_KEY = '__probe__'
FACT_READ_LIMIT = 1000
RECENT_ROW_LIMIT = 20


def _now_iso() -> str:
    # Fixed-width UTC timestamps sort lexically, which retention and recency rely on.
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%fZ')


_stamp_state = {'us': 0}
_stamp_lock = threading.Lock()


def _stamp() -> str:
    """Strictly increasing UTC microsecond stamp, so keys sort in write order even on coarse clocks."""
    with _stamp_lock:
        micro = int(time.time() * 1_000_000)
        if micro <= _stamp_state['us']:
            micro = _stamp_state['us'] + 1
        _stamp_state['us'] = micro
    moment = datetime.fromtimestamp(micro // 1_000_000, timezone.utc).replace(microsecond=micro % 1_000_000)
    return moment.strftime('%Y%m%dT%H%M%S%fZ')


def _safe_json(value: Any, limit: int = 12000) -> str:
    try:
        text = json.dumps(value or {}, default=str, ensure_ascii=False)
    except Exception:
        text = str(value or "")
    return text[:limit]


def _stable_id(*parts: Any) -> str:
    payload = json.dumps([str(part or '') for part in parts], ensure_ascii=True, separators=(',', ':'))
    return 'v2-' + hashlib.sha256(payload.encode('utf-8')).hexdigest()[:32]


def _store(namespace: str):
    from backend.mesh_store import PostgresRegistry
    return PostgresRegistry(namespace)


class AgentMemoryService:
    """Durable PostgreSQL memory for chat turns, reasoning traces, and bridge facts."""

    _health: Dict[str, Dict[str, Any]] = {}

    @classmethod
    def enabled(cls) -> bool:
        return agent_memory_config.enabled()

    @classmethod
    def scope(cls) -> str:
        """Return the mandatory isolation boundary used by every memory key."""
        return agent_memory_config.scope()

    @classmethod
    def _memory_key(cls, session_id: str) -> str:
        return _stable_id(cls.scope(), session_id)

    @classmethod
    def sdk_available(cls) -> bool:
        return False

    @classmethod
    def _record_health(cls, status: str, error_type: str = '') -> None:
        cls._health['postgresql'] = {'status': status, 'checked_at': _now_iso(), **({'error_type': error_type} if error_type else {})}

    @classmethod
    def status(cls, probe: bool = False) -> Dict[str, Any]:
        try:
            active = cls.enabled()
            scope = cls.scope() if active else ''
            agent_memory_config.query_timeout()
        except ValueError as exc:
            return {'enabled': False, 'status': 'configuration_invalid', 'invalid_setting': str(exc)}
        if active and probe:
            cls.ensure_schema()
        health = cls._health.get('postgresql', {})
        state = 'disabled' if not active else health.get('status', 'not_verified')
        return {
            'enabled': active,
            'status': state,
            'schema_status': 'not_applicable' if not active else health.get('status', 'not_verified'),
            'write_status': 'disabled' if not active else health.get('status', 'not_verified'),
            'mode': 'postgresql',
            'sdk_available': False,
            'scope': scope,
            'database': 'depo_registry',
            'memory_layers': ['short_term', 'long_term', 'context'],
            'best_effort': True,
        }

    @classmethod
    def ensure_schema(cls, database=None) -> Dict[str, Any]:
        """Verify PostgreSQL is reachable. Tables are the shared registry table, created by the platform migration."""
        if not cls.enabled():
            return {'enabled': False, 'ensured': False}
        try:
            _store(SESSION_NS).get(PROBE_KEY)
        except Exception as exc:
            cls._record_health('unavailable', type(exc).__name__)
            logger.warning('Agent memory PostgreSQL unavailable error_type=%s', type(exc).__name__)
            return {'enabled': True, 'ensured': False, 'error': 'Agent memory PostgreSQL is unavailable'}
        cls._record_health('available')
        return {'enabled': True, 'ensured': True}

    @classmethod
    def _touch_session(cls, session_id: str, memory_key: str, now: str) -> None:
        store = _store(SESSION_NS)
        existing = store.get(memory_key) or {}
        store.put(memory_key, {**existing, 'memory_key': memory_key, 'session_ref': session_id,
                               'scope': cls.scope(), 'created_at': existing.get('created_at', now),
                               'updated_at': now, 'legal_hold': bool(existing.get('legal_hold', False))})

    @classmethod
    def record_chat_turn(
        cls,
        *,
        session_id: str,
        user_message: str,
        assistant_response: str,
        graph_context: Optional[Dict[str, Any]] = None,
        generation: Optional[Dict[str, Any]] = None,
        status: str = 'completed',
    ) -> bool:
        """Persist one chat turn and its graph context as short-term memory."""
        if not cls.enabled():
            return False
        now = _now_iso()
        memory_key = cls._memory_key(session_id)
        turn_id = _stable_id(cls.scope(), session_id, user_message, assistant_response, now)
        from backend.agentic_service.context_scope import companion_scope
        selected_scope = {key: value for key, value in companion_scope(graph_context).items()
                          if isinstance(value, str) and 0 < len(value) <= 2000}
        row = {
            'turn_id': turn_id,
            'memory_key': memory_key,
            'session_ref': session_id,
            'scope': cls.scope(),
            'created_at': now,
            'status': status,
            'user_message': str(user_message or '')[:4000],
            'assistant_response': str(assistant_response or '')[:12000],
            'generation': generation or {},
            'context': selected_scope,
            'touched_nodes': cls._extract_touched_nodes(graph_context)[:100],
        }
        try:
            _store(SHORT_NS).put(f'{memory_key}/{_stamp()}/{turn_id}', row)
            cls._touch_session(session_id, memory_key, now)
            cls._record_health('available')
            return True
        except Exception as exc:
            cls._record_health('unavailable', type(exc).__name__)
            logger.warning('Agent memory turn not stored error_type=%s', type(exc).__name__)
            return False

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
        """Persist a reasoning or tool trace as context memory."""
        if not cls.enabled():
            return
        now = _now_iso()
        memory_key = cls._memory_key(session_id)
        trace_id = _stable_id(cls.scope(), session_id, task, tool_name, _safe_json(input_payload), now)
        try:
            _store(TRACE_NS).put(f'{memory_key}/{_stamp()}/{trace_id}', {
                'trace_id': trace_id,
                'memory_key': memory_key,
                'session_ref': session_id,
                'scope': cls.scope(),
                'task': str(task or '')[:500],
                'tool_name': str(tool_name or '')[:120],
                'input_payload': _safe_json(input_payload),
                'result_summary': _safe_json(result_summary),
                'success': bool(success),
                'created_at': now,
            })
            cls._touch_session(session_id, memory_key, now)
        except Exception as exc:
            cls._record_health('unavailable', type(exc).__name__)
            logger.warning('Agent memory trace not stored error_type=%s', type(exc).__name__)

    @classmethod
    def record_semantic_bridge_mappings(
        cls,
        *,
        ontology_id: str,
        import_task_id: str,
        mappings: Iterable[Dict[str, Any]],
        task_id: str = '',
    ) -> None:
        """Store approved semantic bridge mappings as long-term facts."""
        rows = [
            cls._mapping_fact_row(ontology_id, import_task_id, mapping, task_id)
            for mapping in mappings
            if mapping and (mapping.get('selected_for_apply') or mapping.get('approvedByUser'))
        ]
        rows = [row for row in rows if row.get('source') and row.get('target')]
        if not rows or not cls.enabled():
            return
        now = _now_iso()
        values = {}
        for row in rows[:5000]:
            values[f"{row['ontology_id']}/{row['fact_id']}"] = {
                **row, 'kind': 'semantic_bridge_mapping', 'memory_schema_version': 1,
                'lifecycle_status': 'approved', 'updated_at': now, 'created_at': now,
            }
        store = _store(FACT_NS)
        try:
            for start in range(0, len(values), 500):
                chunk = dict(list(values.items())[start:start + 500])
                store.put_many(chunk)
            cls._record_health('available')
        except Exception as exc:
            cls._record_health('unavailable', type(exc).__name__)
            logger.warning('Agent memory facts not stored error_type=%s', type(exc).__name__)

    @classmethod
    def recent_context(cls, session_id: str, limit: int = 6) -> Dict[str, Any]:
        """Return the newest messages of one session, newest first, within the retention window."""
        if not cls.enabled():
            return {'enabled': False, 'messages': [], 'facts': []}
        memory_key = cls._memory_key(session_id)
        max_age = max(1, int(os.getenv('AGENT_SESSION_MAX_SECONDS', '86400')))
        cutoff = (datetime.now(timezone.utc) - timedelta(seconds=max_age)).strftime('%Y-%m-%dT%H:%M:%S.%fZ')
        wanted = max(1, min(int(limit or 6), 20))
        try:
            turns = _store(SHORT_NS).prefix_latest(f'{memory_key}/', limit=RECENT_ROW_LIMIT)
        except Exception as exc:
            cls._record_health('unavailable', type(exc).__name__)
            return {'enabled': True, 'status': 'unavailable', 'best_effort': True, 'messages': [], 'facts': []}
        messages: List[Dict[str, Any]] = []
        for _, turn in turns:
            if not isinstance(turn, dict) or turn.get('scope') != cls.scope() or turn.get('created_at', '') < cutoff:
                continue
            # The user message precedes the assistant reply, so the reply is newer and comes first.
            messages.append({'role': 'assistant', 'text': turn.get('assistant_response', ''), 'created_at': turn.get('created_at')})
            messages.append({'role': 'user', 'text': turn.get('user_message', ''), 'created_at': turn.get('created_at')})
            if len(messages) >= wanted:
                break
        cls._record_health('available')
        return {'enabled': True, 'status': 'available', 'best_effort': True, 'messages': messages[:wanted], 'facts': []}

    @classmethod
    def semantic_bridge_facts(cls, ontology_id: str = '', limit: int = 1000) -> List[Dict[str, Any]]:
        """Return approved Semantic Bridge facts for one ontology, newest first, de-duplicated."""
        ontology_id = str(ontology_id or '').strip()
        # A failed ontology resolution must not fall back to all project facts.
        if not cls.enabled() or not ontology_id:
            return []
        now = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%fZ')
        try:
            items = _store(FACT_NS).prefix_items(f'{ontology_id}/', limit=FACT_READ_LIMIT)
        except Exception as exc:
            cls._record_health('unavailable', type(exc).__name__)
            return []
        best: Dict[tuple, Dict[str, Any]] = {}
        for fact in items.values():
            if not isinstance(fact, dict) or fact.get('kind') != 'semantic_bridge_mapping' or fact.get('scope') != cls.scope():
                continue
            if fact.get('lifecycle_status') != 'approved' or fact.get('superseded_by'):
                continue
            if fact.get('valid_from') and fact['valid_from'] > now:
                continue
            if fact.get('valid_until') and fact['valid_until'] <= now:
                continue
            identity = (fact.get('source'), fact.get('target'), fact.get('target_iri'), fact.get('ontology_id'))
            current = best.get(identity)
            if current is None or str(fact.get('updated_at', '')) > str(current.get('updated_at', '')):
                best[identity] = fact
        keys = ('source', 'source_type', 'target', 'target_type', 'ontology_id', 'confidence', 'mapping_type', 'target_iri',
                'generic_match', 'lifecycle_status', 'memory_schema_version', 'import_task_id', 'task_id', 'updated_at')
        rows = [{key: fact.get(key) for key in keys} for fact in best.values()]
        rows.sort(key=lambda row: str(row.get('updated_at') or ''), reverse=True)
        return rows[:max(1, min(int(limit or 1000), 5000))]

    @classmethod
    def delete_session(cls, session_id: str) -> bool:
        """Delete one conversation and its traces inside the active scope."""
        if not cls.enabled():
            return False
        memory_key = cls._memory_key(session_id)
        try:
            _store(SHORT_NS).delete_prefix(f'{memory_key}/')
            _store(TRACE_NS).delete_prefix(f'{memory_key}/')
            _store(SESSION_NS).delete_prefix(memory_key)
            cls._record_health('available')
            return True
        except Exception as exc:
            cls._record_health('unavailable', type(exc).__name__)
            return False

    @classmethod
    def prune_expired_sessions(cls, retention_days: Optional[int] = None) -> Optional[int]:
        """Remove conversation memory older than the retention period, except sessions on legal hold."""
        if not cls.enabled():
            return 0
        configured = retention_days if retention_days is not None else os.getenv('AGENT_MEMORY_RETENTION_DAYS', '30')
        days = max(1, min(int(configured), 3650))
        cutoff_time = datetime.now(timezone.utc) - timedelta(days=days)
        cutoff = cutoff_time.strftime('%Y-%m-%dT%H:%M:%S.%fZ')
        try:
            session_store = _store(SESSION_NS)
            short_store, trace_store = _store(SHORT_NS), _store(TRACE_NS)
            removed = 0
            # Sessions are retired as a whole: their turns and traces go with the session index entry.
            # Each pass is bounded; a legal hold keeps a session and everything under it.
            for _ in range(20):
                expired = session_store.keys_expired_before(scope=cls.scope(), field='updated_at', cutoff=cutoff, limit=200)
                if not expired:
                    break
                for key in expired:
                    short_store.delete_prefix(f'{key}/')
                    trace_store.delete_prefix(f'{key}/')
                    session_store.delete_prefix(key)
                    removed += 1
            cls._record_health('available')
            return removed
        except Exception as exc:
            cls._record_health('unavailable', type(exc).__name__)
            return None

    @classmethod
    def _mapping_fact_row(cls, ontology_id: str, import_task_id: str, mapping: Dict[str, Any], task_id: str) -> Dict[str, Any]:
        source = str(mapping.get('source_term') or mapping.get('source_label') or mapping.get('import_row_key') or '').strip()
        target = str(mapping.get('ontology_term') or mapping.get('target_term') or mapping.get('target_ontology_iri') or '').strip()
        return {
            'fact_id': _stable_id('semantic_bridge', cls.scope(), ontology_id, import_task_id, source, target, mapping.get('target_ontology_iri'), mapping.get('source_type'), mapping.get('target_ontology_type')),
            'scope': cls.scope(),
            'source': source,
            'source_type': str(mapping.get('source_type') or '')[:80],
            'target': target,
            'target_iri': str(mapping.get('target_ontology_iri') or ''),
            'generic_match': bool(mapping.get('generic_match')),
            'target_type': str(mapping.get('target_ontology_type') or '')[:80],
            'ontology_id': str(ontology_id or '')[:256],
            'import_task_id': str(import_task_id or '')[:256],
            'confidence': float(mapping.get('confidence') or 0.0),
            'mapping_type': str(mapping.get('mapping_type') or '')[:80],
            'task_id': str(task_id or '')[:256],
        }

    @classmethod
    def _extract_touched_nodes(cls, graph_context: Optional[Dict[str, Any]]) -> List[Dict[str, str]]:
        context = graph_context or {}
        candidates: List[Dict[str, Any]] = []
        for key in ('selectedNode', 'selected_node', 'rootNode', 'root_node'):
            node = context.get(key)
            if isinstance(node, dict):
                candidates.append(node)
        for key in ('nodes', 'visibleNodes', 'contextNodes'):
            values = context.get(key)
            if isinstance(values, list):
                candidates.extend(item for item in values if isinstance(item, dict))
        for key in ('visibleGraph', 'visible_graph', 'searchResults', 'search_results'):
            section = context.get(key)
            if isinstance(section, dict):
                values = section.get('nodes')
                if isinstance(values, list):
                    candidates.extend(item for item in values if isinstance(item, dict))

        seen = set()
        touched = []
        for node in candidates:
            element_id = str(node.get('elementId') or node.get('element_id') or node.get('id') or '').strip()
            if not element_id or element_id in seen:
                continue
            seen.add(element_id)
            props = node.get('properties') if isinstance(node.get('properties'), dict) else {}
            touched.append({
                'element_id': element_id,
                'label': str(
                    node.get('label') or node.get('name') or node.get('type')
                    or props.get('label') or props.get('name') or props.get('type') or ''
                )[:300],
            })
        return touched
