"""Idempotent delivery of PostgreSQL metadata events to the Neo4j read projection."""
import json


def project_pending(limit=20):
    from .metadata_service import enabled, repository
    if not enabled(): return 0
    from backend.core.graph import graph
    store=repository().store
    from backend.depo_platform.ontology_maintenance import ontology_operation
    import logging
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError('Metadata projection batch must be between 1 and 100')
    completed = 0
    visited = []
    # Share cleanup exclusion for selection, graph delivery and acknowledgement.
    with ontology_operation():
        for _ in range(limit):
            event_id = None
            try:
                with store._connect() as db, db.transaction(), db.cursor() as cursor:
                    cursor.execute('''SELECT o.event_id,e.asset_id,e.revision,e.value FROM depo_metadata_outbox o
                        JOIN depo_metadata_events e USING(event_id) WHERE o.status='pending'
                        AND o.created_at <= now() AND NOT (o.event_id = ANY(%s::text[]))
                        ORDER BY o.created_at,o.event_id LIMIT 1 FOR UPDATE OF o SKIP LOCKED''', (visited,))
                    row = cursor.fetchone()
                    if not row:
                        break
                    event_id,asset_id,revision,event = row
                    visited.append(event_id)
                    graph.query('CREATE CONSTRAINT metadata_asset_id IF NOT EXISTS FOR (a:MetadataAsset) REQUIRE a.asset_id IS UNIQUE')
                    before,after=event.get('before') or {},event['after']
                    fields=sorted(key for key in before.keys() | after.keys() if before.get(key)!=after.get(key))
                    graph.query('''MERGE (a:MetadataAsset {asset_id:$asset_id})
                        SET a.projection_lock=coalesce(a.projection_lock,0)+1
                        WITH a
                        FOREACH (_ IN CASE WHEN coalesce(a.governance_revision,0)<=$revision THEN [1] ELSE [] END |
                          SET a += $asset, a.governance_revision=$revision)
                        MERGE (e:MetadataAuditEvent {event_id:$event_id})
                        SET e.actor=$actor,e.action=$action,e.comment=$comment,e.revision=$revision,
                            e.before_json=$before,e.after_json=$after,e.created_at=$created_at,
                            e.changed_fields=$fields,e.before_values=$before_values,e.after_values=$after_values
                        MERGE (a)-[:HAS_AUDIT_EVENT]->(e)''',
                        params={'asset_id':asset_id,'asset':event['after'],'revision':revision,'event_id':event_id,
                                'actor':event['actor'],'comment':event.get('comment',''),
                                'action':'created' if event['before'] is None else 'lifecycle_transition' if before.get('lifecycle_status')!=after.get('lifecycle_status') else 'updated',
                                'created_at':event.get('created_at',after.get('updated_at')),'fields':fields,
                                'before_values':[str(before.get(key,'')) for key in fields],
                                'after_values':[str(after.get(key,'')) for key in fields],
                                'before':json.dumps(event['before']),'after':json.dumps(event['after'])})
                    cursor.execute("UPDATE depo_metadata_outbox SET status='published' WHERE event_id=%s", (event_id,))
                completed += 1
            except Exception as exc:
                if event_id is None:
                    raise
                # A response loss can leave the graph committed. Stable event IDs
                # make redelivery safe; defer this event so other assets progress.
                with store._connect() as db, db.cursor() as cursor:
                    cursor.execute("UPDATE depo_metadata_outbox SET created_at=now()+interval '30 seconds' WHERE event_id=%s AND status='pending'", (event_id,))
                logging.getLogger(__name__).error('Metadata projection deferred event_id=%s error_type=%s', event_id, type(exc).__name__)
    return completed
