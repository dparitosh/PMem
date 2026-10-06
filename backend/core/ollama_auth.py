"""Server-only Ollama proxy authentication; never exposes subscription keys."""
import os
from urllib.parse import urlsplit, urlunsplit


def ollama_base_url(value=None):
    """Accept an API root or native operation URL; retain legacy configuration."""
    def normalize(raw):
        url = urlsplit(raw.strip())
        if url.scheme not in {'http', 'https'} or not url.hostname or url.username or url.password or url.query or url.fragment:
            raise ValueError('Ollama API URL must be HTTP(S) without credentials, query or fragment')
        path = url.path.rstrip('/')
        for suffix in ('/api/chat', '/api/generate', '/api/tags', '/api/embed', '/api/embeddings', '/chat'):
            if path.endswith(suffix):
                path = path[:-len(suffix)]
                break
        return urlunsplit((url.scheme, url.netloc, path, '', '')).rstrip('/')
    if value is not None:
        return normalize(value)
    api = os.getenv('OLLAMA_API_URL', '').strip()
    legacy = os.getenv('OLLAMA_BASE_URL', '').strip()
    if api and legacy and normalize(api) != normalize(legacy):
        raise ValueError('Conflicting OLLAMA_API_URL and OLLAMA_BASE_URL; keep one or use the same API root')
    return normalize(api or legacy or 'http://127.0.0.1:11434')

def ollama_headers(base_url, api_key=None, *, header_name=None):
    key = (api_key if api_key is not None else os.getenv('OLLAMA_API_KEY', '')).strip()
    if not key:
        return {}
    header = header_name or os.getenv('OLLAMA_API_KEY_HEADER', '').strip()
    if not header:
        header = 'api-key'
    if header not in {'Ocp-Apim-Subscription-Key', 'api-key', 'Authorization'}:
        raise ValueError('OLLAMA_API_KEY_HEADER must be Ocp-Apim-Subscription-Key, api-key or Authorization')
    return {header: ('Bearer ' + key) if header == 'Authorization' else key}


def ollama_timeout():
    value = float(os.getenv('LLM_REQUEST_TIMEOUT_SECONDS', '30'))
    if not 1 <= value <= 120:
        raise ValueError('LLM_REQUEST_TIMEOUT_SECONDS must be between 1 and 120')
    return value


def ollama_generation_route(value=None):
    """Keep an explicitly configured native generation operation."""
    configured = value if value is not None else (os.getenv('OLLAMA_API_URL', '').strip() or os.getenv('OLLAMA_BASE_URL', '').strip())
    base = ollama_base_url(configured) if value is not None else ollama_base_url()
    configured = configured.strip().rstrip('/')
    operation = 'generate' if urlsplit(configured).path.endswith('/api/generate') else 'chat'
    return base + '/api/' + operation, operation


def ollama_tool_chat_root():
    """Tool calling requires a chat route, independently of text generation."""
    explicit = os.getenv('OLLAMA_CHAT_API_URL', '').strip()
    if explicit:
        endpoint, operation = ollama_generation_route(explicit)
        if operation != 'chat':
            raise ValueError('OLLAMA_CHAT_API_URL must select an API root or /api/chat, not /api/generate')
        return ollama_base_url(explicit)
    endpoint, operation = ollama_generation_route()
    if operation == 'generate':
        raise ValueError('Tool calling requires a native /api/chat route. Configure OLLAMA_CHAT_API_URL separately for a generate-only endpoint.')
    return ollama_base_url()
