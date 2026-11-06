"""Shared Companion scope projection; selection never grants authorization."""

SCOPE_FIELDS = ('ontology', 'ontology_prefix', 'page', 'node_id', 'run_id', 'product_id', 'product_version','reconciliation_id')


def companion_scope(context):
    context = context or {}
    return {key: context.get(key, '') for key in SCOPE_FIELDS}


def same_companion_scope(left, right):
    a, b = companion_scope(left), companion_scope(right)
    # A recorded business identity can follow the user between workspaces.
    # Page-only conversations still require an exact page match.
    if any(a[key] and a[key] == b[key] for key in ('node_id','run_id','product_id','reconciliation_id')):
        a.pop('page'); b.pop('page')
    return a == b
