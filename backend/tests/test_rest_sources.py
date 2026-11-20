import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from backend.mesh_store import InMemoryRegistry
from backend.data_pipeline_service import rest_sources as sources


@pytest.fixture
def registered(monkeypatch):
    # Adapter unit tests exercise the child implementation in-process; process
    # termination is covered separately with the real subprocess boundary.
    monkeypatch.setattr(sources, '_isolated_fetch', sources._fetch_in_process)
    monkeypatch.setenv('DEPO_REST_ALLOWED_HOSTS', 'api.example.com')
    monkeypatch.setattr(sources, 'store', InMemoryRegistry())
    return sources.register({'source_id':'parts-api','name':'Parts','endpoint':'https://api.example.com/parts','records_path':'data.items'}, 'tester')


def test_source_is_immutable_and_stores_reference_only(registered):
    assert sources.store.get('parts-api') == registered
    assert 'approval_token' not in registered
    with pytest.raises(FileExistsError):
        sources.register({'source_id':'parts-api','name':'Parts','endpoint':registered['endpoint']},'tester')


@pytest.mark.parametrize('endpoint', ['ftp://api.example.com/a','https://user:password@api.example.com/a','https://api.example.com/a?token=x','https://evil.example/a','https://api.example.com:444/a','https://api.example.com/a#key'])
def test_endpoint_policy_rejects_unsafe_or_secret_urls(registered, endpoint):
    with pytest.raises(ValueError): sources.endpoint_url(endpoint)


def test_http_source_supported_without_credentials(registered, transport):
    source=sources.register({'source_id':'public-api','name':'Public API','endpoint':'http://api.example.com/parts','records_path':'data.items'},'tester')
    assert sources.fetch(source)['record_count']==1
    assert 'Authorization' not in transport['calls'][0][2]['headers']


@pytest.mark.parametrize('header',['Authorization','X-API-Key','api-key'])
def test_http_credentials_supported(registered,transport,monkeypatch,header):
    monkeypatch.setenv('DEPO_REST_SECRET_PLM','external-token')
    source=sources.register({'source_id':'http-api','name':'HTTP','endpoint':'http://api.example.com','credential_ref':'DEPO_REST_SECRET_PLM','auth_header':header,'records_path':'data.items'},'tester')
    sources.fetch(source)
    assert transport['calls'][0][2]['headers'][header]==('Bearer external-token' if header=='Authorization' else 'external-token')


@pytest.mark.parametrize('change', [{'credential_ref':'GRAPH_READ_TOKEN'}, {'name':{}}, {'records_path':'data[0]'}, {'headers':{'Authorization':'secret'}}])
def test_registration_rejects_arbitrary_secret_and_payload_fields(registered, change):
    with pytest.raises(ValueError):
        sources.register({'source_id':'new-api','name':'Parts','endpoint':registered['endpoint'],**change},'tester')


@pytest.fixture
def transport(monkeypatch):
    from semantica.ingest import api_ingestor
    monkeypatch.setattr(sources.socket,'getaddrinfo',lambda *a,**k:[(2,1,6,'',('93.184.216.34',443))])
    state = {'data':{'data':{'items':[{'name':'Part A'}]}}, 'status':200, 'calls':[]}
    def request(method, endpoint, **kwargs):
        state['calls'].append((method,endpoint,kwargs))
        response=Mock(status_code=state['status'],headers={'Content-Type':'application/json'})
        response.iter_content.return_value=[json.dumps(state['data']).encode()]
        response.json.return_value=state['data']
        response.raise_for_status.return_value=None
        kwargs['hooks']['response'](response)
        return response
    monkeypatch.setattr(api_ingestor,'request_with_ssrf_guard',request)
    return state


def test_real_semantica_adapter_and_preview_are_bounded(registered, transport):
    transport['data']['data']['items']=[{'name':str(i)} for i in range(12)]
    result=sources.fetch(registered,preview=True)
    assert result['record_count']==12 and len(result['records'])==10
    method,endpoint,kwargs=transport['calls'][0]
    assert method=='GET' and kwargs['stream'] is True and kwargs['allow_private_ips'] is False


def test_only_dedicated_credential_is_sent(registered,transport,monkeypatch):
    monkeypatch.setenv('DEPO_REST_SECRET_PLM','external-token')
    sources.fetch({**registered,'credential_ref':'DEPO_REST_SECRET_PLM'})
    assert transport['calls'][0][2]['headers']['Authorization']=='Bearer external-token'


def test_missing_credential_fails_before_network(registered,transport,monkeypatch):
    monkeypatch.delenv('DEPO_REST_SECRET_MISSING',raising=False)
    with pytest.raises(ValueError,match='not configured'):
        sources.fetch({**registered,'credential_ref':'DEPO_REST_SECRET_MISSING'})
    assert not transport['calls']


@pytest.mark.parametrize('data',[{}, {'data':{'items':'wrong'}}, {'data':{'items':[1]}}, {'data':{'items':[{}]*1001}}])
def test_malformed_source_response(registered,transport,data):
    transport['data']=data
    with pytest.raises(ValueError): sources.fetch(registered)


def test_redirect_blocked(registered,transport):
    transport['status']=302
    with pytest.raises(ValueError,match='redirects'): sources.fetch(registered)


def test_response_bytes_are_bounded_before_json(registered,transport,monkeypatch):
    monkeypatch.setattr(sources,'MAX_BYTES',4)
    with pytest.raises(ValueError,match='limit'): sources.fetch(registered)


def test_loopback_never_allowed_even_with_private_optin(registered,transport,monkeypatch):
    monkeypatch.setenv('DEPO_REST_ALLOW_PRIVATE','true')
    monkeypatch.setattr(sources.socket,'getaddrinfo',lambda *a,**k:[(2,1,6,'',('127.0.0.1',443))])
    with pytest.raises(ValueError,match='network'): sources.fetch(registered)
    assert not transport['calls']


def test_worker_retains_source_without_claiming_semantic_acceptance(registered,monkeypatch):
    monkeypatch.setattr(sources,'fetch',lambda source:{'records':[{'name':'Part'}],'record_count':1})
    retain=Mock(return_value={'artifact_id':'sha256:source'})
    monkeypatch.setattr(sources,'ArtifactStore',lambda:SimpleNamespace(ingest_bytes=retain))
    result=sources.execute(None,{'source_id':'parts-api'},correlation_id='test')
    assert result['partition_artifacts']=={'source':'sha256:source'}
    assert result['semantic_validation']=='not_assessed'
    assert result['publication']=='not_attempted'
    assert retain.call_args.kwargs['provenance']['source_id']=='parts-api'


def test_handler_contract_is_exposed():
    from backend.data_pipeline_service.handlers import registry
    assert registry.contracts()['rest-source-ingest']==('registered-rest-source-v1','rest-source-records-v1')


def test_source_list_is_paged_and_rejects_unbounded_limit(registered):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from backend.depo_platform.authorization import graph_read_identity
    from backend.data_pipeline_service.rest_router import router
    for index in range(120): sources.store.create(f'source-{index:03}',{'source_id':f'source-{index:03}'})
    app=FastAPI();app.include_router(router);app.dependency_overrides[graph_read_identity]=lambda:'reader'
    client=TestClient(app)
    first=client.get('/pipeline/rest-sources?limit=50').json()
    second=client.get('/pipeline/rest-sources?limit=50&offset=50').json()
    assert first['total']==121 and len(first['sources'])==50 and first['next_offset']==50
    assert not {r['source_id'] for r in first['sources']} & {r['source_id'] for r in second['sources']}
    assert client.get('/pipeline/rest-sources?limit=10000').status_code==422


def test_pipeline_openapi_passes_deployment_contract_gate():
    from backend.data_pipeline_service.app import app
    from backend.depo_platform.openapi_contract import contract_errors, normalize_openapi
    assert contract_errors(normalize_openapi(app.openapi())) == []


def test_routes_enforce_distinct_management_and_execution_credentials(registered,transport,monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from backend.data_pipeline_service.rest_router import router
    monkeypatch.setenv('AUTH_MODE','token')
    monkeypatch.setenv('DEPO_CREDENTIAL_STORE','environment')
    monkeypatch.setenv('DATA_JOB_APPROVAL_TOKEN','management-token')
    monkeypatch.setenv('DATA_JOB_EXECUTION_TOKEN','execution-token')
    app=FastAPI();app.include_router(router)
    client=TestClient(app)
    assert client.post('/pipeline/rest-sources/parts-api/preview',json={}).status_code==403
    assert client.post('/pipeline/rest-sources/parts-api/preview',json={},headers={'Authorization':'Bearer management-token'}).status_code==403
    response=client.post('/pipeline/rest-sources/parts-api/preview',json={},headers={'Authorization':'Bearer execution-token'})
    assert response.status_code==200 and response.json()['preview_only'] is True
    assert client.post('/pipeline/rest-sources',json={'source_id':'new-api','name':'New','endpoint':registered['endpoint']},headers={'Authorization':'Bearer execution-token'}).status_code==403


def test_rest_acquisition_is_queued_without_fetching_in_api(registered,monkeypatch):
    from backend.data_pipeline_service import router as pipeline
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from backend.data_pipeline_service import rest_submissions
    monkeypatch.setattr(rest_submissions,'store',InMemoryRegistry())
    monkeypatch.setattr(pipeline.run_records,'get',lambda key:None)
    monkeypatch.setattr(pipeline,'_authorize_execution',lambda request,payload:('tester',payload))
    monkeypatch.setattr(pipeline,'_worker_execution_enabled',lambda:True)
    monkeypatch.setattr(pipeline.job_definitions,'get',lambda *args:{'job_id':'fetch','version':'1.0.0','job_type':'rest-source-ingest','enabled':True,'lifecycle_state':'approved'})
    queue=Mock(return_value={'run_id':'queued-rest','status':'queued'})
    monkeypatch.setattr(pipeline.run_records,'enqueue',queue)
    fetch=Mock(side_effect=AssertionError('Network fetch must execute in worker'))
    monkeypatch.setattr(sources,'fetch',fetch)
    app=FastAPI();app.include_router(pipeline.router)
    response=TestClient(app).post('/pipeline/jobs/definitions/fetch/1.0.0/run',json={'source_id':'parts-api','idempotency_key':'request-one'})
    assert response.status_code==200 and response.json()['status']=='queued'
    assert queue.call_args.args[1]['source_id']=='parts-api'
    fetch.assert_not_called()


def test_ten_rest_sources_are_independent_and_listed_together(monkeypatch):
    from backend.data_pipeline_service import rest_router
    monkeypatch.setenv('DEPO_REST_ALLOWED_HOSTS', 'api.example.com')
    monkeypatch.setattr(sources, 'store', InMemoryRegistry())
    for index in range(10):
        sources.register({'source_id': f'business-api-{index}', 'name': f'Business API {index}',
            'endpoint': f'https://api.example.com/source-{index}',
            'credential_ref': 'DEPO_REST_SECRET_TEST'}, 'operator')
    page = rest_router.sources(limit=50, offset=0)
    assert page['total'] == 10 and page['next_offset'] is None
    assert len({row['source_id'] for row in page['sources']}) == 10
    assert all(row['created_by'] == 'operator' for row in page['sources'])
    assert all(row['credential_ref'] == 'DEPO_REST_SECRET_TEST' for row in page['sources'])


def test_openapi_source_retains_contract_and_selected_get_operation(registered,monkeypatch,tmp_path):
    from backend.artifact_store import ArtifactStore
    artifacts=ArtifactStore(tmp_path/'contracts');monkeypatch.setattr(sources,'ArtifactStore',lambda:artifacts)
    document={'openapi':'3.0.3','info':{'title':'Engineering API'},'servers':[{'url':'https://api.example.com/v1'}],'paths':{'/parts':{'get':{'operationId':'getParts'}}}}
    row=sources.register({'source_id':'openapi-parts','name':'Released parts','endpoint':'https://api.example.com/v1/parts','openapi_document':document,'openapi_path':'/parts'},'reviewer')
    assert sources.store.get('openapi-parts')['openapi']==row['openapi']
    metadata,path=artifacts.resolve(row['openapi']['artifact_id'])
    assert json.loads(path.read_text(encoding='utf-8'))==document
    assert row['openapi']['operation_id']=='getParts' and row['openapi']['method']=='GET'
    assert metadata['kind']=='rest-source-openapi'
    assert 'openapi_document' not in row


@pytest.mark.parametrize('change',[{'endpoint':'https://api.example.com/other'},{'openapi_path':'/missing'},{'openapi_document':{'openapi':'2.0','paths':{}}}])
def test_openapi_registration_cannot_invent_an_operation_or_endpoint(registered,change):
    document={'openapi':'3.0.3','servers':[{'url':'https://api.example.com'}],'paths':{'/parts':{'get':{}}}}
    with pytest.raises(ValueError):sources.register({'source_id':'imported-api','name':'Parts','endpoint':'https://api.example.com/parts','openapi_document':document,'openapi_path':'/parts',**change},'reviewer')
    assert sources.store.get('imported-api') is None


def test_source_metadata_registration_does_not_grant_outbound_access(monkeypatch):
    from backend.data_pipeline_service import rest_router
    monkeypatch.delenv('DEPO_REST_ALLOWED_HOSTS',raising=False)
    monkeypatch.setattr(sources,'store',InMemoryRegistry())
    row=sources.register({'source_id':'awaiting-setup','name':'Parts API','endpoint':'https://api.example.com/parts'},'operator')
    assert row['source_id']=='awaiting-setup'
    assert rest_router.sources(limit=50,offset=0)['sources'][0]['connection_ready'] is False
    with pytest.raises(ValueError,match='Endpoint host'):sources.endpoint_url(row['endpoint'])


def test_openapi_source_can_be_saved_through_authenticated_http_contract(monkeypatch,tmp_path):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from backend.artifact_store import ArtifactStore
    from backend.data_pipeline_service.rest_router import router
    monkeypatch.setenv('AUTH_MODE','token');monkeypatch.setenv('DEPO_CREDENTIAL_STORE','environment');monkeypatch.setenv('DATA_JOB_APPROVAL_TOKEN','management-token')
    monkeypatch.delenv('DEPO_REST_ALLOWED_HOSTS',raising=False)
    monkeypatch.setattr(sources,'store',InMemoryRegistry());monkeypatch.setattr(sources,'ArtifactStore',lambda:ArtifactStore(tmp_path/'openapi'))
    app=FastAPI();app.include_router(router)
    document={'openapi':'3.0.3','info':{'title':'Engineering'},'servers':[{'url':'https://api.example.com'}],'paths':{'/parts':{'get':{}}}}
    response=TestClient(app).post('/pipeline/rest-sources',headers={'Authorization':'Bearer management-token'},json={'source_id':'imported-parts','name':'Engineering parts','endpoint':'https://api.example.com/parts','openapi_document':document,'openapi_path':'/parts'})
    assert response.status_code==201,response.text
    assert response.json()['openapi']['artifact_id'].startswith('sha256:')
    assert sources.store.get('imported-parts')['openapi']['path']=='/parts'
