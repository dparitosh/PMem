import ast
import os
import unittest
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from backend.depo_platform.ontology_maintenance import ontology_operation, OntologyMaintenanceBusy
from backend.Services.ontology_identity import normalize_ontology_entry, normalize_ontology_entries


class MaintenanceTests(unittest.TestCase):
    def guard(self, acquired=True):
        self.calls = []
        cursor = SimpleNamespace(execute=lambda query, params:self.calls.append(query), fetchone=lambda:(acquired,))
        registry = SimpleNamespace(_session_connect=lambda:nullcontext(SimpleNamespace(cursor=lambda:nullcontext(cursor))))
        return patch.dict('sys.modules', {'backend.mesh_store':SimpleNamespace(PostgresRegistry=lambda name:registry)})

    def test_writer_shared_lock_released_after_failure(self):
        with patch.dict(os.environ, {'DEPO_DATABASE_URL':'test'}), self.guard():
            with self.assertRaises(RuntimeError):
                with ontology_operation(): raise RuntimeError('write failed')
        self.assertIn('pg_try_advisory_lock_shared',self.calls[0])
        self.assertIn('pg_advisory_unlock_shared',self.calls[1])

    def test_cleanup_uses_exclusive_lock(self):
        with patch.dict(os.environ, {'DEPO_DATABASE_URL':'test'}), self.guard():
            with ontology_operation(cleanup=True): pass
        self.assertIn('pg_try_advisory_lock(',self.calls[0])

    def test_active_writer_blocks_cleanup(self):
        with patch.dict(os.environ, {'DEPO_DATABASE_URL':'test'}), self.guard(False):
            with self.assertRaises(OntologyMaintenanceBusy):
                with ontology_operation(cleanup=True): self.fail('must not enter')
        self.assertEqual(len(self.calls),1)

    def test_zero_live_counts_override_historical_counts(self):
        row = normalize_ontology_entry({'node_count':0,'relationship_count':0,'neo4j_nodes_merged':500,'neo4j_relationships_merged':99})
        self.assertEqual((row['node_count'],row['relationship_count']),(0,0))

    def test_registry_keeps_two_ids_with_same_prefix(self):
        tree=ast.parse(Path('backend/Services/ontology_upload_manager.py').read_text(encoding='utf-8'))
        fn=next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name=='_registry_index')
        fn.decorator_list=[]
        scope={'Dict':dict,'Any':object,'normalize_ontology_entries':normalize_ontology_entries}
        exec(compile(ast.Module(body=[fn],type_ignores=[]),'<registry>','exec'),scope)
        rows=scope['_registry_index']([{'ontology_id':'a','prefix':'splm'},{'ontology_id':'b','prefix':'splm'}])
        self.assertEqual(set(rows),{'a','b'})

    def reset(self, count=0, unavailable=False):
        tree=ast.parse(Path('backend/Services/neo4j_schema_cleaner.py').read_text(encoding='utf-8'))
        fn=next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name=='reset_database')
        def run(query):
            if unavailable: raise RuntimeError('offline')
            return SimpleNamespace(single=lambda:{'count':count})
        stats=SimpleNamespace(total_nodes=0,total_relationships=0)
        obj=SimpleNamespace(get_schema_stats=lambda:stats,delete_all_nodes_and_relationships=lambda:(True,''),
            drop_all_constraints=lambda:(True,''),drop_all_indexes=lambda:(True,''),database='test',
            driver=SimpleNamespace(session=lambda **kw:nullcontext(SimpleNamespace(run=run))))
        scope={'Dict':dict,'Any':object}
        exec(compile(ast.Module(body=[fn],type_ignores=[]),'<reset>','exec'),scope)
        return scope['reset_database'](obj,recreate_indexes=False)

    def test_reset_with_remaining_nodes_is_failure(self):
        self.assertEqual(self.reset(count=1)['status'],'FAIL')

    def test_reset_with_unavailable_verification_is_failure(self):
        self.assertEqual(self.reset(unavailable=True)['status'],'FAIL')

    def test_verified_empty_reset_succeeds(self):
        self.assertEqual(self.reset()['status'],'SUCCESS')
