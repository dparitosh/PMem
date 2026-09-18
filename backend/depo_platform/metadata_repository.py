"""Transactional governance storage. Graph publication consumes the outbox.

Not selected by legacy routes until an explicit migration has been verified.
"""
from uuid import uuid4
from psycopg.types.json import Jsonb
from backend.mesh_store import PostgresRegistry


class MetadataConflict(ValueError):
    pass


class MetadataRepository:
    def __init__(self):
        self.store = PostgresRegistry('metadata')

    def save(self, asset_id: str, value: dict, *, expected_revision: int, actor: str) -> dict:
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
            event = dict(actor=actor, before=old[1] if old else None, after=value, revision=revision)
            cursor.execute('''INSERT INTO depo_metadata_assets(asset_id,revision,value) VALUES (%s,%s,%s)
                ON CONFLICT(asset_id) DO UPDATE SET revision=excluded.revision,value=excluded.value,updated_at=now()''',
                (asset_id, revision, Jsonb(value)))
            cursor.execute('INSERT INTO depo_metadata_events(event_id,asset_id,revision,value) VALUES (%s,%s,%s,%s)',
                           (event_id, asset_id, revision, Jsonb(event)))
            cursor.execute('INSERT INTO depo_metadata_outbox(event_id) VALUES (%s)', (event_id,))
            return dict(asset=value, revision=revision, event_id=event_id, publication_status='pending')
