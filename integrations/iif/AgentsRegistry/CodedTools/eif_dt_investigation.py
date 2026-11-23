"""Read an operator-selected business investigation through the NEXUS Graph API."""
import json
import os
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, build_opener

from AgentsRegistry.CodedTools.eif_dt_graph import NoRedirect


def eif_dt_read_selected_investigation():
    path = Path(os.environ.get('NEXUS_INVESTIGATION_INTENT_FILE', ''))
    if not path.is_absolute():
        raise ValueError('Configure an absolute investigation intent file')
    with path.open('rb') as stream:
        raw = stream.read(16385)
    if len(raw) > 16384:
        raise ValueError('Investigation intent exceeds 16 KiB')
    intent = json.loads(raw)
    if not isinstance(intent, dict) or set(intent) != {'ontology_id', 'node_id'}:
        raise ValueError('Select exactly one ontology and investigation node')
    for key, limit in (('ontology_id', 128), ('node_id', 256)):
        value = intent[key]
        if not isinstance(value, str) or not value.strip() or len(value) > limit:
            raise ValueError(f'Invalid {key}')

    base = os.getenv('NEXUS_GRAPH_SERVICE_URL', 'http://127.0.0.1:8013/api/v1').rstrip('/')
    url = urlsplit(base)
    if (url.username or url.password or url.query or url.fragment
            or not url.hostname or url.path != '/api/v1'):
        raise ValueError('Configure the Graph service /api/v1 base URL')
    if url.scheme != 'https' and (url.scheme != 'http' or url.hostname not in {'localhost', '127.0.0.1', '::1'}):
        raise ValueError('Remote Graph service requires HTTPS')
    token = os.getenv('NEXUS_GRAPH_READ_TOKEN', '').strip()
    if not token:
        raise ValueError('Configure the scoped Graph read credential in IIF')
    query = urlencode({**intent, 'depth': 2, 'limit': 60})
    request = Request(f'{base}/graph/business-context?{query}', headers={'Authorization': f'Bearer {token}'})
    try:
        with build_opener(NoRedirect).open(request, timeout=25) as response:
            raw = response.read(262145)
    except HTTPError as exc:
        raise RuntimeError(f'Investigation read rejected (HTTP {exc.code})') from None
    except (URLError, TimeoutError):
        raise RuntimeError('Graph service unavailable') from None
    if len(raw) > 262144:
        raise ValueError('Investigation evidence exceeds 256 KiB')
    result = json.loads(raw)
    if (not isinstance(result, dict) or result.get('root_node_id') != intent['node_id']
            or not isinstance(result.get('view'), dict)
            or result['view'].get('ontology_id') != intent['ontology_id']):
        raise ValueError('Investigation response scope mismatch')
    nodes, edges = result.get('nodes'), result.get('relationships')
    if not isinstance(nodes, list) or not isinstance(edges, list):
        raise ValueError('Invalid investigation evidence')
    ids = set()
    for node in nodes:
        props = node.get('properties') if isinstance(node, dict) else None
        if (not isinstance(props, dict) or not isinstance(node.get('elementId'), str)
                or intent['ontology_id'] not in (props.get('ontology_id'), props.get('source_ontology'))
                or node['elementId'] in ids):
            raise ValueError('Invalid or out-of-scope investigation node')
        ids.add(node['elementId'])
    if intent['node_id'] not in ids or any(
        not isinstance(edge, dict) or not isinstance(edge.get('elementId'), str)
        or edge.get('start') not in ids or edge.get('end') not in ids for edge in edges
    ):
        raise ValueError('Invalid investigation relationship evidence')
    return {'controller': 'IIF', 'selection': intent, 'evidence': result, 'advisory_only': True}
