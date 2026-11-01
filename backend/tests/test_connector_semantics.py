import json
from types import SimpleNamespace
import pytest
from backend.artifact_store import ArtifactStore
from backend.data_pipeline_service import connector_semantics as module

@pytest.fixture
def source(monkeypatch,tmp_path):
 store=ArtifactStore(tmp_path)
 artifact=store.ingest_bytes(b'[{"part_number":"A","part_name":"Housing"}]',filename='parts.json',kind='connector-records')
 run={'run_id':'acquisition','status':'completed','job_type':'registered-source-ingest','source_system':'parts','output_manifest':{'partition_artifacts':{'source':artifact['artifact_id']}}}
 monkeypatch.setattr(module,'ArtifactStore',lambda:store);monkeypatch.setattr(module.run_records,'get',lambda _:run)
 monkeypatch.setattr(module,'contract',SimpleNamespace(version='fixture',mapping_pack=lambda _:{'digest':'mapping-v1','entities':{'Part':{'properties':{'name':'name','$source_id':'identifier'}}}},normalize_entity=lambda **kw:kw['record'],validate_projection=lambda **kw:{'conforms':True}))
 return {'acquisition_run_id':'acquisition','artifact_id':artifact['artifact_id'],'standard':'ap242','source_type':'Part','id_field':'part_number','attribute_fields':{'name':'part_name'}}

def test_normalization_reuses_canonical_contract_and_retains_only_a_proposal(source):
 result=module.execute(None,source,correlation_id='fixture')
 assert result['status']=='completed' and result['validation']['conforms'] is True
 assert result['publication']=='not_attempted' and 'proposal' in result['mapping_status']
 metadata,path=module.ArtifactStore().resolve(result['partition_artifacts']['accepted'])
 batch=json.loads(path.read_text());assert batch['entities']==[{'source_id':'A','source_type':'Part','attributes':{'name':'Housing'}}]
 assert batch['source_artifact_id']==source['artifact_id']

def test_foreign_artifacts_and_unknown_semantic_fields_are_rejected(source):
 with pytest.raises(ValueError,match='does not belong'):module.execute(None,{**source,'artifact_id':'sha256:'+'0'*64},correlation_id='fixture')
 with pytest.raises(ValueError,match='mapping pack'):module.execute(None,{**source,'attribute_fields':{'invented':'part_name'}},correlation_id='fixture')

def test_validation_failure_has_no_publishable_partition(source,monkeypatch):
 monkeypatch.setattr(module.contract,'validate_projection',lambda **kw:{'conforms':False})
 result=module.execute(None,source,correlation_id='fixture')
 assert result['status']=='quality_warning' and 'accepted' not in result['partition_artifacts'] and 'rejected' in result['partition_artifacts']
