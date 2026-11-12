import pytest
from backend.data_pipeline_service import reporting_store as store


def test_reporting_definition_rejects_sql_and_unbounded_scopes():
    with pytest.raises(ValueError):store.validate_definition({'ontology_ids':['v1'],'sql':'select *'})
    with pytest.raises(ValueError):store.validate_definition({'ontology_ids':[]})
    with pytest.raises(ValueError):store.validate_definition({'ontology_ids':['v1'],'max_lag_seconds':1})


def test_resource_normalisation_preserves_values_and_exact_scope():
    definition=store.validate_definition({'ontology_ids':['v1']})
    payload={'title':'Part','rdf:type':['urn:Part'],'properties':{'ontology_id':'v1','uri':'urn:part:1','mass':2.5,'variants':['A','B']}}
    resource=store.normalise('http://provider/oslc/resources/r?ontology_id=v1',payload,definition)
    assert resource['iri']=='urn:part:1' and len(resource['values'])==5
    assert store.normalise('http://provider/oslc/resources/r',payload,store.validate_definition({'ontology_ids':['v2']})) is None


def test_reporting_identity_survives_provider_host_change():
    assert store.resource_key('http://old/oslc/resources/r?ontology_id=v1')==store.resource_key('https://new/oslc/resources/r?ontology_id=v1')
    assert store.resource_key('http://old/oslc/resources/r?ontology_id=v1')!=store.resource_key('http://old/oslc/resources/r?ontology_id=v2')

def test_expired_base_cursor_restarts_staging_and_preserves_active(monkeypatch):
    from backend.data_pipeline_service import reporting_trs as consumer
    from types import SimpleNamespace
    state={**consumer.begin({},'test'),'active_generation':'retained','base_cursor':{'snapshot_id':'expired'},'base_started':True}
    def expired(cursor):raise RuntimeError('TRS Base snapshot expired or missing; restart from /oslc/trs/base')
    monkeypatch.setattr(store,'commit',lambda identifier,expected,updated,changes:updated)
    result=consumer._base_step('feed',state,{},SimpleNamespace(base=expired),0)
    assert result['active_generation']=='retained' and result['base_cursor'] is None
    assert result['building_generation']!=state['building_generation']


def test_reporting_api_has_named_request_contract():
    from fastapi import FastAPI
    from backend.data_pipeline_service.reporting_router import router
    from backend.depo_platform.openapi_contract import contract_errors,normalize_openapi
    app=FastAPI();app.include_router(router,prefix='/api/v1')
    assert contract_errors(normalize_openapi(app.openapi()))==[]


def test_missing_pending_events_cannot_advance_watermark():
    from backend.data_pipeline_service import reporting_trs as consumer
    from types import SimpleNamespace
    with pytest.raises(ValueError,match='pending events'):
        consumer._events_step('feed',{'trs_after':2},{},SimpleNamespace(changes=lambda after:{'events':[],'head_order':3}),0)
