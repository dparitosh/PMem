"""Readable reference labels without changing canonical vocabulary identities."""
import re


def readable_term(iri):
    local = str(iri).rstrip('/').rsplit('#', 1)[-1].rsplit('/', 1)[-1].rsplit(':', 1)[-1]
    return re.sub(r'(?<=[a-z0-9])(?=[A-Z])', ' ', local.replace('_', ' ')).strip()[:250]
