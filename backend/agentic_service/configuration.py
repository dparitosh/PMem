"""Secret-free validation for the agentic installation and readiness probe."""
import math
import os
from urllib.parse import urlsplit


SERVICE_KEYS = ('AGENTIC_SERVICE_URL', 'GRAPH_SERVICE_URL', 'ONTOLOGY_SERVICE_URL',
                'INGESTION_SERVICE_URL', 'OSLC_SERVICE_URL', 'QIF_SERVICE_URL',
                'DATA_CATALOG_URL', 'DATA_PRODUCT_SERVICE_URL', 'CEIM_SERVICE_URL',
                'DATA_PIPELINE_SERVICE_URL')


def configuration_status():
    errors = []
    def require(key):
        value = os.getenv(key, '').strip()
        if not value or '<' in value:
            errors.append(key)
        return value
    def url(key, https=False):
        value = require(key)
        try:
            parsed = urlsplit(value)
            valid = (parsed.scheme in ({'https'} if https else {'http', 'https'}) and
                     parsed.hostname and not parsed.username and not parsed.password and
                     not parsed.query and not parsed.fragment)
        except ValueError:
            valid = False
        if not valid and key not in errors:
            errors.append(key)
    if not (os.getenv('DEPO_DATABASE_URL') or os.getenv('DATABASE_URL')):
        errors.append('DEPO_DATABASE_URL')
    for key in ('NEO4J_URI', 'NEO4J_USER', 'NEO4J_PASS', 'NEO4J_DATABASE'):
        require(key)
    mode = os.getenv('AUTH_MODE', 'token').lower()
    if mode not in {'token', 'entra', 'disabled'}:
        errors.append('AUTH_MODE')
    for key in SERVICE_KEYS:
        url(key, https=mode == 'entra')
    if mode == 'token':
        for key in ('GRAPH_READ_TOKEN', 'AGENTIC_APPROVAL_TOKEN', 'ONTOLOGY_APPROVAL_TOKEN',
                    'DATA_PRODUCT_APPROVAL_TOKEN', 'DATA_JOB_EXECUTION_TOKEN'):
            require(key)
    # Bridge publication uses a private service credential in every auth mode.
    require('GRAPH_PUBLICATION_TOKEN')
    if mode == 'entra':
        require('DEPO_TRUSTED_GATEWAY_IPS')
    if mode == 'disabled' and os.getenv('DEPO_ALLOW_INSECURE_LOCAL_AUTH', '').lower() != 'true':
        errors.append('DEPO_ALLOW_INSECURE_LOCAL_AUTH')
    for flag in ('DT_AGENT_ENABLED', 'OSLC_REMOTE_ENABLED'):
        if os.getenv(flag, 'false').lower() not in {'true', 'false'}:
            errors.append(flag)
    if os.getenv('DT_AGENT_ENABLED', 'false').lower() == 'true':
        url('DT_AGENT_GATEWAY_URL', https=True)
        require('DT_AGENT_GATEWAY_TOKEN')
    if os.getenv('OSLC_REMOTE_ENABLED', 'false').lower() == 'true':
        url('OSLC_REMOTE_BASE_URL', https=mode == 'entra')
    for key, default in (('AGENTIC_TOOL_TIMEOUT_SECONDS', '30'),
                         ('COMPANION_RETRIEVAL_TIMEOUT_SECONDS', '15'),
                         ('OSLC_CLIENT_TIMEOUT_SECONDS', '20'),
                         ('AGENTIC_MAX_UPLOAD_BYTES', str(25 * 1024 * 1024))):
        try:
            value = float(os.getenv(key, default))
            if not math.isfinite(value) or value <= 0 or (key.endswith('_BYTES') and not value.is_integer()):
                raise ValueError()
        except ValueError:
            errors.append(key)
    return {'configuration': {'status': 'unavailable' if errors else 'ready', 'invalid_settings': sorted(set(errors))}}


if __name__ == '__main__':
    import json
    result = configuration_status()
    print(json.dumps(result))
    raise SystemExit(0 if result['configuration']['status'] == 'ready' else 1)
