import json
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from backend.data_pipeline_service import semantic_catalog,run_records
from backend.artifact_store import ArtifactStore

@pytest.fixture
def result_client(tmp_path,monkeypatch):
 monkeypatch.setenv('AUTH_MODE','token');monkeypatch.setenv('DEPO_CREDENTIAL_STORE','environment');monkeypatch.setenv('GRAPH_READ_TOKEN','reader')
 store=ArtifactStore(tmp_path/'artifacts');artifact=store.ingest_bytes(json.dumps({'algorithm':'business-overview','configuration_id':'baseline','rows':[],'private_extra':'not a display field'}).encode(),filename='result.json',kind='data-job-output',provenance={'run_id':'owned'})
 monkeypatch.setattr('backend.artifact_store.ArtifactStore',lambda:store)
 record={'status':'completed','job_type':'semantic-dataset-analysis','output_manifest':{'configuration_id':'baseline','result_artifact_id':artifact['artifact_id']}}
 monkeypatch.setattr(run_records,'get',lambda _:record)
 app=FastAPI();app.include_router(semantic_catalog.router,prefix='/api/v1')
 return TestClient(app),record

def test_display_result_requires_access_and_owned_completed_evidence(result_client):
 c,record=result_client;url='/api/v1/pipeline/semantic/runs/owned/result'
 assert c.get(url).status_code==403
 r=c.get(url,headers={'Authorization':'Bearer reader'});assert r.status_code==200,r.text
 assert r.json()['run_id']=='owned';assert 'private_extra' not in r.json()
 assert c.get(url.replace('owned','foreign'),headers={'Authorization':'Bearer reader'}).status_code==409
 record['status']='running';assert c.get(url,headers={'Authorization':'Bearer reader'}).status_code==409

def test_deduplicated_replay_uses_exact_usage_receipt(tmp_path,monkeypatch):
 monkeypatch.setenv('AUTH_MODE','token');monkeypatch.setenv('DEPO_CREDENTIAL_STORE','environment');monkeypatch.setenv('GRAPH_READ_TOKEN','reader')
 store=ArtifactStore(tmp_path/'dedup');content=json.dumps({'algorithm':'business-mart','configuration_id':'baseline','rows':[]}).encode()
 first=store.ingest_bytes(content,filename='job-1.0.0-first-result.json',kind='data-job-output',media_type='application/json',provenance={'run_id':'first','job_id':'job','job_version':'1.0.0','correlation_id':'a'})
 replay=store.ingest_bytes(content,filename='job-1.0.0-replay-result.json',kind='data-job-output',media_type='application/json',provenance={'run_id':'replay','job_id':'job','job_version':'1.0.0','correlation_id':'b'})
 assert first['artifact_id']==replay['artifact_id'];assert first['usage_id']!=replay['usage_id']
 monkeypatch.setattr('backend.artifact_store.ArtifactStore',lambda:store)
 record={'job_id':'job','job_version':'1.0.0','correlation_id':'b','status':'completed','job_type':'semantic-business-mart','output_manifest':{'configuration_id':'baseline','result_artifact_id':replay['artifact_id'],'result_artifact_usage_id':replay['usage_id']}}
 monkeypatch.setattr(run_records,'get',lambda _:record)
 app=FastAPI();app.include_router(semantic_catalog.router,prefix='/api/v1');c=TestClient(app);url='/api/v1/pipeline/semantic/runs/replay/result';headers={'Authorization':'Bearer reader'}
 assert c.get(url,headers=headers).status_code==200
 record['output_manifest']['result_artifact_usage_id']=first['usage_id']
 assert c.get(url,headers=headers).status_code==409
 record['output_manifest'].pop('result_artifact_usage_id')
 assert c.get(url,headers=headers).status_code==200 # Earlier deployed manifests recover by exact server-owned usage identity.
 usage,_=store.resolve_usage(replay['artifact_id'],replay['usage_id']);assert usage['provenance']['run_id']=='replay'
