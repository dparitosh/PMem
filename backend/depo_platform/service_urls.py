"""Validated service URL lookup shared by cross-service clients."""
from __future__ import annotations

import os


def service_url(name: str, local_default: str) -> str:
    """Return an explicit service URL and reject hidden loopback in production."""
    value = os.getenv(name, '').strip()
    if value:
        return value.rstrip('/')
    environment = os.getenv('DEPO_ENV', os.getenv('ENVIRONMENT', 'development')).lower()
    if environment in {'prod', 'production'}:
        raise RuntimeError(f'{name} must be configured in production; refusing loopback default {local_default}')
    return local_default.rstrip('/')
