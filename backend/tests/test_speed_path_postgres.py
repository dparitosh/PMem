"""Real failure inside a transaction, confined to a disposable test schema."""
import os,uuid
from pathlib import Path
from contextlib import contextmanager
import pytest
import psycopg
from psycopg import sql
from backend.mesh_store import PostgresRegistry

@pytest.mark.skipif(not os.getenv('DEPO_TEST_DATABASE_URL'),reason='Requires isolated depo_acceptance_test')
def test_event_receipt_bundle_rolls_back_all_rows_and_retries():
 dsn=os.environ['DEPO_TEST_DATABASE_URL'];schema='depo_event_test_'+uuid.uuid4().hex[:12]
 with psycopg.connect(dsn,autocommit=True,connect_timeout=5) as control:
  assert control.info.dbname=='depo_acceptance_test','Never run this fixture against an application database'
  control.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
  try:
   control.execute(sql.SQL('SET search_path TO {}').format(sql.Identifier(schema)))
   control.execute('CREATE TABLE depo_registry(namespace text,key text,value jsonb,updated_at timestamptz DEFAULT now(),PRIMARY KEY(namespace,key))')
   control.execute(Path('infra/postgres/migrations/017_speed_event_pagination.sql').read_text(encoding='utf-8'))
   class Registry(PostgresRegistry):
    @contextmanager
    def _connect(self):
     with psycopg.connect(dsn,autocommit=True) as db:
      db.execute(sql.SQL('SET search_path TO {}').format(sql.Identifier(schema)))
      yield db
   events=Registry('speed_path_events');reviews=Registry('speed_path_reconciliations')
   expected={key:{'event_id':key,'status':'accepted'} for key in ['a','b']}
   events.put_many(expected);receipt={'status':'reconciling'};reviews.create('review',receipt)
   updated={key:{**row,'status':'reconciled'} for key,row in expected.items()}
   control.execute("CREATE FUNCTION reject_second_event() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN IF NEW.key='b' AND NEW.value->>'status'='reconciled' THEN RAISE EXCEPTION 'fixture failure'; END IF; RETURN NEW; END $$")
   control.execute('CREATE TRIGGER fixture_failure BEFORE UPDATE ON depo_registry FOR EACH ROW EXECUTE FUNCTION reject_second_event()')
   with pytest.raises(psycopg.Error):reviews.transition_bundle('review',{'status':'ready'},related_store=events,expected_rows=expected,updated_rows=updated,expected_value=receipt)
   assert events.get('a')==expected['a'] and events.get('b')==expected['b'] and reviews.get('review')==receipt
   control.execute('DROP TRIGGER fixture_failure ON depo_registry')
   assert reviews.transition_bundle('review',{'status':'ready'},related_store=events,expected_rows=expected,updated_rows=updated,expected_value=receipt)
   assert events.get('a')['status']=='reconciled' and reviews.get('review')['status']=='ready'
  finally:control.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))
