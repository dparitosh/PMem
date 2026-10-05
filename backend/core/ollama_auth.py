"""Server-only Ollama proxy authentication; never exposes subscription keys."""
import os
from urllib.parse import urlsplit

def ollama_headers(base_url, api_key=None, *, header_name=None):
    key = (api_key if api_key is not None else os.getenv('OLLAMA_API_KEY', '')).strip()
    if not key:
        return {}
    header = header_name or os.getenv('OLLAMA_API_KEY_HEADER', '').strip()
    if not header:
        host = (urlsplit(base_url).hostname or '').lower()
        header = 'Ocp-Apim-Subscription-Key' if host.endswith('.azure-api.net') else 'api-key'
    if header not in {'Ocp-Apim-Subscription-Key', 'api-key', 'Authorization'}:
        raise ValueError('OLLAMA_API_KEY_HEADER must be Ocp-Apim-Subscription-Key, api-key or Authorization')
    return {header: ('Bearer ' + key) if header == 'Authorization' else key}


def ollama_timeout():
    value = float(os.getenv('LLM_REQUEST_TIMEOUT_SECONDS', '30'))
    if not 1 <= value <= 120:
        raise ValueError('LLM_REQUEST_TIMEOUT_SECONDS must be between 1 and 120')
    return value
