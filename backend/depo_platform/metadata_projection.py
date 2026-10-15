"""Idempotent delivery of PostgreSQL metadata events to the Neo4j read projection."""
import json


def project_pending(limit=20):
    from .metadata_service import enabled, repository
    if not enabled(): return 0
    from backend.core.graph import graph
    store=repository().store
    with store._connect() as db, db.transaction(), db.cursor() as cursor:
        cursor.execute('''SELECT o.event_id,e.asset_id,e.revision,e.value FROM depo_metadata_outbox o
            JOIN depo_metadata_events e USING(event_id) WHERE o.status='pending'
            ORDER BY o.created_at,o.event_id LIMIT %s FOR UPDATE OF o SKIP LOCKED''',(limit,))
        rows=cursor.fetchall()
        if rows:
            graph.query('CREATE CONSTRAINT metadata_asset_id IF NOT EXISTS FOR (a:MetadataAsset) REQUIRE a.asset_id IS UNIQUE')
        for event_id,asset_id,revision,event in rows:
            before,after=event.get('before') or {},event['after']
            fields=sorted(key for key in before.keys() | after.keys() if before.get(key)!=after.get(key))
            graph.query('''MERGE (a:MetadataAsset {asset_id:$asset_id})
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
            cursor.execute("UPDATE depo_metadata_outbox SET status='published' WHERE event_id=%s",(event_id,))
    return len(rows)
