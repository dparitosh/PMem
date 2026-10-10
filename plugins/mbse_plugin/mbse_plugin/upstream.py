"""Browser-safe upstream configuration and durable-run contract checks."""
import os
from urllib.parse import urlsplit


def configuration():
    base = os.getenv('DEPO_INGESTION_URL', '').strip().rstrip('/')
    try:
        parsed = urlsplit(base)
        valid = (parsed.scheme in {'http', 'https'} and parsed.hostname and
                 not (parsed.username or parsed.password or parsed.query or parsed.fragment) and
                 parsed.path.endswith('/api/v1') and (parsed.port is None or parsed.port > 0))
    except ValueError:
        valid = False
    if not valid:
        raise ValueError('DEPO_INGESTION_URL must be an HTTP(S) API URL ending in /api/v1')
    token = os.getenv('DEPO_INGESTION_TOKEN', '').strip()
    if not token:
        raise ValueError('Configure DEPO_INGESTION_TOKEN using the central DATA_JOB_EXECUTION_TOKEN')
    headers = {'Authorization': 'Bearer ' + token}
    key = os.getenv('DEPO_APIM_SUBSCRIPTION_KEY', '').strip()
    if key:
        headers['Ocp-Apim-Subscription-Key'] = key
    return base, headers


def require_durable_run(result):
    if not isinstance(result, dict):
        raise ValueError('Invalid ingestion response')
    manifest = result.get('run_manifest')
    if not isinstance(manifest, dict) or not isinstance(manifest.get('run_id'), str) or not manifest['run_id'].strip():
        raise ValueError('Ingestion response is missing a durable run ID')
    return result
