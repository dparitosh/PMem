"""Failure isolation, cleanup recovery and database deadline regressions."""
import ast
from contextlib import nullcontext
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import MagicMock, Mock, patch

from backend.depo_platform.operations import OperationContext, operation_scope
from backend.depo_platform import postgres_pool, metadata_projection, metadata_service


def function(path, name, scope):
    node = next(n for n in ast.parse(Path(path).read_text(encoding='utf-8-sig')).body if isinstance(n, ast.FunctionDef) and n.name == name)
    node.decorator_list = []
    exec(compile(ast.Module(body=[node], type_ignores=[]), path, 'exec'), scope)
    return scope[name]


class DatabaseIntegrationFixes(unittest.TestCase):
    def context(self, seconds=3):
        return OperationContext('database-test', (datetime.now(timezone.utc)+timedelta(seconds=seconds)).isoformat())

    def test_failed_event_does_not_block_other_asset_or_acknowledge_failure(self):
        db=MagicMock(); db.__enter__.return_value=db
        cursor=db.cursor.return_value.__enter__.return_value
        event=lambda asset: {'before':None,'after':{'asset_id':asset,'name':asset},'actor':'verified'}
        cursor.fetchone.side_effect=[('bad','a',1,event('a')),('good','b',1,event('b')),None]
        graph=SimpleNamespace(query=Mock(side_effect=[None,RuntimeError('lost response'),None,[]]))
        module=ModuleType('backend.core.graph'); module.graph=graph
        with patch.object(metadata_service,'enabled',return_value=True), patch.object(metadata_service,'repository',return_value=SimpleNamespace(store=SimpleNamespace(_connect=lambda:db))), patch.dict(sys.modules,{'backend.core.graph':module}), patch('backend.depo_platform.ontology_maintenance.ontology_operation',return_value=nullcontext()) as lock:
            self.assertEqual(metadata_projection.project_pending(),1)
        lock.assert_called_once()
        acknowledgements=[c.args[1] for c in cursor.execute.call_args_list if "SET status='published'" in c.args[0]]
        self.assertEqual(acknowledgements,[('good',)])
        self.assertTrue(any("interval '30 seconds'" in c.args[0] and c.args[1]==('bad',) for c in cursor.execute.call_args_list))
        self.assertGreaterEqual(db.transaction.call_count,2)
        self.assertIn('SET a.projection_lock',graph.query.call_args.args[0])

    def test_cleanup_busy_prevents_any_projection_query(self):
        with patch.object(metadata_service,'enabled',return_value=True), patch.object(metadata_service,'repository',return_value=SimpleNamespace(store=Mock())), patch.dict(sys.modules,{'backend.core.graph':SimpleNamespace(graph=Mock())}), patch('backend.depo_platform.ontology_maintenance.ontology_operation',side_effect=ValueError('cleanup active')):
            with self.assertRaisesRegex(ValueError,'cleanup active'):
                metadata_projection.project_pending()

    def test_graph_reset_requeues_metadata_without_deleting_governance(self):
        from backend.depo_platform import maintenance
        db=MagicMock(); cursor=db.cursor.return_value.__enter__.return_value; cursor.rowcount=4
        with patch.dict(sys.modules,{'psycopg.types.json':SimpleNamespace(Jsonb=lambda value:value)}), patch('backend.depo_platform.credentials.uses_postgres',return_value=True),patch('backend.mesh_store.PostgresRegistry') as registry:
            registry.return_value._connect.return_value.__enter__.return_value=db
            result=maintenance.reconcile_graph_reset()
        self.assertEqual(result['requeued_metadata_events'],4)
        statements=[c.args[0] for c in cursor.execute.call_args_list]
        self.assertIn("UPDATE depo_metadata_outbox SET status='pending', created_at=now()",statements)
        self.assertFalse(any('DELETE' in query for query in statements))

    def test_sql_budget_recalculated_and_expiry_prevents_dispatch(self):
        raw=Mock(); cursor=postgres_pool._DeadlineCursor(raw)
        with operation_scope(self.context(2)):
            cursor.execute('SELECT 1')
        budget=raw.execute.call_args_list[0].args[1]
        self.assertGreater(int(budget[0]),0); self.assertLessEqual(int(budget[0]),2000)
        self.assertEqual(raw.execute.call_args_list[1].args,('SELECT 1',))
        raw.reset_mock()
        with operation_scope(self.context(-1)), self.assertRaises(TimeoutError): cursor.execute('SELECT 2')
        raw.execute.assert_not_called()

    def test_bulk_dispatch_checks_budget_between_rows(self):
        raw=Mock(rowcount=1); cursor=postgres_pool._DeadlineCursor(raw)
        with patch.object(cursor,'_budget',side_effect=[None,TimeoutError('expired')]),self.assertRaises(TimeoutError):
            cursor.executemany('INSERT',[(1,),(2,)])
        raw.execute.assert_called_once_with('INSERT',(1,))

    def test_isolation_selection_precedes_budget_sql(self):
        raw=Mock(); cursor=postgres_pool._DeadlineCursor(raw)
        with operation_scope(self.context(2)):
            cursor.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ')
            cursor.execute('SELECT 1')
        self.assertEqual(raw.execute.call_args_list[0].args,('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ',))
        self.assertIn('set_config',raw.execute.call_args_list[1].args[0])
        self.assertEqual(raw.execute.call_args_list[2].args,('SELECT 1',))

    def test_bulk_rowcount_matches_all_dispatched_rows(self):
        raw=Mock(rowcount=1); cursor=postgres_pool._DeadlineCursor(raw)
        with operation_scope(self.context(2)):
            cursor.executemany('INSERT',[(1,),(2,)])
        self.assertEqual(cursor.rowcount,2)
        with operation_scope(self.context(2)):
            cursor.execute('SELECT 1')
        self.assertEqual(cursor.rowcount,1)

    def test_expired_pool_budget_does_not_connect(self):
        connect=Mock()
        with patch.dict(sys.modules,{'psycopg':SimpleNamespace(connect=connect),'psycopg.pq':SimpleNamespace(TransactionStatus=SimpleNamespace(IDLE=0))}),operation_scope(self.context(-1)),self.assertRaises(TimeoutError):
            with postgres_pool.connection('expired-test'): pass
        connect.assert_not_called()

    def test_deadline_connection_resets_session_limits_before_reuse(self):
        database=Mock(closed=False,info=SimpleNamespace(transaction_status='idle'))
        connect=Mock(return_value=database)
        modules={'psycopg':SimpleNamespace(connect=connect),'psycopg.pq':SimpleNamespace(TransactionStatus=SimpleNamespace(IDLE='idle'))}
        with patch.dict(sys.modules,modules),operation_scope(self.context(3)):
            with postgres_pool.connection('operation-owned-connection',connect_timeout=10) as connection:
                self.assertIs(connection.database,database)
        self.assertEqual([call.args[0] for call in database.execute.call_args_list], ['RESET statement_timeout', 'RESET lock_timeout'])
        database.close.assert_not_called()
        postgres_pool.close_idle()
        self.assertGreaterEqual(connect.call_args.kwargs['connect_timeout'],2)
        self.assertLessEqual(connect.call_args.kwargs['connect_timeout'],3)

    def test_legacy_graph_driver_keeps_server_query_timeout(self):
        session=MagicMock()
        legacy=SimpleNamespace(_driver=SimpleNamespace(session=lambda **kwargs:session))
        scope=dict(NEO4J_QUERY_TIMEOUT=300,time=__import__('time'),CENTRALIZED_CONFIG_AVAILABLE=False,
                   get_graph=lambda:legacy,database='neo4j',
                   Query=lambda text,timeout:SimpleNamespace(text=text,timeout=timeout),logger=Mock())
        query=function('backend/core/graph.py','query_with_timeout',scope)
        with operation_scope(self.context(2)): query('RETURN 1')
        dispatched=session.__enter__.return_value.run.call_args.args[0]
        self.assertGreater(dispatched.timeout,0);self.assertLessEqual(dispatched.timeout,2)

    def test_graph_query_caps_server_timeout_and_rejects_expired_operation(self):
        session=MagicMock(); driver=SimpleNamespace(session=lambda **kwargs:session)
        scope=dict(NEO4J_QUERY_TIMEOUT=300,time=__import__('time'),CENTRALIZED_CONFIG_AVAILABLE=True,
                   get_config=lambda:SimpleNamespace(database='neo4j'),get_driver=lambda:driver,
                   Query=lambda text,timeout:SimpleNamespace(text=text,timeout=timeout),logger=Mock())
        query=function('backend/core/graph.py','query_with_timeout',scope)
        with operation_scope(self.context(2)): query('RETURN 1')
        dispatched=session.__enter__.return_value.run.call_args.args[0]
        self.assertGreater(dispatched.timeout,0);self.assertLessEqual(dispatched.timeout,2)
        session.reset_mock()
        with operation_scope(self.context(-1)),self.assertRaises(TimeoutError): query('CREATE ()')
        session.__enter__.return_value.run.assert_not_called()

    def test_memory_query_respects_budget_and_expiry_stays_best_effort(self):
        from backend.Services.agent_memory_service import AgentMemoryService as Memory
        session=MagicMock(); driver=Mock(); driver.session.return_value=session
        neo=SimpleNamespace(Query=lambda text,timeout:SimpleNamespace(text=text,timeout=timeout))
        with patch.dict(os.environ,{'AGENT_MEMORY_ENABLED':'true','AGENT_MEMORY_SCOPE':'test:project','AGENT_MEMORY_QUERY_TIMEOUT':'5','NEO4J_DATABASE':'neo4j'}),patch.dict(sys.modules,{'backend.core.db_config':SimpleNamespace(get_driver=lambda:driver),'neo4j':neo}),operation_scope(self.context(2)):
            Memory._query('RETURN 1')
        query=session.__enter__.return_value.run.call_args.args[0]
        self.assertGreater(query.timeout,0);self.assertLessEqual(query.timeout,2)
        driver.reset_mock()
        with patch.object(Memory,'enabled',return_value=True),operation_scope(self.context(-1)):
            self.assertIsNone(Memory._query('CREATE ()'))
        driver.session.assert_not_called()

    def test_bridge_retains_per_publication_evidence_without_parallel_instance_edges(self):
        tx=Mock()
        result=lambda value:SimpleNamespace(single=lambda:value)
        tx.run.side_effect=[result({'receipt':None}),SimpleNamespace(data=lambda:[{'sources':1,'targets':1}]),result({'applied':1}),SimpleNamespace(consume=lambda:None)]
        scope=dict(json=json,datetime=datetime,timezone=timezone)
        publish=function('backend/graph_service/bridge_publication.py','_publish_transaction',scope)
        command={'publication_id':'p','request_digest':'hash','approved_by':'actor','preview_id':'preview','ontology_id':'onto','rows':[{'candidate_id':'c'}]}
        with patch('backend.depo_platform.agent_memory_config.enabled',return_value=False):
            self.assertEqual(publish(tx,command)['applied_links'],1)
        query=tx.run.call_args_list[2].args[0]
        self.assertIn('evidence:DepoBridgeMapping {publication_id:$id, candidate_id:row.candidate_id}',query)
        self.assertIn('MERGE (evidence)-[:SOURCE]->(n)',query)
        self.assertIn('MERGE (evidence)-[:TARGET]->(target)',query)
        self.assertIn('MERGE (n)-[inst:INSTANCE_OF]->(target)',query)


if __name__=='__main__': unittest.main()
