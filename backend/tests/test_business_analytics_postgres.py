"""Real PostgreSQL business evidence at explicit role and record grains."""
import os,uuid,tempfile
from pathlib import Path
from contextlib import contextmanager
from unittest.mock import patch
import pytest
import psycopg
from psycopg import sql
from backend.artifact_store import ArtifactStore
from backend.mesh_store import PostgresRegistry
from backend.data_pipeline_service import semantic_datasets as datasets,semantic_configuration as configuration,business_analytics as business

DATA=b'''@prefix p: <urn:business:> .
p:portfolio a p:Product; p:part p:a,p:b,p:c .
p:a a p:Part; p:family "A"; p:satisfies p:r1; p:child p:b; p:process p:machining .
p:b a p:Part; p:family "B" .
p:c a p:Part; p:family "A"; p:process p:machining .
p:r1 a p:Requirement . p:r2 a p:Requirement . p:machining a p:Process .'''
MODEL={'product_class':'urn:business:Product','part_class':'urn:business:Part','requirement_class':'urn:business:Requirement','process_class':'urn:business:Process','product_part_property':'urn:business:part','classification_properties':['urn:business:family'],'requirement_property':'urn:business:satisfies','bom_property':'urn:business:child','process_property':'urn:business:process'}

@pytest.mark.skipif(not os.getenv('DEPO_TEST_DATABASE_URL'),reason='Requires isolated depo_acceptance_test')
def test_product_to_manufacturing_metrics_keep_grain_and_unknown_completeness():
 dsn=os.environ['DEPO_TEST_DATABASE_URL'];schema='business_acceptance_'+uuid.uuid4().hex[:12]
 with psycopg.connect(dsn,autocommit=True) as control,tempfile.TemporaryDirectory() as temporary:
  assert control.info.dbname=='depo_acceptance_test'
  control.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
  try:
   control.execute(sql.SQL('SET search_path TO {}').format(sql.Identifier(schema)))
   control.execute(Path('infra/postgres/migrations/015_semantic_datasets.sql').read_text(encoding='utf-8'))
   control.execute('CREATE TABLE depo_registry(namespace TEXT NOT NULL,key TEXT NOT NULL,value JSONB NOT NULL,updated_at TIMESTAMPTZ DEFAULT now(),PRIMARY KEY(namespace,key))')
   class Registry(PostgresRegistry):
    @contextmanager
    def _connect(self,**kwargs):
     with psycopg.connect(dsn,autocommit=True) as db:
      db.execute(sql.SQL('SET search_path TO {}').format(sql.Identifier(schema)));yield db
    _session_connect=_connect
   store=ArtifactStore(Path(temporary));artifact=store.ingest_bytes(DATA,filename='business.ttl')
   with patch.object(configuration,'PostgresRegistry',Registry),patch.object(configuration,'ArtifactStore',return_value=store),patch.object(configuration,'capture_trs_start',return_value={'state':'captured','order':0}),patch.object(datasets,'PostgresRegistry',Registry),patch.object(datasets,'ArtifactStore',return_value=store),patch.object(datasets,'resolve_source',return_value={'name':'Business fixture','version':'1.0.0'}),patch.object(business,'PostgresRegistry',Registry):
    receipt=datasets.materialize({'source_id':'catalog:test:1.0.0','artifact_id':artifact['artifact_id']},'test')
    payload={'dataset_id':receipt['dataset_id'],'business_model':MODEL}
    result=business.analyse_business(payload);metrics={r['measure']:r for r in result['rows']}
    assert metrics['Product records']['value']==1;assert metrics['Part records']['value']==3
    assert metrics['Requirements with a recorded part link (%)']['value']==50
    assert metrics['Parts with a recorded process link (%)']['value']==66.67
    assert metrics['BOM completeness (%)']['value'] is None
    assert metrics['Recorded parent-part to child-part links']['value']==1
    assert {r['value']:r['parts'] for r in result['classifications'][0]['rows']}=={'A':2,'B':1}
    unknown=business.analyse_business({**payload,'business_model':{k:v for k,v in MODEL.items() if k!='requirement_property'}})
    assert next(r for r in unknown['rows'] if r['measure']=='Requirements with a recorded part link (%)')['value'] is None
    with pytest.raises(ValueError,match='configuration'):business.analyse_business({**payload,'configuration_id':'wrong'})
  finally:control.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))

def test_business_model_contract_rejects_malformed_dimensions():
 from pydantic import TypeAdapter,ValidationError
 from backend.depo_platform.request_bodies import JobInputBody
 value=TypeAdapter(JobInputBody).validate_python({'dataset_id':'a'*64,'algorithm':'business-overview','business_model':MODEL})
 assert value['business_model']==MODEL
 with pytest.raises(ValidationError):TypeAdapter(JobInputBody).validate_python({'algorithm':'business-overview','business_model':{**MODEL,'classification_properties':'not a list'}})
 with pytest.raises(ValueError):business.analyse_business({'dataset_id':'a'*64,'business_model':{'product_class':'urn:P','part_class':'urn:A','sql':'DELETE'}})
