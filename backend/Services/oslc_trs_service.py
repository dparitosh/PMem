"""Minimal file-backed OSLC TRS service."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import threading
import uuid
from typing import Any, Dict, List, Optional


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

    @classmethod
    def is_enabled(cls) -> bool:
        return str(os.getenv('OSLC_TRS_ENABLED', os.getenv('OSLC_ENABLED', 'true'))).strip().lower() in {'true', '1', 'yes'}

    @classmethod
    def base_url(cls) -> str:
        return str(os.getenv('OSLC_BASE_URL', 'http://localhost:8000')).strip().rstrip('/') or 'http://localhost:8000'

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
            return {'events': [], 'counter': 0}
        try:
            return json.loads(path.read_text(encoding='utf-8'))
        except Exception:
            return {'events': [], 'counter': 0}

    @classmethod
    def _save(cls, payload: Dict[str, Any]) -> None:
        cls._storage_path().write_text(json.dumps(payload, indent=2), encoding='utf-8')

    @classmethod
    def publish_event(cls, resource_uri: str, event_type: str, *, title: str = '', metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if not cls.is_enabled():
            return {'status': 'disabled'}
        with cls._lock:
            state = cls._load()
            order = int(state.get('counter', 0)) + 1
            event = {
                'event_id': str(uuid.uuid4()),
                'order': order,
                'event_type': str(event_type or 'Modification'),
                'resource_uri': str(resource_uri or '').strip(),
                'changed_at': datetime.now(timezone.utc).isoformat(),
                'title': str(title or '').strip(),
                'metadata': metadata or {},
            }
            state['counter'] = order
            events = list(state.get('events') or [])
            events.append(event)
            state['events'] = events[-5000:]
            cls._save(state)
            return event

    @classmethod
    def tracked_resource_set(cls) -> Dict[str, Any]:
        return {
            'uri': f'{cls.base_url()}/oslc/trs',
            'type': 'trs:TrackedResourceSet',
            'base': f'{cls.base_url()}/oslc/trs/base',
            'changeLog': f'{cls.base_url()}/oslc/trs/changelog',
        }

    @classmethod
    def base_resources(cls, limit: int = 200) -> Dict[str, Any]:
        state = cls._load()
        seen = set()
        members: List[Dict[str, Any]] = []
        for event in reversed(state.get('events') or []):
            uri = str(event.get('resource_uri') or '').strip()
            if not uri or uri in seen:
                continue
            seen.add(uri)
            members.append({
                'resource_uri': uri,
                'title': event.get('title') or uri,
                'last_event_type': event.get('event_type') or 'Modification',
                'last_changed_at': event.get('changed_at'),
            })
            if len(members) >= limit:
                break
        members.reverse()
        return {
            'uri': f'{cls.base_url()}/oslc/trs/base',
            'type': 'trs:Base',
            'members': members,
            'count': len(members),
        }

    @classmethod
    def change_log(cls, *, after: int = 0, limit: int = 200) -> Dict[str, Any]:
        state = cls._load()
        events = [event for event in (state.get('events') or []) if int(event.get('order') or 0) > int(after)]
        events = events[:max(1, min(1000, int(limit or 200)))]
        return {
            'uri': f'{cls.base_url()}/oslc/trs/changelog',
            'type': 'trs:ChangeLog',
            'events': events,
            'count': len(events),
            'next_after': events[-1]['order'] if events else after,
        }
