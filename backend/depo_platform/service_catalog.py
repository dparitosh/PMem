"""Configuration-aware display catalog using the deployment manifest."""
import os
import re
from urllib.parse import urlsplit, urlunsplit

NAMES = {'schema-sets': 'QIF', 'ontology': 'ONTOLOGY', 'agentic': 'AGENTIC', 'graph': 'GRAPH',
         'ingestion': 'INGESTION', 'oslc': 'OSLC', 'catalog': 'CATALOG',
         'data-products': 'DATA_PRODUCT', 'ceim': 'CEIM', 'data-pipeline': 'DATA_PIPELINE'}


def service_origin(service):
    name = NAMES[service['id']]
    key = 'DATA_CATALOG_URL' if name == 'CATALOG' else name + '_SERVICE_URL'
    mode = os.getenv('DEPO_ROUTING_MODE', '').strip().lower()
    if mode == 'gateway':
        base = os.getenv('DEPO_API_GATEWAY_URL', '').rstrip('/')
        suffix = os.getenv('DEPO_GATEWAY_' + name + '_PATH') or service['apim_path']
        if not base or not re.fullmatch(r'[A-Za-z0-9_-]+(?:/[A-Za-z0-9_-]+)*', suffix) or suffix.endswith('api/v1'):
            raise ValueError('Invalid service gateway configuration')
        endpoint, source = base + '/' + suffix, 'DEPO_API_GATEWAY_URL; DEPO_GATEWAY_' + name + '_PATH'
    elif mode == 'local':
        host = os.getenv('DEPO_LOCAL_SERVICE_HOST') or os.getenv('DEPO_SERVICE_HOST') or '127.0.0.1'
        if not re.fullmatch(r'[A-Za-z0-9.-]+', host) or host in {'0.0.0.0', '*'}:
            raise ValueError('Configure a reachable DEPO_LOCAL_SERVICE_HOST')
        endpoint, source = f'http://{host}:{service["port"]}', 'DEPO_LOCAL_SERVICE_HOST; infra/deployment/services.json'
    elif mode:
        raise ValueError('Invalid DEPO_ROUTING_MODE')
    else:
        endpoint, source = os.getenv(key, '').rstrip('/'), key
        if not endpoint:
            return '', source
        endpoint = endpoint.removesuffix('/api/v1')
    url = urlsplit(endpoint)
    url.port
    if url.scheme not in {'http', 'https'} or not url.hostname or url.username or url.password or url.query or url.fragment or any(c.isspace() or c in '<>\\' for c in endpoint):
        raise ValueError('Invalid service endpoint configuration')
    return urlunsplit(url), source


def service_rows(manifest):
    rows = []
    for service in manifest['services']:
        endpoint, source = service_origin(service)
        rows.append({'id': service['id'], 'name': service.get('display_name') or service['id'],
                     'type': 'standalone_api', 'status': 'configured; health unverified' if endpoint else 'not configured',
                     'owner': 'Digital Engineering', 'endpoint': endpoint,
                     'health_endpoint': endpoint + '/readyz' if endpoint else '', 'config_source': source,
                     'route_count': 0, 'frontend_mapped_count': 0, 'port': service['port']})
    return rows
