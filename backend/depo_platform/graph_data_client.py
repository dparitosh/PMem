"""Read-only data service adapter for graph-backed ontology mapping terms."""
import json

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
        with httpx.Client(timeout=bounded_timeout_seconds('GRAPH_QUERY_TIMEOUT_SECONDS', default=30, maximum=300),
                          trust_env=False, follow_redirects=False) as client:
            with client.stream('GET', endpoint, params={'scope': scope}, headers=headers) as response:
                response.raise_for_status()
                content = bytearray()
                for chunk in response.iter_bytes():
                    content.extend(chunk)
                    if len(content) > 16 * 1024 * 1024:
                        raise RuntimeError('Graph mapping response exceeds the permitted size.')
        payload = json.loads(content)
        terms = payload.get('terms') if isinstance(payload, dict) else None
        if not isinstance(terms, list) or len(terms) > 10000 or any(
            not isinstance(term, dict) or term.get('kind') not in {'Class', 'ObjectProperty', 'DatatypeProperty', 'AnnotationProperty'}
            or not isinstance(term.get('element_id'), str) or not term['element_id']
            or not isinstance(term.get('name'), str) or not term['name'] for term in terms):
            raise RuntimeError('Graph data service returned invalid mapping terms.')
        return terms


graph_data_client = GraphDataClient()
