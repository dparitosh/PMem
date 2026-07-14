"""Minimal file-backed OSLC TRS service."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from contextlib import contextmanager
import json
import os
from pathlib import Path
import threading
import time
import uuid
from typing import Any, Dict, List, Optional
from urllib.parse import quote, urlparse


@dataclass(frozen=True)
class TRSEvent:
    event_id: str
    order: int
    event_type: str
    resource_uri: str
    changed_at: str
    title: str
    metadata: Dict[str, Any]


class OSLCTRSService:
    _lock = threading.Lock()
    MAX_EVENTS = 5000
    LOCK_TIMEOUT_SECONDS = 10.0
    STALE_LOCK_SECONDS = 60.0

    @classmethod
    def is_enabled(cls) -> bool:
        return str(os.getenv('OSLC_TRS_ENABLED', os.getenv('OSLC_ENABLED', 'true'))).strip().lower() in {'true', '1', 'yes'}

    @classmethod
    def base_url(cls) -> str:
        configured = str(os.getenv('OSLC_BASE_URL', '')).strip().rstrip('/')
        if configured:
            return configured
        host = str(os.getenv('APP_HOST', '')).strip() or 'localhost'
        port = str(os.getenv('APP_PORT', os.getenv('BACKEND_PORT', '8000'))).strip() or '8000'
        scheme = str(os.getenv('APP_SCHEME', 'http')).strip() or 'http'
        return f'{scheme}://{host}:{port}'

    @classmethod
    def _storage_path(cls) -> Path:
        root = Path(__file__).resolve().parents[2]
        target = root / 'uploads' / 'oslc_trs' / 'change_log.json'
        target.parent.mkdir(parents=True, exist_ok=True)
        return target

    @classmethod
    def _load(cls) -> Dict[str, Any]:
        path = cls._storage_path()
        if not path.exists():
            return {'events': [], 'counter': 0, 'first_retained_order': 0}
        try:
            state = json.loads(path.read_text(encoding='utf-8'))
        except Exception as exc:
            raise RuntimeError(f'OSLC TRS changelog is unreadable: {path}: {exc}') from exc
        if not isinstance(state, dict) or not isinstance(state.get('events', []), list):
            raise RuntimeError(f'OSLC TRS changelog has an invalid structure: {path}')
        events = state.get('events') or []
        orders = [int(event.get('order') or 0) for event in events if isinstance(event, dict)]
        counter = int(state.get('counter') or 0)
        if orders and counter < max(orders):
            raise RuntimeError(f'OSLC TRS counter is behind its retained events: {path}')
        state['counter'] = counter
        state['first_retained_order'] = int(state.get('first_retained_order') or (min(orders) if orders else 0))
        return state

    @classmethod
    def _save(cls, payload: Dict[str, Any]) -> None:
        path = cls._storage_path()
        temp_path = path.with_name(f'.{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp')
        try:
            with temp_path.open('w', encoding='utf-8') as handle:
                json.dump(payload, handle, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_path, path)
        finally:
            if temp_path.exists():
                temp_path.unlink(missing_ok=True)

    @classmethod
    @contextmanager
    def _cross_process_lock(cls):
        lock_path = cls._storage_path().with_suffix('.lock')
        deadline = time.monotonic() + cls.LOCK_TIMEOUT_SECONDS
        descriptor = None
        while descriptor is None:
            try:
                descriptor = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(descriptor, f'{os.getpid()}\n'.encode('ascii', errors='ignore'))
            except FileExistsError:
                try:
                    if time.time() - lock_path.stat().st_mtime > cls.STALE_LOCK_SECONDS:
                        lock_path.unlink(missing_ok=True)
                        continue
                except FileNotFoundError:
                    continue
                if time.monotonic() >= deadline:
                    raise RuntimeError(f'Timed out acquiring OSLC TRS lock: {lock_path}')
                time.sleep(0.05)
        try:
            yield
        finally:
            if descriptor is not None:
                os.close(descriptor)
            lock_path.unlink(missing_ok=True)

    @classmethod
    def _normalize_resource_path(cls, resource_uri: str) -> str:
        raw = str(resource_uri or '').strip()
        if not raw:
            raise ValueError('OSLC TRS resource URI is required')
        parsed = urlparse(raw)
        path = parsed.path or raw
        query = f'?{parsed.query}' if parsed.query else ''
        if path.startswith('/api/v1/ontology/'):
            ontology_id = path.rsplit('/', 1)[-1]
            return f'/oslc/shapes/{quote(ontology_id, safe="")}'
        if path.startswith('/api/v1/import/status/'):
            task_id = path.rsplit('/', 1)[-1]
            where_value = quote(f'import_id="{task_id}"', safe='')
            return f'/oslc/query/resources?oslc.where={where_value}'
        if path == '/api/v1/admin/schema-stats':
            return '/oslc/trs/base'
        if not path.startswith('/oslc/') and path != '/oslc':
            raise ValueError(f'TRS events must reference an OSLC resource: {raw}')
        return f'{path}{query}'

    @classmethod
    def _external_resource_uri(cls, resource_uri: str) -> str:
        return f'{cls.base_url()}{cls._normalize_resource_path(resource_uri)}'

    @classmethod
    def ontology_resource_uri(cls, ontology_id: str) -> str:
        return f'{cls.base_url()}/oslc/shapes/{quote(str(ontology_id or "").strip(), safe="")}'

    @classmethod
    def import_resource_uri(cls, task_id: str) -> str:
        where_value = quote(f'import_id="{str(task_id or "").strip()}"', safe='')
        return f'{cls.base_url()}/oslc/query/resources?oslc.where={where_value}'

    @classmethod
    def base_resource_uri(cls) -> str:
        return f'{cls.base_url()}/oslc/trs/base'

    @classmethod
    def _external_event(cls, event: Dict[str, Any]) -> Dict[str, Any]:
        payload = dict(event)
        payload['resource_uri'] = cls._external_resource_uri(str(event.get('resource_uri') or ''))
        return payload

    @classmethod
    def publish_event(cls, resource_uri: str, event_type: str, *, title: str = '', metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if not cls.is_enabled():
            return {'status': 'disabled'}
        event_type_lookup = {value.lower(): value for value in ('Creation', 'Modification', 'Deletion')}
        normalized_event_type = event_type_lookup.get(str(event_type or '').strip().lower())
        if not normalized_event_type:
            raise ValueError(f'Unsupported OSLC TRS event type: {event_type}')
        resource_path = cls._normalize_resource_path(resource_uri)
        with cls._lock:
            with cls._cross_process_lock():
                state = cls._load()
                order = int(state.get('counter', 0)) + 1
                event = {
                    'event_id': str(uuid.uuid4()),
                    'order': order,
                    'event_type': normalized_event_type,
                    'resource_uri': resource_path,
                    'changed_at': datetime.now(timezone.utc).isoformat(),
                    'title': str(title or '').strip(),
                    'metadata': metadata or {},
                }
                events = list(state.get('events') or [])
                events.append(event)
                retained_events = events[-cls.MAX_EVENTS:]
                state['counter'] = order
                state['events'] = retained_events
                state['first_retained_order'] = int(retained_events[0].get('order') or order) if retained_events else 0
                cls._save(state)
                return cls._external_event(event)

    @classmethod
    def tracked_resource_set(cls) -> Dict[str, Any]:
        return {
            'uri': f'{cls.base_url()}/oslc/trs',
            'type': 'trs:TrackedResourceSet',
            'base': f'{cls.base_url()}/oslc/trs/base',
            'changeLog': f'{cls.base_url()}/oslc/trs/changelog',
            'domains': [
                {
                    'id': 'ap242',
                    'title': 'AP242 Product and Manufacturing Information',
                    'namespace': 'http://depo-onto.local/ap242#',
                },
                {
                    'id': 'oslc_am',
                    'title': 'OSLC Architecture Management',
                    'namespace': 'http://open-services.net/ns/am#',
                },
                {
                    'id': 'oslc_rm',
                    'title': 'OSLC Requirements Management',
                    'namespace': 'http://open-services.net/ns/rm#',
                },
            ],
        }

    @classmethod
    def base_resources(cls, limit: int = 200) -> Dict[str, Any]:
        state = cls._load()
        safe_limit = max(1, min(1000, int(limit or 200)))
        try:
            try:
                from backend.Services.graph_view_service import GraphViewService
                from backend.Services.oslc_service import OSLCService
            except ImportError:
                from Services.graph_view_service import GraphViewService
                from Services.oslc_service import OSLCService
            rows = GraphViewService._run(
                """
                MATCH (n)
                WHERE NOT (n:DatasheetChunk OR n:GraphChunk)
                RETURN elementId(n) AS element_id,
                       coalesce(n.name, n.title, n.code, n.label, n.id, elementId(n)) AS title,
                       labels(n) AS labels,
                       {
                         element_type: n.element_type,
                         entity_type: n.entity_type,
                         type: n.type,
                         semantic_role: n.semantic_role,
                         source_format: n.source_format,
                         archimate_type: n.archimate_type
                       } AS domain_properties
                ORDER BY elementId(n)
                LIMIT $limit
                """,
                {'limit': safe_limit + 1},
            )
        except Exception as exc:
            raise RuntimeError(f'Unable to build the OSLC TRS Base from the current graph: {exc}') from exc
        candidates: List[Dict[str, Any]] = []
        try:
            try:
                from backend.Services.ontology_upload_manager import OntologyUploadManager
            except ImportError:
                from Services.ontology_upload_manager import OntologyUploadManager
            listed = OntologyUploadManager.list_ontologies()
            for meta in listed.get('ontologies', []) if listed.get('status') == 'success' else []:
                ontology_id = str(meta.get('ontology_id') or '').strip()
                if ontology_id:
                    candidates.append({
                        'resource_uri': cls.ontology_resource_uri(ontology_id),
                        'title': meta.get('ontology_name') or meta.get('original_filename') or ontology_id,
                        'ontology_id': ontology_id,
                    })
        except Exception:
            # Graph resources still form a valid Base if the optional file registry
            # is unavailable; Neo4j-only ontologies remain represented as nodes.
            pass
        for row in rows:
            element_id = str(row.get('element_id') or '').strip()
            if not element_id:
                continue
            candidates.append({
                'resource_uri': f'{cls.base_url()}/oslc/resources/{quote(element_id, safe="")}',
                'title': row.get('title') or element_id,
                'element_id': element_id,
                'rdf_types': OSLCService.resource_domain_types(
                    row.get('labels') or [], row.get('domain_properties') or {}
                ),
            })
        for event in reversed(state.get('events') or []):
            if str(event.get('event_type') or '') == 'Deletion':
                continue
            try:
                event_uri = cls._external_resource_uri(str(event.get('resource_uri') or ''))
            except ValueError:
                continue
            if event_uri == cls.base_resource_uri():
                continue
            candidates.append({'resource_uri': event_uri, 'title': event.get('title') or event_uri})

        seen = set()
        unique_members = []
        for candidate in candidates:
            uri = candidate.get('resource_uri')
            if not uri or uri in seen:
                continue
            seen.add(uri)
            unique_members.append(candidate)
        truncated = len(rows) > safe_limit or len(unique_members) > safe_limit
        members = unique_members[:safe_limit]
        return {
            'uri': f'{cls.base_url()}/oslc/trs/base',
            'type': 'trs:Base',
            'members': members,
            'count': len(members),
            'cutoff_order': int(state.get('counter') or 0),
            'truncated': truncated,
        }

    @classmethod
    def change_log(cls, *, after: int = 0, limit: int = 200) -> Dict[str, Any]:
        state = cls._load()
        events = [event for event in (state.get('events') or []) if int(event.get('order') or 0) > int(after)]
        events = events[:max(1, min(1000, int(limit or 200)))]
        first_retained_order = int(state.get('first_retained_order') or (events[0].get('order') if events else 0) or 0)
        rebase_required = bool(first_retained_order and int(after) < first_retained_order - 1)
        external_events = [cls._external_event(event) for event in events]
        return {
            'uri': f'{cls.base_url()}/oslc/trs/changelog',
            'type': 'trs:ChangeLog',
            'events': external_events,
            'count': len(external_events),
            'next_after': external_events[-1]['order'] if external_events else after,
            'first_retained_order': first_retained_order,
            'rebase_required': rebase_required,
            'base': f'{cls.base_url()}/oslc/trs/base',
        }
