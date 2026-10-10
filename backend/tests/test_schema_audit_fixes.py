import os
import sys
import unittest
from unittest.mock import MagicMock, patch
from contextlib import contextmanager
from backend.depo_platform import database_setup as setup
from backend.depo_platform.schema_contract import CONSTRAINTS, INDEXES, verify_structure
from backend.postgres_migrations import MIGRATIONS, MIGRATIONS_DIR, migration_checksum, apply_migrations


def catalog_fixture(schema='semantic'):
    defaults = {('depo_schema_migrations','applied_at'):'now()', ('depo_registry','updated_at'):'now()', ('depo_metadata_assets','updated_at'):'now()', ('depo_metadata_events','created_at'):'now()', ('depo_metadata_outbox','created_at'):'now()', ('depo_metadata_outbox','status'):"'pending'::text", ('depo_chat_messages','message_id'):f"nextval('{schema}.depo_chat_messages_message_id_seq'::regclass)"}
    attrs = [(table,column,'YES' if table=='depo_ontology_analytics' or column=='checksum' or (table,column)==('depo_api_credentials','expires_at') else 'NO',defaults.get((table,column))) for table,columns in setup.EXPECTED_COLUMNS.items() for column in columns]
    credential_defaults = {('depo_api_credentials','revoked'):'false', ('depo_api_credentials','updated_at'):'now()', ('depo_api_credential_events','created_at'):'now()'}
    attrs = [(table,column,nullable,credential_defaults.get((table,column),default)) for table,column,nullable,default in attrs]
    constraints = [(table,name,definition,True,schema if definition.startswith('FOREIGN') else None) for name,(table,definition) in CONSTRAINTS.items()]
    indexes = [(name,f'CREATE INDEX {name} {definition}',True,True) for name,definition in INDEXES.items()]
    relations = [(table,'v' if table=='depo_ontology_analytics' else 'r') for table in setup.EXPECTED_COLUMNS]
    view = (MIGRATIONS_DIR/'004_ontology_analytics_view.sql').read_text(encoding='utf-8').split('AS\n',1)[1]
    return [attrs,constraints,indexes,relations], [('a',f'{schema}.depo_api_credential_events_event_id_seq'), (f'{schema}.depo_chat_messages_message_id_seq',),(view,)]

class SchemaAudit(unittest.TestCase):
    def cursor(self, mutate=None):
        lists, singles = catalog_fixture()
        if mutate: mutate(lists,singles)
        cursor = MagicMock(); cursor.fetchall.side_effect = lists; cursor.fetchone.side_effect = singles
        return cursor
    def test_valid_contract(self):
        verify_structure(self.cursor(), 'semantic', setup.EXPECTED_COLUMNS)
    def test_nullable_required_column_rejected(self):
        def bad(lists,singles):
            index=next(i for i,row in enumerate(lists[0]) if row[:2]==('depo_registry','value'))
            lists[0][index]=('depo_registry','value','YES',None)
        with self.assertRaisesRegex(RuntimeError,'NOT NULL'): verify_structure(self.cursor(bad),'semantic',setup.EXPECTED_COLUMNS)
    def test_wrong_constraint_and_unvalidated_constraint_rejected(self):
        for wrong in ('CHECK(true)', CONSTRAINTS['depo_registry_value_object'][1]):
            def bad(lists,singles):
                index=next(i for i,row in enumerate(lists[1]) if row[1]=='depo_registry_value_object')
                lists[1][index]=('depo_registry','depo_registry_value_object',wrong,wrong=='CHECK(true)',None)
            with self.assertRaisesRegex(RuntimeError,'constraint'): verify_structure(self.cursor(bad),'semantic',setup.EXPECTED_COLUMNS)
    def test_invalid_index_rejected(self):
        def bad(lists,singles):
            name,definition,valid,ready=lists[2][0];lists[2][0]=(name,definition,False,ready)
        with self.assertRaisesRegex(RuntimeError,'index'): verify_structure(self.cursor(bad),'semantic',setup.EXPECTED_COLUMNS)
    def test_wrong_view_and_sequence_rejected(self):
        for which in (1,2):
            def bad(lists,singles): singles[which]=(None if which==1 else 'SELECT 1',)
            with self.assertRaises(RuntimeError): verify_structure(self.cursor(bad),'semantic',setup.EXPECTED_COLUMNS)
    def test_revoked_default_drift_rejected(self):
        def bad(lists,singles):
            index=next(i for i,row in enumerate(lists[0]) if row[:2]==('depo_api_credentials','revoked'))
            lists[0][index]=('depo_api_credentials','revoked','NO','true')
        with self.assertRaisesRegex(RuntimeError,'default'): verify_structure(self.cursor(bad),'semantic',setup.EXPECTED_COLUMNS)
    def test_credential_events_identity_drift_rejected(self):
        def bad(lists,singles): singles[0]=('d','semantic.fake_sequence')
        with self.assertRaisesRegex(RuntimeError,'identity'): verify_structure(self.cursor(bad),'semantic',setup.EXPECTED_COLUMNS)
    def test_missing_credential_check_rejected(self):
        def bad(lists,singles):
            lists[1][:]=[row for row in lists[1] if row[1]!='depo_api_credentials_digest_lengths']
        with self.assertRaisesRegex(RuntimeError,'constraint'): verify_structure(self.cursor(bad),'semantic',setup.EXPECTED_COLUMNS)
    def test_checksum_drift_and_legacy_optin(self):
        for legacy in (False,True):
            conn=MagicMock();cursor=conn.cursor.return_value.__enter__.return_value
            cursor.fetchall.return_value=[(v,n,None if legacy else 'wrong') for v,n,_ in MIGRATIONS]
            with patch.dict(os.environ,{'DEPO_ACCEPT_LEGACY_MIGRATION_CHECKSUMS':'false'}):
                with self.assertRaises(RuntimeError): apply_migrations(conn)
        conn=MagicMock();cursor=conn.cursor.return_value.__enter__.return_value
        cursor.fetchall.return_value=[(v,n,None) for v,n,_ in MIGRATIONS]
        with patch.dict(os.environ,{'DEPO_ACCEPT_LEGACY_MIGRATION_CHECKSUMS':'true'}): apply_migrations(conn)
        self.assertEqual(sum('UPDATE depo_schema_migrations SET checksum' in c.args[0] for c in cursor.execute.call_args_list),len(MIGRATIONS))
    def test_verification_failure_rolls_back_migration_transaction(self):
        class Connection:
            def __init__(self): self.versions=[]; self.active=False
            @contextmanager
            def transaction(self):
                before=list(self.versions);self.active=True
                try: yield
                except BaseException: self.versions=before;raise
                finally: self.active=False
            def cursor(self): return MagicMock()
            def __enter__(self): return self
            def __exit__(self,*a): return False
        conn=Connection()
        def verify(value):
            self.assertTrue(value.active)
            raise RuntimeError('bad columns')
        with patch.dict(sys.modules,{'psycopg':MagicMock(connect=lambda *a,**kw:conn)}), patch.dict(os.environ,{'DEPO_DATABASE_URL':'postgresql://fixture'}), patch.object(setup,'initialise_schema'), patch.object(setup,'verify_migration_privileges'), patch.object(setup,'apply_migrations',side_effect=lambda c:c.versions.append(7)), patch.object(setup,'verify_schema',side_effect=verify):
            with self.assertRaises(RuntimeError): setup.setup_database()
        self.assertEqual(conn.versions,[])
    def test_registry_rejects_array_before_database_access(self):
        from backend.mesh_store import PostgresRegistry
        with self.assertRaisesRegex(ValueError,'JSON objects'):
            PostgresRegistry('test').put('key', [])
    def test_missing_default_rejected(self):
        def bad(lists,singles):
            index=next(i for i,row in enumerate(lists[0]) if row[:2]==('depo_registry','updated_at'))
            lists[0][index]=('depo_registry','updated_at','NO',None)
        with self.assertRaisesRegex(RuntimeError,'default'): verify_structure(self.cursor(bad),'semantic',setup.EXPECTED_COLUMNS)
    def test_checksum_normalizes_windows_line_endings(self):
        self.assertEqual(migration_checksum(['SELECT 1;\r\n']),migration_checksum(['SELECT 1;\n']))

if __name__ == '__main__': unittest.main()
