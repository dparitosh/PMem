"""Regression checks for resolved analytics audit findings."""
import pytest
from unittest.mock import patch,MagicMock
from backend.data_pipeline_service import analytics_catalog as catalog

def test_inventory_tolerates_missing_schema_in_legacy_completed_receipt():
    cursor=MagicMock();cursor.fetchone.return_value=(1,)
    cursor.fetchall.return_value=[({'run_id':'legacy','output_manifest':{'ods_receipt':{'status':'completed'}}},)]
    db=MagicMock();db.cursor.return_value.__enter__.return_value=cursor
    with patch.object(catalog,'PostgresRegistry') as registry:
        registry.return_value._connect.return_value.__enter__.return_value=db
        assert catalog.inventory(20,0)['datasets']==[]

def test_relationship_relations_available_for_consumption():
    model={'tables':[{'entity_id':'part','sql_name':'parts','relationships':[{'name':'children'}]}]}
    names={item['name'] for item in catalog.relations({},model)}
    from backend.Services.xsd_analytics_plan import sql_name
    assert sql_name('part/children/0/link') in names

def test_route_requires_authorization_and_validates_bounds():
    from fastapi import FastAPI, HTTPException
    from fastapi.testclient import TestClient
    app=FastAPI();app.include_router(catalog.router,prefix='/api/v1')
    def deny():raise HTTPException(403,'denied')
    app.dependency_overrides[catalog.graph_read_identity]=deny
    with patch.object(catalog,'inventory') as inventory:
        assert TestClient(app).get('/api/v1/pipeline/analytics').status_code==403
        inventory.assert_not_called()
    app.dependency_overrides[catalog.graph_read_identity]=lambda:'reader'
    with patch.object(catalog,'inventory',return_value={'datasets':[],'total':0}) as inventory:
        client=TestClient(app)
        assert client.get('/api/v1/pipeline/analytics?limit=101').status_code==422
        assert client.get('/api/v1/pipeline/analytics?offset=-1').status_code==422
        assert client.get('/api/v1/pipeline/analytics').status_code==200
        inventory.assert_called_once_with(20,0)

def test_database_failure_remains_unavailable_not_empty():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    app=FastAPI();app.include_router(catalog.router,prefix='/api/v1')
    app.dependency_overrides[catalog.graph_read_identity]=lambda:'reader'
    with patch.object(catalog,'inventory',side_effect=RuntimeError('postgres unavailable')):
        response=TestClient(app).get('/api/v1/pipeline/analytics')
        assert response.status_code==503
        assert 'datasets' not in response.json()


def test_execution_identity_is_server_resolved_and_requires_execution_access():
    from fastapi import FastAPI,HTTPException
    from fastapi.testclient import TestClient
    from backend.data_pipeline_service import router as pipeline
    app=FastAPI();app.include_router(pipeline.router,prefix='/api/v1')
    client=TestClient(app)
    with patch.object(pipeline,'service_write_identity',return_value='verified-actor') as identity:
        response=client.get('/api/v1/pipeline/jobs/execution-identity',headers={'Authorization':'Bearer scoped-test-token'})
        assert response.status_code==200
        assert response.json()=={'actor':'verified-actor','source':'authenticated-connection'}
        assert identity.call_args.kwargs['token_env']=='DATA_JOB_EXECUTION_TOKEN'
    with patch.object(pipeline,'service_write_identity',side_effect=HTTPException(403,'denied')):
        assert client.get('/api/v1/pipeline/jobs/execution-identity').status_code==403
