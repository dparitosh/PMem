"""Shared Companion scope projection; selection never grants authorization."""

SCOPE_FIELDS = ('ontology', 'ontology_prefix', 'page')


def companion_scope(context):
    context = context or {}
    return {key: context.get(key, '') for key in SCOPE_FIELDS}


def same_companion_scope(left, right):
    return companion_scope(left) == companion_scope(right)
