"""Read-only data service adapter for graph-backed ontology mapping terms."""
import json
import time

from .network import bounded_timeout_seconds, service_bearer_headers
from .service_urls import service_url


class GraphDataClient:
    def mapping_terms(self, scope):
        if not isinstance(scope, str) or not scope.strip() or len(scope) > 256:
            raise ValueError('Select a valid ontology scope.')
        import httpx
        base = service_url('GRAPH_SERVICE_URL', 'http://127.0.0.1:8013/api/v1')
        endpoint = base + ('/graph/mapping-terms' if base.endswith('/api/v1') else '/api/v1/graph/mapping-terms')
        # This is a private peer read, including when browser auth uses Entra.
        # The Graph service verifies this server-owned credential independently.
        headers = service_bearer_headers('GRAPH_PUBLICATION_TOKEN', service_name='Graph data service', endpoint=endpoint)
        from .peer_http import peer_response
        terms=[];seen=set();offset=0;revision=None;size=0
        budget=bounded_timeout_seconds('GRAPH_QUERY_TIMEOUT_SECONDS', default=30, maximum=300)
        deadline=time.monotonic()+budget
        while True:
            remaining=deadline-time.monotonic()
            if remaining<=0:raise TimeoutError('Complete mapping lookup exceeded its deadline; no partial evidence was accepted')
            response = peer_response('GET', endpoint, params={'scope':scope,'offset':offset,'limit':5000}, headers=headers,
                                     budget=remaining,
                                     response_limit=16 * 1024 * 1024)
            response.raise_for_status()
            content=response.content;size+=len(content)
            if size>64*1024*1024:raise RuntimeError('Complete mapping lookup exceeds the 64 MiB evidence budget')
            payload=json.loads(content)
            page=payload.get('terms') if isinstance(payload,dict) else None
            if not isinstance(page,list) or len(page)>10000 or any(
            not isinstance(term, dict) or term.get('kind') not in {'Class', 'ObjectProperty', 'DatatypeProperty', 'AnnotationProperty'}
            or not isinstance(term.get('element_id'), str) or not term['element_id']
            or not isinstance(term.get('name'), str) or not term['name'] for term in page):
                raise RuntimeError('Graph data service returned invalid mapping terms.')
            if 'offset' not in payload:
                if offset:raise RuntimeError('Mapping peer does not support complete paginated reads; deploy the full release')
                return page # Complete legacy single response; older peers reject >10000.
            if payload.get('scope')!=scope or type(payload.get('offset')) is not int or payload.get('offset')!=offset or len(page)>5000:
                raise RuntimeError('Mapping page changed selected scope or offset')
            if offset and payload.get('revision')!=revision:raise RuntimeError('Ontology projection changed during mapping lookup; retry a new preview')
            revision=payload.get('revision')
            for term in page:
                key=(term['element_id'],term['kind'])
                if key in seen:raise RuntimeError('Mapping pages repeated a target; no partial lookup was accepted')
                seen.add(key)
            terms.extend(page)
            if len(terms)>100000:raise RuntimeError('Complete mapping lookup exceeds 100000 terms; split the ontology scope')
            following=payload.get('next_offset')
            if following is None:break
            if not isinstance(revision,str) or len(revision)!=64 or type(following) is not int or following!=offset+5000 or len(page)!=5000:
                raise RuntimeError('Mapping continuation lacks a complete version-bound page; republish legacy ontology data')
            offset=following
        return terms


graph_data_client = GraphDataClient()
