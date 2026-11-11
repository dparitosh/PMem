import asyncio
from datetime import datetime,timedelta,timezone
from pathlib import Path
from unittest.mock import patch
import httpx
import pytest
from rdflib import Graph
from backend.depo_platform.projection_preparation import build_projection
from backend.depo_platform.product_lineage import validate_lineage,resolve_lineage
from backend.artifact_store import ArtifactStore
from backend.mesh_store import InMemoryRegistry
from backend.data_catalog_service.artifact_retention import ArtifactRetentionRegistry
from backend.data_catalog_service.product_contract import validate_revision

A='sha256:'+'a'*64


def test_projection_indexes_types_and_preserves_literals_blank_annotations():
    graph=Graph().parse(data='''@prefix ex: <urn:ex:> . @prefix owl:<http://www.w3.org/2002/07/owl#> .
    @prefix rdfs:<http://www.w3.org/2000/01/rdf-schema#> .
    ex:Part a owl:Class . ex:instance a ex:Part ; rdfs:label "Teil"@de,"Part"@en ; ex:mass "2"^^<http://www.w3.org/2001/XMLSchema#decimal> .
    ex:Part ex:restriction [ a owl:Restriction; rdfs:comment "Retained blank expression" ] .''',format='turtle')
    with patch.object(graph,'objects',side_effect=AssertionError('Repeated resource lookup')):
        resources,edges,_=build_projection(graph)
    indexed={r['iri']:r for r in resources}
    assert indexed['urn:ex:instance']['kind']=='individual'
    assert indexed['urn:ex:instance']['label']=='Part'
    assert 'decimal' in indexed['urn:ex:instance']['rdf_properties']
    assert any(r['description']=='Retained blank expression' and r['kind']=='restriction' for r in resources)
    assert sum(map(len,edges.values()))==sum(1 for _,_,obj in graph if not isinstance(obj,__import__('rdflib').Literal))


@pytest.mark.parametrize('sources', [[42],['url'],[{}],[{'url':'http://attacker/','run_id':'r'}],[{'artifact_id':'invalid'}]])
def test_malformed_lineage_rejected(sources):
    with pytest.raises(ValueError): validate_lineage({'sources':sources})


def test_lineage_resolves_configured_owners_and_artifact_membership(monkeypatch):
    monkeypatch.setenv('DATA_PIPELINE_SERVICE_URL','http://pipeline:8019/api/v1')
    seen=[]
    async def peer(method,url,**kwargs):
        seen.append(url)
        return httpx.Response(200,json={'run_id':'run-a','status':'completed','output_manifest':{'artifact_id':A}})
    with patch('backend.depo_platform.product_lineage.async_peer_response',peer),patch('backend.depo_platform.product_lineage.service_bearer_headers',return_value={}):
        result=asyncio.run(resolve_lineage({'sources':[{'run_id':'run-a'}]},[({'artifact_id':A},Path('fixture'))]))
    assert seen==['http://pipeline:8019/api/v1/pipeline/jobs/runs/run-a']
    assert result['status']=='resolved' and result['graph_publication_verified'] is False


@pytest.mark.parametrize('response', [
    {'run_id':'wrong','status':'completed','output_manifest':{'artifact_id':A}},
    {'run_id':'run-a','status':'running','output_manifest':{'artifact_id':A}},
    {'run_id':'run-a','status':'completed','output_manifest':{'artifact_id':'sha256:'+'b'*64}},
])
def test_lineage_identity_status_and_package_mismatch_fail_closed(response):
    async def peer(*args,**kwargs): return httpx.Response(200,json=response)
    with patch('backend.depo_platform.product_lineage.async_peer_response',peer),patch('backend.depo_platform.product_lineage.service_bearer_headers',return_value={}):
        with pytest.raises(ValueError): asyncio.run(resolve_lineage({'sources':[{'run_id':'run-a'}]},[({'artifact_id':A},Path('fixture'))]))


def test_referenced_artifact_retention_refuses_deletion(tmp_path,monkeypatch):
    monkeypatch.delenv('DEPO_DATABASE_URL',raising=False);monkeypatch.delenv('DATABASE_URL',raising=False)
    artifacts=ArtifactStore(tmp_path)
    item=artifacts.ingest_bytes(b'fixture',filename='part.ttl',provenance={'run_id':'retained-run'})
    retention=ArtifactRetentionRegistry.__new__(ArtifactRetentionRegistry)
    retention.store=InMemoryRegistry();retention.artifact_store=artifacts
    now=datetime.now(timezone.utc);retention._now=lambda:now
    retention.register(item['artifact_id'],{'retention_days':1,'reason':'Fixture'},'reviewer')
    retention._now=lambda:now+timedelta(days=2)
    with pytest.raises(ValueError,match='usage provenance'): retention.purge(item['artifact_id'],'reviewer','Expired')
    assert artifacts.resolve(item['artifact_id'])[1].read_bytes()==b'fixture'
    assert retention.store.get('policy:'+item['artifact_id'])['status']=='active'


def test_description_backfill_must_match_immutable_manifest():
    old={'name':'Part evidence','manifest':{'description':'Business purpose'},'lifecycle_state':'published'}
    validate_revision(old,{**old,'description':'Business purpose'})
    with pytest.raises(ValueError): validate_revision(old,{**old,'description':'Invented new purpose'})
