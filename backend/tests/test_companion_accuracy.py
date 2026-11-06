import asyncio
import json
from unittest.mock import AsyncMock

import httpx
import pytest

from backend.agentic_service.companion_memory import retrieval_query
from backend.agentic_service.prompt_security import validate_summary
from backend.graph_service.search_evidence import search_properties


def test_definitions_survive_projection_without_forwarding_arbitrary_properties():
    props=search_properties({'description':'Source comment','publication_revision':'revision-1','password':'hidden',
        'rdf_properties':json.dumps({'http://www.w3.org/2004/02/skos/core#definition':[{'value':'Reviewed definition'}],
                                    'urn:secret':[{'value':'hidden'}]})})
    assert props['definition']=='Reviewed definition'
    assert props['description']=='Source comment'
    assert props['publication_revision']=='revision-1'
    assert 'hidden' not in json.dumps(props)
    assert search_properties({'rdf_properties':'bad-json'})=={}
    assert search_properties({'description':'a'*2000})['description']=='a'*1000


def test_new_topics_do_not_inherit_history_and_followups_keep_scope():
    turns=[{'user_request':'AP242 mappings','graph_context':{'ontology':'ap242'}},
           {'user_request':'QIF measurement','graph_context':{'ontology':'qif'}}]
    assert retrieval_query('QIF mappings',turns,{'ontology':'qif'})=='QIF mappings'
    assert retrieval_query('What about its properties?',turns,{'ontology':'qif'})=='QIF measurement What about its properties?'
    assert retrieval_query('What about its properties?',turns,{'ontology':'new'})=='What about its properties?'
    assert retrieval_query('What about its properties?',turns,{})=='What about its properties?'


def test_citation_validation_rejects_uncited_paragraphs_and_unknown_ids():
    for text in ('Supported [evidence:one]\n\nUncited new assertion.',
                 '- Supported [evidence:one]\n- Uncited assertion.',
                 'Claim [evidence:unknown]'):
        with pytest.raises(ValueError):validate_summary(text,['one'])
    assert validate_summary('Supported [evidence:one]\n\nOther supported point [evidence:one]',['one'])


@pytest.mark.parametrize('problem',['duplicate','missing','scope'])
def test_invalid_graph_identities_or_foreign_scope_never_answer(monkeypatch,problem):
    from backend.agentic_service import companion as module
    from backend.agentic_service import companion_context
    monkeypatch.setattr(companion_context,'mapping_context',AsyncMock(return_value={'evidence':[],'status':'not_requested'}))
    nodes=[{'elementId':'one','properties':{'label':'Product','ontology_id':'selected','search_score':1}}]
    if problem=='duplicate':nodes.append(dict(nodes[0]))
    if problem=='missing':nodes[0].pop('elementId')
    if problem=='scope':nodes[0]['properties']['ontology_id']='foreign'
    real=httpx.AsyncClient
    monkeypatch.setattr(module.httpx,'AsyncClient',lambda **kw:real(transport=httpx.MockTransport(lambda req:httpx.Response(200,json={'nodes':nodes,'relationships':[]})),**kw))
    with pytest.raises(RuntimeError):asyncio.run(module.KnowledgeCompanion().ask('product',headers={},ontology_id='selected'))


def test_cut_down_evidence_reports_limits_and_does_not_claim_semantic_verification(monkeypatch):
    from backend.agentic_service import companion as module
    monkeypatch.setenv('COMPANION_LLM_ENABLED','false')
    nodes=[{'elementId':str(i),'properties':{'label':'Product','search_score':1,'description':'Reviewed description'}} for i in range(10)]
    real=httpx.AsyncClient
    monkeypatch.setattr(module.httpx,'AsyncClient',lambda **kw:real(transport=httpx.MockTransport(lambda req:httpx.Response(200,json={'nodes':nodes,'relationships':[]})),**kw))
    result=asyncio.run(module.KnowledgeCompanion().ask('product',headers={}))
    assert result['retrieval']['selected_resources']==8
    assert result['retrieval']['selection_truncated'] is True
    assert result['retrieval']['semantic_entailment_verified'] is False
    assert len(result['retrieval']['evidence_sha256'])==64
    assert result['retrieval']['retrieved_at']
    assert 'does not establish whole-graph counts' in result['response']
    assert 'Reviewed description' in result['response']
