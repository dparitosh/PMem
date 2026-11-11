import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from backend.mesh_store import InMemoryRegistry
from backend.data_pipeline_service import connector_sources as sources,connector_adapters as adapters

@pytest.fixture
def profile(monkeypatch,tmp_path):
 p={'parts-profile':{'name':'LOCAL TEST parts','kind':'Parquet','resources':{'parts':'parts.parquet'},'connection_ref':'DEPO_CONNECTOR_SECRET_LOCAL'}}
 monkeypatch.setenv('DEPO_CONNECTOR_PROFILES',json.dumps(p));monkeypatch.setenv('DEPO_CONNECTOR_SECRET_LOCAL',json.dumps({'root':str(tmp_path)}));monkeypatch.setattr(sources,'store',InMemoryRegistry())
 return p

def test_registration_is_immutable_secret_free_and_reconciles_the_same_intent(profile):
 payload={'source_id':'local-parts','name':'LOCAL TEST parts','profile_id':'parts-profile','resource':'parts'}
 record=sources.register(payload,'tester');assert sources.register(payload,'tester')==record
 assert 'connection_ref' not in record and 'root' not in record
 with pytest.raises(FileExistsError):sources.register({**payload,'name':'Changed'},'tester')
 with pytest.raises(ValueError):sources.register({**payload,'password':'forbidden'},'tester')

def test_profile_changes_require_a_new_reviewed_registration(profile,monkeypatch):
 record=sources.register({'source_id':'local-parts','name':'Parts','profile_id':'parts-profile','resource':'parts'},'tester')
 profile['parts-profile']['resources']['parts']='other.parquet';monkeypatch.setenv('DEPO_CONNECTOR_PROFILES',json.dumps(profile))
 with pytest.raises(ValueError,match='profile changed'):sources.resolved(record)

def test_public_profile_never_discloses_connection_or_locations(profile):
 assert sources.public_profiles()==[{'profile_id':'parts-profile','name':'LOCAL TEST parts','kind':'Parquet','resources':['parts'],'configured':True}]

@pytest.mark.parametrize('kind',sources.KINDS)
def test_each_reviewed_adapter_dispatches_only_its_bounded_read(kind,monkeypatch,tmp_path):
 f=tmp_path/'parts.data';f.write_text('test')
 calls=[]
 class Fake:
  def __init__(self,*a,**kw):self.imap_client=Mock();calls.append(('init',a,kw))
  def ingest_file(self,*a,**kw):calls.append(('file',a,kw));return {'data':[{'part':'A'}]}
  def ingest_url(self,*a,**kw):return {'name':'A'}
  def ingest_feed(self,*a,**kw):return {'entries':[{'part':'A'}]}
  def ingest_public_api(self,*a,**kw):return {'records':[{'part':'A'}]}
  def ingest_database(self,*a,**kw):calls.append(('database',a,kw));return {'tables':{'Parts':{'rows':[{'part':'A'}]}}}
  def ingest_table(self,*a,**kw):calls.append(('table',a,kw));return {'data':[{'part':'A'}]}
  def connect_imap(self,*a,**kw):pass
  def ingest_mailbox(self,*a,**kw):self.imap_client.select('INBOX');self.imap_client.fetch('1','(RFC822)');return [{'subject':'A'}]
  def connect(self,*a,**kw):pass
  def read_resource(self,*a,**kw):return {'contents':[{'text':'A'}]}
  def ingest_repository(self,*a,**kw):calls.append(('repo',a,kw));return {'code_files':[{'name':'a.md'}]}
  def download_object(self,*a,**kw):return b'[{"part":"A"}]'
  def ingest_kafka(self,*a,**kw):
   calls.append(('stream',a,kw));return SimpleNamespace(consumer=SimpleNamespace(poll=lambda **kw:{'topic':[SimpleNamespace(value={'part':'A'})]},close=lambda:None))
 monkeypatch.setattr(adapters,'load_ingestor',lambda name:Fake)
 monkeypatch.setenv('DEPO_REST_ALLOWED_HOSTS','api.example.com')
 resource='https://api.example.com/data' if kind in {'Web','Feed','PublicAPI','Repo'} else 'Parts'
 settings={}
 if kind in {'Parquet','Arrow'}:resource='parts.data';settings={'root':str(tmp_path)}
 if kind=='DB':settings={'connection_string':'sqlite:///:memory:'}
 if kind=='Email':settings={'server':'mail.example.com','username':'tester','password':'never-persist'}
 if kind=='MCP':settings={'url':'https://api.example.com/mcp'};resource='urn:resource:parts'
 if kind=='CloudStorage':settings={'provider':'s3','bucket':'parts'};resource='parts.json'
 if kind=='Stream':
  settings={'bootstrap_servers':['broker:9092']};clock=iter([0,1,11]);monkeypatch.setattr(adapters.time,'monotonic',lambda:next(clock))
 output=adapters.acquire(kind,resource,settings);assert output['record_count']==1
 assert 'never-persist' not in json.dumps(output)
 if kind in {'Parquet','Arrow'}:assert calls[1][2]['limit']==1000
 if kind=='Stream':assert calls[1][2]['consumer_config']['enable_auto_commit'] is False
 if kind=='Repo':assert calls[1][2]['include_history'] is False

def test_real_parquet_and_arrow_reads(tmp_path):
 import pyarrow as pa
 import pyarrow.parquet as pq
 import pyarrow.ipc as ipc
 table=pa.table({'part':['A','B'],'quantity':[1,2]})
 pq.write_table(table,tmp_path/'parts.parquet')
 with pa.OSFile(str(tmp_path/'parts.arrow'),'wb') as sink:
  with ipc.new_file(sink,table.schema) as writer:writer.write_table(table)
 for kind,file in [('Parquet','parts.parquet'),('Arrow','parts.arrow')]:
  result=adapters.acquire(kind,file,{'root':str(tmp_path)});assert result['record_count']==2

def test_real_database_read_is_limited_and_excludes_connection_details(tmp_path):
 import sqlite3
 path=tmp_path/'source.sqlite'
 with sqlite3.connect(path) as db:db.execute('CREATE TABLE Parts (name TEXT)');db.execute("INSERT INTO Parts VALUES ('A')")
 result=adapters.acquire('DB','Parts',{'connection_string':'sqlite:///'+str(path)})
 assert result['records']==[{'name':'A'}]
 assert 'connection' not in json.dumps(result)

def test_read_only_email_proxy_does_not_mark_messages_seen():
 client=Mock();proxy=adapters.ReadOnlyMailbox(client);proxy.select('INBOX');proxy.fetch('1','(RFC822)')
 client.select.assert_called_once_with('INBOX',readonly=True);client.fetch.assert_called_once_with('1','(BODY.PEEK[])')

def test_limits_path_escape_and_secret_fields_are_enforced(tmp_path):
 outside=tmp_path/'outside';outside.write_text('x');root=tmp_path/'allowed';root.mkdir()
 with pytest.raises(ValueError):adapters.local_file('../outside',{'root':str(root)})
 with pytest.raises(ValueError):adapters.rows([{}]*1001)
 assert adapters.rows({'password':'never-persist','part':'A'})['records']==[{'part':'A'}]


def test_real_acquisition_child_preserves_only_bounded_records(profile,tmp_path,monkeypatch):
 import pyarrow as pa
 import pyarrow.parquet as pq
 monkeypatch.setenv('DEPO_SERVICE_RUNTIME_MODE','shared')
 pq.write_table(pa.table({'part':['LOCAL-A','LOCAL-B']}),tmp_path/'parts.parquet')
 record=sources.register({'source_id':'local-child','name':'LOCAL TEST child','profile_id':'parts-profile','resource':'parts'},'tester')
 result=sources.acquire(record)
 assert result['records']==[{'part':'LOCAL-A'},{'part':'LOCAL-B'}]
 assert result['semantic_validation']=='not_assessed'


def test_http_registration_requires_approval_and_never_returns_connection_settings(profile,monkeypatch):
 from fastapi import FastAPI
 from fastapi.testclient import TestClient
 from backend.data_pipeline_service.connector_router import router
 monkeypatch.setenv('AUTH_MODE','token');monkeypatch.setenv('DEPO_CREDENTIAL_STORE','environment')
 monkeypatch.setenv('GRAPH_READ_TOKEN','read-fixture');monkeypatch.setenv('DATA_JOB_APPROVAL_TOKEN','approve-fixture')
 app=FastAPI();app.include_router(router)
 with TestClient(app) as client:
  assert client.get('/pipeline/connector-sources/profiles').status_code==403
  response=client.get('/pipeline/connector-sources/profiles',headers={'Authorization':'Bearer read-fixture'})
  assert response.status_code==200 and 'connection_ref' not in response.text
  payload={'source_id':'http-parts','name':'Parts','profile_id':'parts-profile','resource':'parts'}
  assert client.post('/pipeline/connector-sources',json=payload).status_code==403
  response=client.post('/pipeline/connector-sources',json=payload,headers={'Authorization':'Bearer approve-fixture'})
  assert response.status_code==201 and response.json()['kind']=='Parquet'
  assert client.post('/pipeline/connector-sources',json={**payload,'resource':42},headers={'Authorization':'Bearer approve-fixture'}).status_code==422
