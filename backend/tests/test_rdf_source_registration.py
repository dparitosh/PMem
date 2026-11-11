import pytest
from fastapi import FastAPI,HTTPException
from fastapi.testclient import TestClient
from backend.routes import metadata_registry_routes as routes
from backend.artifact_store import ArtifactStore

@pytest.fixture
def client(tmp_path,monkeypatch):
 records={}
 monkeypatch.setenv('AUTH_MODE','token');monkeypatch.setenv('DEPO_CREDENTIAL_STORE','environment');monkeypatch.setenv('ONTOLOGY_APPROVAL_TOKEN','author-token')
 store=ArtifactStore(tmp_path/'artifacts');monkeypatch.setattr('backend.artifact_store.ArtifactStore',lambda:store)
 def get(key):
  if key not in records:raise HTTPException(404,'missing')
  return records[key]
 def create(request,actor):
  value={**request.model_dump(),'asset_id':request.asset_id,'actor':actor};records[request.asset_id]=value;return value
 monkeypatch.setattr(routes,'get_metadata_asset',get);monkeypatch.setattr(routes,'create_metadata_asset',create)
 app=FastAPI();app.include_router(routes.router,prefix='/api/v1')
 return TestClient(app),records

def test_source_upload_is_retained_owned_draft_and_idempotent(client):
 c,records=client;args=dict(data={'name':'Parts'},files={'file':('parts.ttl',b'<urn:p> <urn:name> "Part" .','text/turtle')},headers={'Authorization':'Bearer author-token'})
 a=c.post('/api/v1/metadata-registry/rdf-sources',**args);assert a.status_code==201,a.text
 b=c.post('/api/v1/metadata-registry/rdf-sources',**args);assert b.status_code==201,b.text
 assert a.json()['source_id']==b.json()['source_id'];assert len(records)==1
 assert a.json()['asset']['lifecycle_status']=='draft';assert a.json()['approval_status']=='not_granted'
 assert a.json()['asset']['implementation_ref']==a.json()['artifact_id']

def test_source_upload_rejects_unauthorized_and_unsafe_content(client):
 c,records=client
 assert c.post('/api/v1/metadata-registry/rdf-sources',data={'name':'Bad'},files={'file':('bad.ttl',b'not RDF')}).status_code==403
 for filename,data in [('bad.ttl',b'not RDF'),('broken.rdf',b'<rdf:RDF>'),('../parts.ttl',b'<urn:p> <urn:n> "p" .'),('data.jsonld',b'{"@context":"https://remote.example/context"}')]:
  r=c.post('/api/v1/metadata-registry/rdf-sources',data={'name':'Bad'},files={'file':(filename,data)},headers={'Authorization':'Bearer author-token'})
  assert r.status_code==422,r.text
 assert not records
