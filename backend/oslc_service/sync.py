"""Auditable, on-demand OSLC pull synchronization without a task queue."""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .client import OSLCClient


QUERY_KEYS = {'oslc.where', 'oslc.select', 'oslc.orderBy', 'oslc.searchTerms', 'oslc.paging', 'oslc.pageSize', 'oslc.pageNum'}

def safe_parameters(parameters):
    return {key: value for key, value in parameters.items() if key in QUERY_KEYS}

def redact_legacy_snapshots(store):
    if not store.root.exists(): return
    for path in store.root.glob('*.json'):
        try:
            value = json.loads(path.read_text(encoding='utf-8'))
            clean = safe_parameters(value.get('parameters') or {})
            if clean != value.get('parameters'):
                value['parameters'] = clean
                temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
                temporary.write_text(json.dumps(value), encoding='utf-8')
                os.replace(temporary, path)
        except (OSError, ValueError, AttributeError):
            continue

class OSLCSyncStore:
    """Persist remote OSLC query snapshots for explicit review and ingestion.

    This service deliberately does not push to a remote provider or publish to
    the semantic graph. Both actions need a target-domain mapping and an
    explicit approval step, rather than an opaque scheduled mutation.
    """

    def __init__(self) -> None:
        self.root = Path(os.getenv("OSLC_SYNC_STORAGE", "data/oslc_service/syncs"))

    def _path(self, sync_id: str) -> Path:
        try:
            return self.root / f"{uuid.UUID(sync_id)}.json"
        except (AttributeError, ValueError) as exc:
            raise ValueError("sync_id must be a UUID") from exc

    def create(self, *, resource_type: str, parameters: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
        self.root.mkdir(parents=True, exist_ok=True)
        sync_id = str(uuid.uuid4())
        if not isinstance(payload, dict): raise ValueError('Remote query response must be an object')
        resources = next((payload[key] for key in ('members', 'value', 'resources', 'results') if key in payload), None)
        if resources is None: raise ValueError('Remote query response has no resource collection')
        if not isinstance(resources, list):
            raise ValueError('Remote resources must be an array')
        snapshot = {
            "sync_id": sync_id,
            "status": "staged",
            "direction": "pull",
            "resource_type": resource_type,
            "parameters": safe_parameters(parameters),
            "complete": not bool(payload.get("nextPage") or payload.get("oslc:nextPage") or int(payload.get("oslc:totalCount", len(resources))) > len(resources)),
            "next_page": payload.get("nextPage") or payload.get("oslc:nextPage"),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "resources": resources,
            "resource_count": len(resources),
            "next_action": "Map and approve this snapshot through the ingestion service before graph publication.",
        }
        if not snapshot['complete']:
            snapshot['status'] = 'staged_partial'
            snapshot['next_action'] = 'Retrieve remaining remote pages before mapping or approving this snapshot; it is incomplete.'
        path = self._path(sync_id)
        temporary = path.with_suffix('.tmp')
        temporary.write_text(json.dumps(snapshot, indent=2), encoding='utf-8')
        os.replace(temporary, path)
        return snapshot

    def list(self) -> list[dict[str, Any]]:
        if not self.root.exists():
            return []
        entries = []
        for path in self.root.glob("*.json"):
            try:
                snapshot = json.loads(path.read_text(encoding="utf-8"))
                snapshot['parameters'] = safe_parameters(snapshot.get('parameters') or {})
                entries.append({key: value for key, value in snapshot.items() if key != "resources"})
            except (OSError, json.JSONDecodeError):
                continue
        return sorted(entries, key=lambda item: str(item.get("created_at", "")), reverse=True)

    def get(self, sync_id: str) -> dict[str, Any] | None:
        try:
            path = self._path(sync_id)
        except ValueError:
            return None
        if not path.exists():
            return None
        snapshot = json.loads(path.read_text(encoding='utf-8'))
        snapshot['parameters'] = safe_parameters(snapshot.get('parameters') or {})
        return snapshot


class OSLCSynchronizer:
    def __init__(self, client: OSLCClient, store: OSLCSyncStore | None = None) -> None:
        self.client, self.store = client, store or OSLCSyncStore()

    def pull(self, resource_type: str, parameters: dict[str, Any]) -> dict[str, Any]:
        parameters = safe_parameters(parameters)
        payload = self.client.query(resource_type, parameters)
        from urllib.parse import urljoin
        current_url = self.client.base_url.rstrip('/') + '/oslc/query/' + resource_type
        max_pages = int(os.getenv('OSLC_SYNC_MAX_PAGES', '20'))
        max_resources = int(os.getenv('OSLC_SYNC_MAX_RESOURCES', '10000'))
        max_bytes = int(os.getenv('OSLC_SYNC_MAX_BYTES', str(32 * 1024 * 1024)))
        if not 1 <= max_pages <= 1000 or not 1 <= max_resources <= 100000 or max_bytes <= 0:
            raise ValueError('Invalid OSLC synchronization bounds')
        resources, visited, size = [], set(), 0
        for page in range(max_pages):
            collection = next((payload[key] for key in ('members', 'value', 'resources', 'results') if key in payload), None)
            if not isinstance(collection, list):
                raise ValueError('Remote resources must be an array')
            size += len(json.dumps(payload).encode('utf-8'))
            if size > max_bytes or len(resources) + len(collection) > max_resources:
                raise ValueError('OSLC synchronization exceeds configured resource or byte limit; no snapshot applied')
            resources.extend(collection)
            link = payload.get('nextPage') or payload.get('oslc:nextPage')
            if not link or page + 1 == max_pages:
                break
            if not isinstance(link, str) or link in visited:
                raise ValueError('Remote pagination is invalid or cyclic; no snapshot applied')
            visited.add(link)
            payload = self.client.next_page(link, current_url)
            current_url = urljoin(current_url, link)
        result = {'members': resources, 'nextPage': link,
                  'oslc:totalCount': payload.get('oslc:totalCount', len(resources))}
        return self.store.create(resource_type=resource_type, parameters=parameters, payload=result)
