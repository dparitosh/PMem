"""Import CR/CO does not write until exact native authority is established."""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import asyncio
import pytest
from fastapi import HTTPException
from backend.mesh_store import InMemoryRegistry
from backend.ingestion_service import import_change as change
from backend.depo_platform import approval_matrix
from backend.depo_platform.request_bodies import MergeChangeCommand

@pytest.fixture
def setup(monkeypatch):
    monkeypatch.setattr(change,'store',InMemoryRegistry('import-change-test'))
    monkeypatch.setattr(approval_matrix,'configuration',InMemoryRegistry('matrix-test'))
    task={'task_id':'import-a','filename':'assembly.xml','status':'ready_for_commit','committing':False,
          'parsed_rows':[{'name':'Bearing'}],'auto_schema':{'nodes':[]},'stats':{'ontology_mapping':'parts'},'workflow_id':'instances'}
    calls=[]
    async def commit(identifier):
        change.require_dispatch(identifier,task,task['auto_schema']);calls.append(identifier)
        task.update(status='processing',committing=True)
    fake=SimpleNamespace(_task_snapshot_path=lambda identifier:Path(identifier+'.json'),_read_status_task=lambda identifier:task,get_status=lambda identifier:deepcopy(task),
        _restore_task=lambda identifier:task,_persist_task=lambda identifier:None,commit_import=commit)
    monkeypatch.setattr(change,'service',lambda:fake)
    return task,calls

def act(action):
    current=change.view('import-a')
    return asyncio.run(change.command('import-a',MergeChangeCommand(action=action,expected_revision=current['change_request']['revision'],expected_plan_digest=current['current_plan_digest'],reason='Reviewed'),'reviewer'))

def authorize():
    change.submit('import-a','requester','Review assembly load');act('accept');act('authorize')

def test_execution_requires_authorized_co(setup):
    change.submit('import-a','requester','Review assembly load')
    with pytest.raises(HTTPException):act('execute')
    assert setup[1]==[]
    act('accept');act('authorize');result=act('execute')
    assert result['change_request']['state']=='executing' and setup[1]==['import-a']
    with pytest.raises(HTTPException):act('execute')
    assert setup[1]==['import-a']

def test_changed_rows_block_load_and_allow_cancellation(setup):
    authorize();setup[0]['parsed_rows'][0]['name']='Shaft'
    with pytest.raises(HTTPException):act('execute')
    assert not setup[1]
    assert act('cancel')['change_request']['state']=='cancelled'

def test_background_rechecks_configuration(setup):
    authorize();act('execute')
    setup[0]['auto_schema']['nodes']=['Changed']
    with pytest.raises(ValueError):change.require_dispatch('import-a',setup[0],setup[0]['auto_schema'])

def test_reconciliation_uses_native_receipt_not_queue_acceptance(setup):
    authorize();act('execute')
    assert act('reconcile')['change_request']['state']=='executing'
    setup[0].update(status='completed',committing=False,result={'nodes_created':1})
    assert act('reconcile')['change_request']['state']=='executed'
    assert setup[1]==['import-a']

def test_partial_or_unknown_load_is_never_certified(setup):
    authorize();act('execute')
    setup[0].update(status='outcome_unknown',committing=False)
    assert act('reconcile')['change_request']['state']=='needs_recovery'
    with pytest.raises(HTTPException):act('execute')
    setup[0].update(status='completed',result={'incomplete_relationships':['HAS_PART']})
    assert act('reconcile')['change_request']['state']=='needs_recovery'

def test_direct_importer_guard_rejects_missing_co(setup):
    with pytest.raises(HTTPException):change.require_dispatch('import-a',setup[0],setup[0]['auto_schema'])
    with pytest.raises(HTTPException):change.submit('../outside','reviewer','Invalid scope')


def test_cancelled_order_is_not_current_authorization(setup):
    authorize()
    assert not act('cancel')['authorization_valid']


def test_changed_native_receipt_is_not_current_evidence(setup):
    authorize();act('execute')
    setup[0].update(status='completed',committing=False,result={'nodes_created':1})
    assert act('reconcile')['authorization_valid']
    setup[0]['result']['nodes_created']=2
    assert not change.view('import-a')['authorization_valid']


def test_skipped_relationships_do_not_become_a_complete_receipt(setup):
    authorize();act('execute')
    setup[0].update(status='completed',committing=False,result={'nodes_created':1,'relationships_skipped':1})
    assert act('reconcile')['change_request']['state']=='executing'
    assert not change.view('import-a')['already_applied']
