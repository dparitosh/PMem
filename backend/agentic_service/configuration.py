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
    for key, default, minimum, maximum in (
        ('AGENT_SESSION_IDLE_SECONDS', '1800', 60, 86400),
        ('AGENT_SESSION_MAX_SECONDS', '86400', 60, 2592000),
        ('AGENTIC_RUN_TIMEOUT_SECONDS', '300', 1, 3600),
        ('DEPO_REGISTRY_STATEMENT_TIMEOUT_SECONDS', '30', 1, 300),
        ('LLM_REQUEST_TIMEOUT_SECONDS', '30', 1, 120),
        ('AGENT_MEMORY_RETENTION_DAYS', '30', 1, 3650),
    ):
        try:
            if not minimum <= int(os.getenv(key, default)) <= maximum:
                raise ValueError()
        except ValueError:
            errors.append(key)
    def require(key):
        value = os.getenv(key, '').strip()
        if not value or '<' in value:
            errors.append(key)
        return value
    def url(key, https=False):
        value = require(key)
        try:
            from backend.depo_platform.service_urls import service_url
            value = service_url(key, value)
            parsed = urlsplit(value)
            valid = (parsed.scheme in ({'https'} if https else {'http', 'https'}) and
                     parsed.hostname and not parsed.username and not parsed.password and
                     not parsed.query and not parsed.fragment)
        except (ValueError, RuntimeError):
            valid = False
        if not valid and key not in errors:
            errors.append(key)
    if os.getenv('AGENT_MEMORY_ENABLED', 'false').lower() == 'true':
        require('AGENT_MEMORY_SCOPE')
    if not (os.getenv('DEPO_DATABASE_URL') or os.getenv('DATABASE_URL')):
        errors.append('DEPO_DATABASE_URL')
    for key in ('NEO4J_URI', 'NEO4J_DATABASE'):
        require(key)
    neo4j_auth_mode = os.getenv('NEO4J_AUTH_MODE', 'token').lower()
    if neo4j_auth_mode not in {'token', 'none'}:
        errors.append('NEO4J_AUTH_MODE')
    if neo4j_auth_mode == 'token':
        for key in ('NEO4J_USER', 'NEO4J_PASS'):
            require(key)
    mode = os.getenv('AUTH_MODE', 'token').lower()
    if mode not in {'token', 'entra', 'disabled'}:
        errors.append('AUTH_MODE')
    for key in SERVICE_KEYS:
        url(key, https=mode == 'entra')
    if mode == 'token':
        for key in ('GRAPH_READ_TOKEN', 'AGENTIC_APPROVAL_TOKEN', 'ONTOLOGY_APPROVAL_TOKEN',
                    'DATA_PRODUCT_APPROVAL_TOKEN', 'DATA_JOB_EXECUTION_TOKEN', 'INGESTION_WRITE_TOKEN'):
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
    if os.getenv('ONTOLOGY_AGENT_LLM_ENABLED', 'false').lower() not in {'true', 'false'}:
        errors.append('ONTOLOGY_AGENT_LLM_ENABLED')
    try:
        ontology_limit = int(os.getenv('ONTOLOGY_AGENT_MAX_BYTES', str(25 * 1024 * 1024)))
        if ontology_limit <= 0:
            raise ValueError()
    except ValueError:
        errors.append('ONTOLOGY_AGENT_MAX_BYTES')
    if os.getenv('DT_AGENT_ENABLED', 'false').lower() == 'true':
        url('DT_AGENT_GATEWAY_URL', https=True)
        require('DT_AGENT_GATEWAY_TOKEN')
    if os.getenv('OSLC_REMOTE_ENABLED', 'false').lower() == 'true':
        url('OSLC_REMOTE_BASE_URL', https=mode == 'entra')
    for key, default in (('AGENTIC_TOOL_TIMEOUT_SECONDS', '30'),
                         ('COMPANION_RETRIEVAL_TIMEOUT_SECONDS', '15'),
                         ('OSLC_CLIENT_TIMEOUT_SECONDS', '20'),
                         ('AGENTIC_MAX_RESPONSE_BYTES', str(8 * 1024 * 1024)),
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
