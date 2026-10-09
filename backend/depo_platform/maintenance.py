"""Shared cache invalidation and graph publication reconciliation."""
import uuid
from datetime import datetime, timezone


def cache_generation():
    from .credentials import uses_postgres
    if not uses_postgres():
        return 'local'
    from backend.mesh_store import PostgresRegistry
    try:
        record = PostgresRegistry('maintenance_state').get('cache_generation')
        return record.get('generation', 'initial') if record else 'initial'
    except Exception:
        # Never serve a potentially stale cache when the authority is unavailable.
        return None


def invalidate_shared_caches():
    from .credentials import uses_postgres
    if not uses_postgres():
        return False
    from backend.mesh_store import PostgresRegistry
    PostgresRegistry('maintenance_state').put('cache_generation', {
        'generation': uuid.uuid4().hex, 'changed_at': datetime.now(timezone.utc).isoformat()})
    return True


def reconcile_graph_reset():
    """Preserve governed artifacts/history, invalidate removed graph projections."""
    from .credentials import uses_postgres
    if not uses_postgres():
        return {'status': 'not_applicable'}
    from backend.mesh_store import PostgresRegistry
    from psycopg.types.json import Jsonb
    with PostgresRegistry('maintenance_state')._connect() as db, db.transaction(), db.cursor() as cursor:
        cursor.execute('UPDATE depo_registry SET value=value || %s, updated_at=now() WHERE namespace=%s',
                       (Jsonb({'status': 'not_published', 'receipt': None,
                               'invalidated_at': datetime.now(timezone.utc).isoformat(),
                               'invalidation_reason': 'admin graph reset'}), 'ontology_graph_publications_v1'))
        count = cursor.rowcount
        cursor.execute('UPDATE depo_registry SET value=value || %s, updated_at=now() WHERE namespace=%s AND value->>\'kind\'=\'publication\'',
                       (Jsonb({'status': 'stale', 'receipt': None,
                               'error': 'Graph reset removed publication evidence. Create and approve a new preview.',
                               'invalidated_at': datetime.now(timezone.utc).isoformat()}), 'semantic_bridge_jobs_v1'))
        bridge_count = cursor.rowcount
    return {'status': 'success', 'invalidated_publications': count,
            'invalidated_bridge_publications': bridge_count,
            'governed_artifacts_retained': True}
