import ast
import copy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock
import pytest
from fastapi import HTTPException
from backend.depo_platform.cleanup_receipts import CleanupReceipt


class Store:
    def __init__(self): self.rows={}; self.fail=False
    def put(self,key,value):
        if self.fail: raise RuntimeError('fixture receipt failure')
        self.rows[key]=copy.deepcopy(value)


def test_intent_is_mandatory_and_post_action_storage_failure_remains_partial():
    store=Store();store.fail=True
    with pytest.raises(RuntimeError): CleanupReceipt(store)
    store.fail=False;receipt=CleanupReceipt(store)
    for phase in receipt.record['phases']: receipt.phase(phase,'completed')
    store.fail=True
    assert receipt.finish()['status']=='partial'
    assert receipt.record['receipt_persisted'] is False
    assert receipt.record['automatic_replay_allowed'] is False


def clean_function(store,monkeypatch):
    from backend.depo_platform import import_cleanup, ontology_cleanup, maintenance
    from backend import mesh_store
    monkeypatch.setattr(mesh_store,'PostgresRegistry',lambda namespace:store)
    def imports(*,dry_run=False):
        if dry_run:return {'status':'success'}
        raise RuntimeError('fixture registry outage')
    monkeypatch.setattr(import_cleanup,'clear_import_workflows',imports)
    monkeypatch.setattr(ontology_cleanup,'clear_ontology_registrations',lambda:{'status':'success','cleared':1,'verification':{}})
    monkeypatch.setattr(maintenance,'invalidate_shared_caches',lambda:None)
    node=next(n for n in ast.parse(Path('backend/routes/admin_routes.py').read_text()).body if getattr(n,'name','')=='clean_neo4j_schema')
    node.decorator_list=[]
    cleaner=MagicMock();cleaner.return_value.reset_database.return_value={'status':'SUCCESS'}
    ns={'CleanSchemaRequest':object,'CLEAN_SCHEMA_CONFIRM_TOKEN':'confirm','HTTPException':HTTPException,
        'SCHEMA_CLEANER_AVAILABLE':True,'Neo4jSchemaCleaner':cleaner,'logger':MagicMock(),
        '_reconcile_reset':lambda:{'status':'success'},'OSLCTRSService':MagicMock()}
    exec(compile(ast.Module(body=[node],type_ignores=[]),'cleanup.py','exec'),ns)
    return ns['clean_neo4j_schema'],cleaner


def test_partial_import_failure_after_graph_delete_returns_phase_receipt(monkeypatch):
    store=Store();clean,cleaner=clean_function(store,monkeypatch)
    result=clean(SimpleNamespace(confirm='confirm'))
    assert result['success'] is False and result['status']=='partial'
    receipt=result['cleanup_receipt']
    assert receipt['phases']['graph']=='completed'
    assert receipt['phases']['import_workflows']=='partial'
    assert store.rows[receipt['run_id']]['status']=='partial'
    cleaner.return_value.close.assert_called_once()


def test_receipt_outage_prevents_graph_reset(monkeypatch):
    store=Store();store.fail=True
    clean,cleaner=clean_function(store,monkeypatch)
    with pytest.raises(HTTPException):clean(SimpleNamespace(confirm='confirm'))
    cleaner.assert_not_called()
