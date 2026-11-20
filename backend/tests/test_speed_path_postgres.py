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


@pytest.mark.skipif(not os.getenv('DEPO_TEST_DATABASE_URL'),reason='Requires isolated depo_acceptance_test')
def test_new_workflow_revision_and_receipt_are_atomic():
 dsn=os.environ['DEPO_TEST_DATABASE_URL'];schema='depo_revision_test_'+uuid.uuid4().hex[:12]
 with psycopg.connect(dsn,autocommit=True,connect_timeout=5) as control:
  assert control.info.dbname=='depo_acceptance_test','Never run this fixture against an application database'
  control.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
  try:
   control.execute(sql.SQL('SET search_path TO {}').format(sql.Identifier(schema)))
   control.execute('CREATE TABLE depo_registry(namespace text,key text,value jsonb,updated_at timestamptz DEFAULT now(),PRIMARY KEY(namespace,key))')
   class Registry(PostgresRegistry):
    @contextmanager
    def _connect(self):
     with psycopg.connect(dsn,autocommit=True) as db:
      db.execute(sql.SQL('SET search_path TO {}').format(sql.Identifier(schema)));yield db
   changes=Registry('changes');definitions=Registry('definitions')
   old={'version':'1.0.0'};new={'version':'1.0.1'};pending={'state':'authorized'}
   definitions.create('old',old);changes.create('request',pending)
   control.execute("CREATE FUNCTION reject_receipt() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN IF NEW.namespace='changes' AND NEW.value->>'state'='executed' THEN RAISE EXCEPTION 'fixture receipt failure'; END IF; RETURN NEW; END $$")
   control.execute('CREATE TRIGGER reject_receipt BEFORE INSERT OR UPDATE ON depo_registry FOR EACH ROW EXECUTE FUNCTION reject_receipt()')
   params={'related_store':definitions,'expected_rows':{'old':old,'new':None},'updated_rows':{'old':old,'new':new},'expected_value':pending}
   with pytest.raises(psycopg.Error):changes.transition_bundle('request',{'state':'executed'},**params)
   assert definitions.get('new') is None and definitions.get('old')==old and changes.get('request')==pending
   control.execute('DROP TRIGGER reject_receipt ON depo_registry')
   assert changes.transition_bundle('request',{'state':'executed'},**params)
   assert definitions.get('new')==new and definitions.get('old')==old
   changes.create('competing',pending)
   assert changes.transition_bundle('competing',{'state':'executed'},**params) is False
   assert changes.get('competing')==pending and definitions.get('new')==new
  finally:control.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))
