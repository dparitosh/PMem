"""Read-only OSLC-first retrieval for agentic GraphRAG context."""
from __future__ import annotations
import os
import asyncio
import re
import json
from typing import Any
from urllib.parse import urlsplit
import httpx
from .response_limits import read_bounded_response
from backend.depo_platform.network import bounded_timeout_seconds


class OSLCGraphRAG:
    max_results = 20

    @staticmethod
    def _base() -> str:
        value = os.getenv('OSLC_REMOTE_BASE_URL', '').strip().rstrip('/')
        if not value:
            raise RuntimeError('OSLC_REMOTE_BASE_URL is not configured')
        parsed = urlsplit(value)
        if parsed.scheme not in {'http', 'https'} or not parsed.netloc or parsed.query or parsed.fragment:
            raise RuntimeError('OSLC_REMOTE_BASE_URL is invalid')
        return value

    async def retrieve(self, query: str, resource_type: str = 'resources', limit: int = 10) -> dict[str, Any]:
        query = ' '.join(str(query or '').split())
        if not query:
            raise ValueError('query is required')
        if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]*', resource_type):
            raise ValueError('resource_type is invalid')
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= self.max_results:
            raise ValueError('limit must be an integer between 1 and 20')
        base = self._base()
        headers = {'Accept': 'application/json'}
        token = os.getenv('OSLC_REMOTE_TOKEN', '').strip()
        if token:
            headers['Authorization'] = f'Bearer {token}'
        params = {'oslc.searchTerms': query, 'oslc.pageSize': limit}
        endpoint = f'{base}/oslc/query/{resource_type}'
        try:
            timeout = bounded_timeout_seconds('OSLC_CLIENT_TIMEOUT_SECONDS', default=20)
            async with asyncio.timeout(timeout), httpx.AsyncClient(timeout=timeout, follow_redirects=False, trust_env=False) as client:
                async with client.stream('GET', endpoint, params=params, headers=headers) as response:
                    response.raise_for_status()
                    payload = json.loads(await read_bounded_response(response))
            if not isinstance(payload, (dict, list)):
                raise ValueError('Invalid OSLC response')
        except (httpx.HTTPError, ValueError, TimeoutError) as exc:
            raise RuntimeError('OSLC retrieval is unavailable') from exc
        raw = payload.get('results') if isinstance(payload, dict) else payload
        raw = raw if isinstance(raw, list) else payload.get('members', []) if isinstance(payload, dict) else []
        if not isinstance(raw, list):
            raise RuntimeError('OSLC retrieval returned an invalid member collection')
        evidence = []
        for item in raw[:limit]:
            if not isinstance(item, dict):
                continue
            evidence.append({
                'resource_id': item.get('uri') or item.get('id') or item.get('identifier'),
                'title': item.get('title') or item.get('name') or item.get('label'),
                'ontology_id': item.get('ontology_id') or item.get('ontologyId'),
                'revision': item.get('revision') or item.get('version'),
                'resource_type': resource_type,
                'source': endpoint,
                'validation_status': item.get('validation_status') or item.get('validationStatus') or 'unreported',
                'links': item.get('outgoingLinks') or item.get('links') or [],
            })
        return {'status': 'grounded' if evidence else 'no_evidence', 'answerable': bool(evidence),
                'query': query, 'evidence': evidence, 'resource_ids': [e['resource_id'] for e in evidence if e['resource_id']],
                'ontology_context': sorted({str(e['ontology_id']) for e in evidence if e['ontology_id']}),
                'revisions': sorted({str(e['revision']) for e in evidence if e['revision']}),
                'validation': {'statuses': sorted({str(e['validation_status']) for e in evidence}), 'source': 'OSLC resources'},
                'retrieval': {'endpoint': endpoint, 'count': len(evidence), 'bounded': True}}


oslc_graph_rag = OSLCGraphRAG()
