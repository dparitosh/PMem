"""Emit only public browser routing overrides for the Linux frontend build."""
import json
import os
import re
from urllib.parse import urlsplit


def browser_routing(values):
    mode = values.get('DEPO_ROUTING_MODE', '').strip().lower()
    if not mode:
        return {}
    if mode not in {'local', 'gateway'}:
        raise ValueError('DEPO_ROUTING_MODE must be local or gateway')
    base = values.get('DEPO_API_GATEWAY_URL', '').rstrip('/')
    host = values.get('DEPO_LOCAL_SERVICE_HOST') or values.get('DEPO_SERVICE_HOST') or '127.0.0.1'
    if mode == 'local':
        if values.get('AUTH_MODE') != 'token' or not re.fullmatch(r'[A-Za-z0-9.-]+', host) or host == '0.0.0.0':
            raise ValueError('Local browser routing requires token authentication and a reachable hostname or IPv4 address')
    else:
        uri = urlsplit(base)
        if uri.scheme not in {'http', 'https'} or not uri.hostname or uri.username or uri.password or uri.query or uri.fragment or re.search(r'[<>\s\\]', base):
            raise ValueError('Invalid DEPO_API_GATEWAY_URL')
        if values.get('AUTH_MODE') == 'entra' and uri.scheme != 'https':
            raise ValueError('Entra gateway routing requires HTTPS')
    result = {'VITE_API_GATEWAY_URL': base if mode == 'gateway' else '', 'VITE_BACKEND_URL': ''}
    names = ['QIF', 'ONTOLOGY', 'AGENTIC', 'GRAPH', 'INGESTION', 'OSLC', 'CATALOG', 'DATA_PRODUCT', 'CEIM', 'DATA_PIPELINE']
    paths = ['qif', 'ontology', 'agentic', 'graph', 'ingestion', 'oslc', 'catalog', 'data-products', 'ceim', 'data-pipeline']
    for i, (name, path) in enumerate(zip(names, paths)):
        path = values.get(f'DEPO_GATEWAY_{name}_PATH') or path
        if mode == 'gateway' and (not re.fullmatch(r'[A-Za-z0-9_-]+(?:/[A-Za-z0-9_-]+)*', path) or re.search(r'(^|/)api/v1$', path)):
            raise ValueError(f'Invalid gateway path for {name}')
        result[f'VITE_{name}_SERVICE_URL'] = f'http://{host}:{8010+i}' if mode == 'local' else f'{base}/{path}'
    return result


if __name__ == '__main__':
    print(json.dumps(browser_routing(os.environ)))
