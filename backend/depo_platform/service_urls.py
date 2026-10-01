"""Validated service URL lookup shared by cross-service clients."""
from __future__ import annotations
import os
from urllib.parse import urlsplit, unquote

def service_url(name: str, local_default: str) -> str:
    value = os.getenv(name, '').strip()
    if not value:
        production = any(os.getenv(key, '').strip().lower() in {'prod', 'production'}
                         for key in ('DEPO_ENV', 'ENVIRONMENT', 'APP_ENV', 'DEPLOYMENT_ENV'))
        if production or os.getenv('DEPO_ROUTING_MODE', '').strip().lower() == 'gateway':
            raise RuntimeError(f'{name} must be configured for production or gateway routing')
        value = local_default
    try:
        parsed = urlsplit(value)
        parsed.port
        path = unquote(parsed.path)
        valid = (parsed.scheme in {'http', 'https'} and parsed.hostname
                 and not parsed.username and not parsed.password
                 and not parsed.query and not parsed.fragment
                 and not any(c.isspace() for c in value)
                 and not any(c in value for c in '<>\\')
                 and not any(part in {'.', '..'} for part in path.split('/')))
    except ValueError:
        valid = False
    if not valid:
        raise RuntimeError(f'{name} must be an HTTP/HTTPS service URL without credentials, placeholders or query strings')
    return value.rstrip('/')
