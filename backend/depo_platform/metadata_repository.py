"""Transactional governance storage. Graph publication consumes the outbox.

Selected with DEPO_METADATA_STORAGE=postgres after verified legacy adoption.
"""
from uuid import uuid4
from datetime import datetime, timezone
from psycopg.types.json import Jsonb
from backend.mesh_store import PostgresRegistry


class MetadataConflict(ValueError):
    pass


class MetadataRepository:
    def __init__(self):
        self.store = PostgresRegistry('metadata')

    def get(self, asset_id):
        with self.store._connect() as db, db.cursor() as cursor:
            cursor.execute("SELECT a.revision,a.value,COALESCE((SELECT o.status FROM depo_metadata_events e JOIN depo_metadata_outbox o USING(event_id) WHERE e.asset_id=a.asset_id AND e.revision=a.revision),'pending') FROM depo_metadata_assets a WHERE a.asset_id=%s",(asset_id,))
            row=cursor.fetchone()
            return {**row[1],'revision':row[0],'publication_status':row[2]} if row else None

    def page(self, *, status=None, domain=None, limit=100, offset=0):
        with self.store._connect() as db, db.cursor() as cursor:
            cursor.execute("SELECT a.revision,a.value,COALESCE((SELECT o.status FROM depo_metadata_events e JOIN depo_metadata_outbox o USING(event_id) WHERE e.asset_id=a.asset_id AND e.revision=a.revision),'pending') FROM depo_metadata_assets a WHERE (%s::text IS NULL OR value->>'lifecycle_status'=%s) AND (%s::text IS NULL OR value->>'domain'=%s) ORDER BY value->>'name',asset_id LIMIT %s OFFSET %s",
                           (status,status,domain,domain,limit+1,offset))
            rows=cursor.fetchall()
            return {'assets':[{**row[1],'revision':row[0],'publication_status':row[2]} for row in rows[:limit]],'count':len(rows[:limit]),'limit':limit,'offset':offset,'has_more':len(rows)>limit}

    def history(self, asset_id, limit=100):
        with self.store._connect() as db, db.cursor() as cursor:
            cursor.execute('SELECT event_id,revision,value,created_at FROM depo_metadata_events WHERE asset_id=%s ORDER BY revision DESC LIMIT %s',(asset_id,limit))
            events=[]
            for event_id,revision,value,created in cursor.fetchall():
                before,after=value.get('before') or {},value.get('after') or {}
                fields=sorted(key for key in before.keys() | after.keys() if before.get(key)!=after.get(key))
                events.append({**value,'event_id':event_id,'revision':revision,'created_at':created.isoformat(),
                    'action':'created' if not before else 'lifecycle_transition' if before.get('lifecycle_status')!=after.get('lifecycle_status') else 'updated',
                    'changed_fields':fields,'before_values':[str(before.get(key,'')) for key in fields],
                    'after_values':[str(after.get(key,'')) for key in fields]})
                events.extend(value.get('legacy_history') or [])
            return events[:limit]

    def save(self, asset_id: str, value: dict, *, expected_revision: int, actor: str, comment: str = '', legacy_history=None) -> dict:
        from .metadata_validation import validate_asset_state
        validate_asset_state(value)
        if not asset_id or not actor.strip() or value.get('asset_id') != asset_id:
            raise ValueError('Matching asset_id and audit actor are required')
        if expected_revision < 0:
            raise ValueError('expected_revision must not be negative')
        with self.store._connect() as connection, connection.transaction(), connection.cursor() as cursor:
            cursor.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))', ('metadata:' + asset_id,))
            cursor.execute('SELECT revision, value FROM depo_metadata_assets WHERE asset_id=%s FOR UPDATE', (asset_id,))
            old = cursor.fetchone()
            if (old[0] if old else 0) != expected_revision:
                raise MetadataConflict('Metadata revision changed; reload before updating')
            revision = expected_revision + 1
            event_id = str(uuid4())
            event = dict(actor=actor, before=old[1] if old else None, after=value, revision=revision,
                         comment=comment, created_at=datetime.now(timezone.utc).isoformat())
            if legacy_history is not None: event['legacy_history'] = legacy_history
            cursor.execute('''INSERT INTO depo_metadata_assets(asset_id,revision,value) VALUES (%s,%s,%s)
                ON CONFLICT(asset_id) DO UPDATE SET revision=excluded.revision,value=excluded.value,updated_at=now()''',
                (asset_id, revision, Jsonb(value)))
            cursor.execute('INSERT INTO depo_metadata_events(event_id,asset_id,revision,value) VALUES (%s,%s,%s,%s)',
                           (event_id, asset_id, revision, Jsonb(event)))
            cursor.execute('INSERT INTO depo_metadata_outbox(event_id) VALUES (%s)', (event_id,))
            return dict(asset=value, revision=revision, event_id=event_id, publication_status='pending')
