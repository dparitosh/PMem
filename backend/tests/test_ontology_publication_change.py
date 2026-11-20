from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime,timezone,timedelta
import hashlib
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from fastapi import HTTPException
from backend.mesh_store import InMemoryRegistry
from backend.ontology_service import publication_change as change,publication_jobs as module,router as native
from backend.ontology_service.publication_jobs import PublicationJobs

class Store(InMemoryRegistry):
    def get(self,key):return deepcopy(super().get(key))
    def put(self,key,value):return super().put(key,deepcopy(value))

@pytest.fixture
def setup(monkeypatch):
    metadata={'name':'Engineering ontology','prefix':'eng','lifecycle_status':'approved','status':'active'}
    data={'content':b'@prefix ex: <urn:eng:> . ex:Part a <http://www.w3.org/2002/07/owl#Class> .'}
    catalog=SimpleNamespace(read_artifact=lambda key:(deepcopy(metadata),data['content']),with_publication_lock=lambda key,operation:operation())
    monkeypatch.setattr(native,'catalog',catalog)
    monkeypatch.setattr(native,'releases',SimpleNamespace(verify_artifact=lambda *args:None))
    monkeypatch.setattr(native,'graph_publications',Store())
    clock={'now':datetime.now(timezone.utc)}
    jobs=PublicationJobs(Store(),clock=lambda:clock['now']);monkeypatch.setattr(module,'publication_jobs',jobs)
    receipt={'ontology_id':'ontology','publication_id':hashlib.sha256(data['content']).hexdigest(),'status':'published','current':True,'resources':1,'relationships':0}
    from backend.ontology_service import publication_worker
    monkeypatch.setattr(publication_worker,'verify',lambda key:deepcopy(receipt) if (module.publication_jobs.get(key) or {}).get('change_request',{}).get('state') in {'executing','needs_recovery'} else {'status':'not_published','publication_idle':True})
    return jobs,data,metadata,receipt,clock


def act(action,actor='reviewer',reason='Review engineering vocabulary'):
    value=change.view('ontology');request=value['change_request']
    return change.transition('ontology',action,actor,request['revision'] if request else 0,value['current_plan_digest'],reason)
def authorize():act('submit','requester');act('accept');act('authorize','authorizer')


def test_submission_and_acceptance_never_enter_worker_queue(setup):
    jobs,*_=setup;act('submit');act('accept');execute=Mock()
    jobs.run_once(execute,lambda _:setup[3]);execute.assert_not_called()
    assert jobs.get('ontology')['status']=='review_pending'
    with pytest.raises(HTTPException):act('execute')


def test_authorization_queue_worker_and_current_receipt_are_separate(setup):
    jobs,*_=setup;authorize();assert jobs.get('ontology')['status']=='review_pending'
    value=act('execute','executor');assert value['change_request']['state']=='executing'
    assert jobs.get('ontology')['approved_by']=='authorizer'
    execute=Mock(return_value={'status':'published','ontology_id':'ontology','publication_id':setup[3]['publication_id']})
    jobs.run_once(execute,lambda _:setup[3]);assert execute.call_count==1
    assert change.view('ontology')['change_request']['state']=='executed'
    jobs.run_once(execute,lambda _:setup[3]);assert execute.call_count==1


def test_cancelled_request_blocks_native_submit_and_dispatch(setup):
    jobs,*_=setup;authorize();act('cancel')
    with pytest.raises(ValueError):jobs.submit('ontology',setup[3]['publication_id'],'other')
    with pytest.raises(HTTPException):change.dispatch_guard('ontology','authorizer',setup[3]['publication_id'])
    execute=Mock();jobs.run_once(execute,lambda _:setup[3]);execute.assert_not_called()


@pytest.mark.parametrize('change_scope',['bytes','prefix','approval'])
def test_worker_revalidates_authorized_artifact_and_lifecycle(setup,change_scope):
    jobs,data,metadata,*_=setup;authorize();act('execute')
    if change_scope=='bytes':data['content']+=b' changed'
    elif change_scope=='prefix':metadata['prefix']='other'
    else:metadata['lifecycle_status']='retired'
    execute=Mock();jobs.run_once(execute,lambda _:{'status':'unverified'})
    execute.assert_not_called();assert jobs.get('ontology')['change_request']['state']=='needs_recovery'


def test_lost_response_recovers_by_receipt_without_replaying_write(setup):
    jobs,*_=setup;authorize();act('execute')
    execute=Mock(side_effect=TimeoutError('lost response'))
    jobs.run_once(execute,lambda _:{'status':'unverified'})
    assert jobs.get('ontology')['change_request']['state']=='needs_recovery'
    assert act('reconcile','reconciler')['change_request']['state']=='executed'
    assert execute.call_count==1


@pytest.mark.parametrize('field,value',[('current',False),('ontology_id','other'),('publication_id','other'),('resources',True),('relationships',-1)])
def test_wrong_or_stale_receipt_never_completes_order(setup,field,value):
    jobs,*_=setup;authorize();act('execute');setup[3][field]=value
    execute=Mock(return_value={'status':'published','ontology_id':'ontology','publication_id':jobs.get('ontology')['artifact_sha256']})
    jobs.run_once(execute,lambda _:setup[3])
    assert jobs.get('ontology')['change_request']['state']!='executed'
    with pytest.raises(HTTPException):act('reconcile')
    assert execute.call_count==1


def test_uncertain_managed_job_cannot_automatically_resume_even_when_idle(setup):
    jobs,*_=setup;authorize();act('execute');execute=Mock(side_effect=TimeoutError())
    jobs.run_once(execute,lambda _:{'status':'unverified'})
    setup[4]['now']+=timedelta(seconds=8)
    jobs.run_once(execute,lambda _:{'status':'not_published','resumable':True,'publication_idle':True})
    assert execute.call_count==1 and jobs.get('ontology')['status']!='queued'
    assert jobs.get('ontology')['change_request']['state']=='needs_recovery'


def test_stale_revision_and_old_publications_cannot_be_reapproved(setup):
    first=act('submit');act('accept')
    with pytest.raises(HTTPException):change.transition('ontology','authorize','other',first['change_request']['revision'],first['current_plan_digest'])
    setup[0].registry.put('ontology',{'ontology_id':'ontology','job_id':'old','artifact_sha256':setup[3]['publication_id'],'status':'published'})
    assert change.view('ontology')['already_applied']
    with pytest.raises(HTTPException):act('submit')


def test_managed_native_dispatch_requires_worker_state_and_exact_order(setup):
    jobs,*_=setup;authorize()
    with pytest.raises(HTTPException):change.dispatch_guard('ontology','authorizer',setup[3]['publication_id'])
    act('execute');job=jobs.get('ontology');job['status']='running';jobs.registry.put('ontology',job)
    change.dispatch_guard('ontology','authorizer',setup[3]['publication_id'])
    with pytest.raises(HTTPException):change.dispatch_guard('ontology','wrong',setup[3]['publication_id'])
    with pytest.raises(HTTPException):change.dispatch_guard('ontology','authorizer',None)


def test_central_projection_preserves_exact_order_and_verified_delivery(setup):
    from backend.oslc_service.change_control import normalize
    from backend.oslc_service.change_dossier import build_dossier
    jobs,*_=setup;authorize();act('execute');jobs.run_once(lambda job:setup[3],lambda _:setup[3])
    job=jobs.get('ontology');summary=normalize('publications',job)
    assert summary['type']=='oslc_cm:ChangeRequest' and summary['receipt_retained']
    assert build_dossier('publications',job,summary,'http://local')['release']['order']['operation']=='publish_ontology_artifact'
    job['change_request']['order']['authorized_by']='other'
    assert not normalize('publications',job)['receipt_retained']


def test_queue_expiry_without_dispatch_requires_explicit_requeue(setup):
    jobs,*_=setup;authorize();act('execute');setup[4]['now']+=timedelta(days=2)
    execute=Mock();jobs.run_once(execute,lambda _:{})
    execute.assert_not_called()
    assert jobs.get('ontology')['change_request']['state']=='authorized'
    assert jobs.get('ontology')['status']=='timed_out'
    act('execute','second-executor')
    assert jobs.get('ontology')['status']=='queued'


from backend.tests.test_reporting_trs_postgres import reporting_db


def test_postgres_request_survives_restart_and_receipt_recovery(reporting_db,setup,monkeypatch):
    Registry=type(reporting_db)
    with reporting_db._connect() as db:
        db.execute("CREATE TABLE depo_registry(namespace text NOT NULL,key text NOT NULL,value jsonb NOT NULL,updated_at timestamptz NOT NULL DEFAULT now(),PRIMARY KEY(namespace,key))")
    setup[0].registry=Registry('ontology_publication_jobs_v1')
    authorize()
    jobs=PublicationJobs(Registry('ontology_publication_jobs_v1'));monkeypatch.setattr(module,'publication_jobs',jobs)
    act('execute','executor');execute=Mock(side_effect=TimeoutError('lost response'))
    jobs.run_once(execute,lambda _:{'status':'unverified'})
    jobs=PublicationJobs(Registry('ontology_publication_jobs_v1'));monkeypatch.setattr(module,'publication_jobs',jobs)
    assert change.view('ontology')['change_request']['state']=='needs_recovery'
    assert act('reconcile','reconciler')['change_request']['state']=='executed'
    assert execute.call_count==1


def test_native_command_checks_approval_before_reading_artifact(setup,monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    monkeypatch.setattr(native,'approval_identity',Mock(side_effect=HTTPException(403,'Approval access rejected')))
    fingerprint=Mock(side_effect=AssertionError('Unauthorized artifact read'))
    monkeypatch.setattr(change,'fingerprint',fingerprint)
    app=FastAPI();app.include_router(native.router,prefix='/api/v1')
    response=TestClient(app).post('/api/v1/ontologies/ontology/change',json={'action':'submit','expected_revision':0,'expected_plan_digest':'a'*64,'reason':'Review'})
    assert response.status_code==403
    fingerprint.assert_not_called()


@pytest.mark.parametrize('existing',[{'status':'published'},{'status':'unverified'},{'status':'not_published','publication_idle':False}])
def test_absent_local_history_cannot_hide_existing_or_uncertain_graph_state(setup,monkeypatch,existing):
    from backend.ontology_service import publication_worker
    monkeypatch.setattr(publication_worker,'verify',lambda key:existing)
    with pytest.raises(HTTPException):act('submit')
    assert not setup[0].get('ontology')
