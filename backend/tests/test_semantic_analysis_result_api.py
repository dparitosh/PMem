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
