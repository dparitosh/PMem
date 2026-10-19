"""Namespace-derived ontology prefixes; source identifiers are never rewritten."""
import re
from urllib.parse import urlsplit


def ontology_prefix(namespace: str, fallback: str = 'ontology') -> str:
    value = str(namespace or '').strip().rstrip('#/')
    if not value:
        return fallback
    parsed = urlsplit(value)
    local = parsed.fragment or parsed.path.rstrip('/').rsplit('/', 1)[-1] or parsed.hostname or ''
    if parsed.scheme == 'urn':
        local = local.rsplit(':', 1)[-1]
    token = re.sub(r'[^a-z0-9_]+', '_', local.lower()).strip('_')
    if token and not token[0].isalpha():
        token = 'ns_' + token
    return token[:50] or fallback
