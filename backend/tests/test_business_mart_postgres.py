"""Real isolated PostgreSQL: governed versions, unit conversion, rollback and retry."""
import os,uuid,tempfile
from pathlib import Path
from contextlib import contextmanager
from unittest.mock import patch
import psycopg
from psycopg import sql
import pytest
from backend.mesh_store import PostgresRegistry
from backend.artifact_store import ArtifactStore
from backend.data_pipeline_service import analytics_models as models,business_mart as marts,business_analytics as business,semantic_datasets as datasets,semantic_configuration as configuration
from backend.tests.test_business_analytics_postgres import DATA,MODEL


def test_definition_rejects_unsafe_or_ambiguous_models():
    base={'business_model':MODEL,'scope':'Pinned test revision A / effective date 2026-11-01'}
    assert models.validate_definition(base)==base
    with pytest.raises(ValueError):models.validate_definition({**base,'sql':'DROP TABLE x'})
    with pytest.raises(ValueError):models.validate_definition({**base,'expected_bom':[{'parent':'a','child':'a'}]})
    with pytest.raises(ValueError):models.validate_definition({**base,'kpis':[{'name':'Mass','role':'part','property':'urn:mass','unit':'kg','unit_property':'urn:unit','aggregation':'sum','conversions':[{'from_unit':'g','scale':'NaN','offset':'0'}]}]})


@pytest.mark.skipif(not os.getenv('DEPO_TEST_DATABASE_URL'),reason='Requires isolated depo_acceptance_test')
def test_approved_mart_materializes_all_grains_and_rolls_back_invalid_units():
    dsn=os.environ['DEPO_TEST_DATABASE_URL'];schema='mart_acceptance_'+uuid.uuid4().hex[:12]
    with psycopg.connect(dsn,autocommit=True) as control,tempfile.TemporaryDirectory() as temporary:
        assert control.info.dbname=='depo_acceptance_test'
        control.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
        try:
            control.execute(sql.SQL('SET search_path TO {}').format(sql.Identifier(schema)))
            for migration in ('015_semantic_datasets.sql','016_business_marts.sql'):
                control.execute((Path('infra/postgres/migrations')/migration).read_text(encoding='utf-8'))
            control.execute('CREATE TABLE depo_registry(namespace text,key text,value jsonb,updated_at timestamptz DEFAULT now(),PRIMARY KEY(namespace,key))')
            class Registry(PostgresRegistry):
                @contextmanager
                def _connect(self,**kwargs):
                    with psycopg.connect(dsn,autocommit=True) as db:
                        db.execute(sql.SQL('SET search_path TO {}').format(sql.Identifier(schema)));yield db
                _session_connect=_connect
            content=DATA+b'\n@prefix p: <urn:business:> . @prefix xsd: <http://www.w3.org/2001/XMLSchema#> . p:a p:mass 1000; p:unit "g" . p:b p:mass 2; p:unit "kg" . p:c p:mass 500; p:unit "g" .'
            store=ArtifactStore(Path(temporary));artifact=store.ingest_bytes(content,filename='business.ttl')
            with patch.object(configuration,'PostgresRegistry',Registry),patch.object(configuration,'ArtifactStore',return_value=store),patch.object(configuration,'capture_trs_start',return_value={'state':'captured','order':0}),patch.object(datasets,'PostgresRegistry',Registry),patch.object(datasets,'ArtifactStore',return_value=store),patch.object(datasets,'resolve_source',return_value={'name':'Business fixture','version':'1.0.0'}),patch.object(models,'PostgresRegistry',Registry),patch.object(marts,'PostgresRegistry',Registry),patch.object(business,'PostgresRegistry',Registry):
                source=datasets.materialize({'source_id':'catalog:test:1.0.0','artifact_id':artifact['artifact_id']},'test')
                dataset=source['dataset_id'];definition={'business_model':MODEL,'scope':'Test revision A / 2026-11-01 only; expected children reviewed',
                 'expected_bom':[{'parent':'urn:business:a','child':'urn:business:b'},{'parent':'urn:business:a','child':'urn:business:c'}],
                 'kpis':[{'name':'Total part mass','role':'part','property':'urn:business:mass','aggregation':'sum','unit':'kg','unit_property':'urn:business:unit','conversions':[{'from_unit':'g','scale':'0.001','offset':'0'},{'from_unit':'kg','scale':'1','offset':'0'}]}]}
                identity=models.create_model(dataset,'Test portfolio','1.0.0',definition,'author')
                assert models.create_model(dataset,'Test portfolio','1.0.0',definition,'author')==identity
                payload={'dataset_id':dataset,'analytics_model_id':identity}
                with pytest.raises(ValueError,match='not approved'):marts.materialize_mart(payload)
                models.approve_model(identity,'reviewer');result=marts.materialize_mart(payload)
                assert result['mart']['model_approved_by']=='reviewer'
                measures={r['measure']:r for r in result['rows']}
                assert float(measures['Total part mass']['value'])==3.5
                assert measures['BOM completeness (%)']['value']==50
                assert marts.materialize_mart(payload)['mart']==result['mart']
                with pytest.raises(ValueError,match='another dataset'):marts.materialize_mart({**payload,'dataset_id':'0'*64})
                counts={t['name']:t['rows'] for t in result['mart']['tables']}
                assert counts['depo_analytics_dim_entity']==7
                assert counts['depo_analytics_fact_measure']==3
                assert counts['depo_analytics_fact_link']==7
                bad={**definition,'kpis':[{**definition['kpis'][0],'conversions':[{'from_unit':'g','scale':'0.001','offset':'0'}]}]}
                invalid=models.create_model(dataset,'Invalid units','1.0.0',bad,'author');models.approve_model(invalid,'reviewer')
                with pytest.raises(ValueError,match='reviewed unit'):marts.materialize_mart({**payload,'analytics_model_id':invalid})
                assert control.execute('SELECT count(*) FROM depo_analytics_marts').fetchone()[0]==1
                assert control.execute('SELECT count(*) FROM depo_analytics_dim_entity').fetchone()[0]==7
                fenced=models.create_model(dataset,'Lease lost','1.0.0',definition,'author');models.approve_model(fenced,'reviewer')
                with patch.object(marts,'ensure_execution_allowed',side_effect=RuntimeError('lease lost')):
                    with pytest.raises(RuntimeError,match='lease lost'):marts.materialize_mart({**payload,'analytics_model_id':fenced})
                assert control.execute('SELECT count(*) FROM depo_analytics_marts').fetchone()[0]==1
        finally:
            control.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))
