import asyncio
from unittest.mock import AsyncMock
import httpx
import pytest
from backend.agentic_service import companion as module, companion_context


@pytest.fixture
def graph(monkeypatch):
    monkeypatch.setenv('COMPANION_LLM_ENABLED','false')
    monkeypatch.setattr(companion_context,'mapping_context',AsyncMock(return_value={'evidence':[],'status':'not_requested'}))
    real=httpx.AsyncClient
    def select(nodes,edges=None):
        transport=httpx.MockTransport(lambda req:httpx.Response(200,json={'nodes':nodes,'relationships':edges or []}))
        monkeypatch.setattr(module.httpx,'AsyncClient',lambda **kw:real(transport=transport,**kw))
    return select


def node(label,ontology,prefix):
    return {'elementId':ontology+':'+label,'properties':{'label':label,'ontology_id':ontology,
        'prefix':prefix,'search_score':5,'description':'Controlled synthetic domain fixture','publication_revision':'fixture-revision'}}


@pytest.mark.parametrize('label,ontology,prefix',[
    ('GeometricTolerance','ap242-v1','ap242'),('Characteristic','qif-v1','qif'),
    ('ProductInstance','plmxml-v1','splm'),('Requirement','mbse-v1','mbse')])
def test_domain_resource_keeps_identity_revision_and_explicit_limits(graph,label,ontology,prefix):
    graph([node(label,ontology,prefix)])
    result=asyncio.run(module.KnowledgeCompanion().ask(label,headers={},ontology_id=ontology,ontology_prefix=prefix))
    assert result['answerable'] is True
    evidence=result['evidence'][0]
    assert evidence['resource_id']==ontology+':'+label
    assert evidence['ontology_id']==ontology
    assert evidence['properties']['publication_revision']=='fixture-revision'
    assert result['retrieval']['semantic_entailment_verified'] is False


@pytest.mark.parametrize('problem',['foreign_prefix','missing_prefix','id_alias','dangling_relationship'])
def test_scope_and_relationship_failures_never_become_domain_answers(graph,problem):
    item=node('Characteristic','qif-v1','qif')
    edges=[]
    if problem=='foreign_prefix':item['properties']['prefix']='ap242'
    if problem=='missing_prefix':item['properties'].pop('prefix')
    if problem=='id_alias':item['properties']['ontology_id']='qif'
    if problem=='dangling_relationship':edges=[{'start':item['elementId'],'end':'unreturned-resource','type':'SATISFIES'}]
    graph([item],edges)
    with pytest.raises(RuntimeError):
        asyncio.run(module.KnowledgeCompanion().ask('Characteristic',headers={},ontology_id='qif-v1',ontology_prefix='qif'))


def test_prefix_only_question_cannot_use_another_domain(graph):
    graph([node('Characteristic','foreign','other')])
    with pytest.raises(RuntimeError):
        asyncio.run(module.KnowledgeCompanion().ask('Characteristic',headers={},ontology_prefix='qif'))


def test_empty_domain_does_not_fabricate_an_answer(graph):
    graph([])
    result=asyncio.run(module.KnowledgeCompanion().ask('GeometricTolerance',headers={},ontology_id='ap242-v1'))
    assert result['answerable'] is False and result['evidence']==[]
