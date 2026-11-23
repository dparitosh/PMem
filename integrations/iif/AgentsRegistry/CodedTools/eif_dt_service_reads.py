"""Function adapters for existing PMem catalog and CEIM read APIs."""
import json
import os
import re
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlsplit
from urllib.request import Request, build_opener

from AgentsRegistry.CodedTools.eif_dt_graph import NoRedirect


def _read(service, port, path, parameters=None):
    base = os.getenv(f'NEXUS_{service}_SERVICE_URL', f'http://127.0.0.1:{port}/api/v1').rstrip('/')
    url = urlsplit(base)
    if (not url.hostname or url.username or url.password or url.query
            or url.fragment or url.path != '/api/v1'):
        raise ValueError('Configure the service /api/v1 base URL')
    if url.scheme != 'https' and (url.scheme != 'http' or url.hostname not in {'127.0.0.1', 'localhost', '::1'}):
        raise ValueError('Remote service requires HTTPS')
    token = os.getenv(f'NEXUS_{service}_READ_TOKEN', '').strip()
    if not token:
        raise ValueError(f'Configure the scoped {service} read credential in IIF_DT')
    query = '?' + urlencode(parameters) if parameters else ''
    request = Request(base + path + query, headers={'Authorization': f'Bearer {token}', 'Accept': 'application/json'})
    try:
        with build_opener(NoRedirect).open(request, timeout=25) as response:
            raw = response.read(262145)
    except HTTPError as exc:
        raise RuntimeError(f'{service} read rejected (HTTP {exc.code})') from None
    except (URLError, TimeoutError):
        raise RuntimeError(f'{service} service unavailable') from None
    if len(raw) > 262144:
        raise ValueError('Service output exceeds 256 KiB')
    result = json.loads(raw)
    if not isinstance(result, dict):
        raise ValueError('Expected a service JSON object')
    return result


def eif_dt_list_catalog_products(limit: int = 25) -> dict:
    """List a bounded page of governed catalog product versions."""
    if type(limit) is not int or not 1 <= limit <= 50:
        raise ValueError('Select a limit from 1 to 50')
    return _read('CATALOG', 8016, '/catalog/products', {'limit': limit})


def eif_dt_read_catalog_product(product_id: str) -> dict:
    """Read the retained versions for one catalog product ID."""
    if not isinstance(product_id, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,127}', product_id):
        raise ValueError('Select a catalog product ID')
    result = _read('CATALOG', 8016, '/catalog/products/' + quote(product_id, safe=''))
    if result.get('product_id') != product_id:
        raise ValueError('Catalog response changed the selected product')
    return result


def eif_dt_read_ceim_contract() -> dict:
    """Read the shared engineering information contract."""
    return _read('CEIM', 8018, '/ceim/contract')
