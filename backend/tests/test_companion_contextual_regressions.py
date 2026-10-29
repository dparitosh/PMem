import asyncio
from unittest.mock import AsyncMock, Mock
import httpx
import pytest

from backend.depo_platform.plm_questions import intent, requirement_subject
from backend.agentic_service import companion, companion_context


@pytest.mark.parametrize('question,expected', [
    ('What requirements does Housing have?', 'associated_requirements'),
    ('Show the specifications linked to Housing.', 'associated_requirements'),
    ('Does Housing have PMI?', 'parts_with_pmi'),
    ('Show PMI for Housing.', 'parts_with_pmi'),
    ('Show product details for Housing.', 'product_assembly'),
])
def test_business_question_variants_have_consistent_routes(question, expected):
    assert intent(question) == expected


def test_requirement_subject_handles_common_question_forms():
    assert requirement_subject('What requirements does Housing have?') == 'Housing'
    assert requirement_subject('Show requirements associated with Housing.') == 'Housing'


def test_requirement_limit_applies_after_alternative_paths_are_grouped(monkeypatch):
    from backend.graph_service.plm_answers import retrieve
    monkeypatch.delenv('DEPO_DATABASE_URL', raising=False)
    monkeypatch.delenv('DATABASE_URL', raising=False)
    publisher = Mock(_session_rows=Mock(return_value=[]))
    retrieve(publisher, query='Show requirements associated with Housing.')
    query = publisher._session_rows.call_args.args[0]
    assert query.index('WITH p,q,head(collect(path))') < query.index('LIMIT 21')
    assert 'ORDER BY length(path)' in query
    assert 'recorded_path_count' in query


def test_named_pmi_question_binds_the_requested_business_subject(monkeypatch):
    from backend.graph_service.plm_answers import retrieve
    monkeypatch.delenv('DEPO_DATABASE_URL', raising=False)
    monkeypatch.delenv('DATABASE_URL', raising=False)
    publisher = Mock(_session_rows=Mock(return_value=[]))
    retrieve(publisher, query='Which parts have PMI for Housing?')
    assert publisher._session_rows.call_args.kwargs['subject'] == 'Housing'
    assert '$subject' in publisher._session_rows.call_args.args[0]


@pytest.mark.asyncio
async def test_business_answer_contract_rejects_a_different_intent(monkeypatch):
    monkeypatch.setattr(companion_context, '_read_json', AsyncMock(return_value=({
        'evidence_type':'business_answer', 'source':'graph-service:typed-business-read',
        'resource_id':'business-answer:test', 'rows':[], 'intent':'product_assembly'}, 'http://fixture')))
    with pytest.raises(ValueError, match='intent'):
        await companion_context.plm_context('Which parts have PMI?', headers={})


@pytest.mark.asyncio
async def test_generic_business_output_keeps_definitions_and_sanitizes_excerpts(monkeypatch):
    monkeypatch.setenv('COMPANION_LLM_ENABLED', 'false')
    monkeypatch.setattr(companion_context, 'mapping_context', AsyncMock(return_value={'status':'not_requested','evidence':[]}))
    monkeypatch.setattr(companion_context, 'page_context', AsyncMock(return_value={'status':'not_requested','evidence':[]}))
    monkeypatch.setattr(companion_context, 'document_context', AsyncMock(return_value={'status':'available','evidence':[
        {'evidence_type':'document_excerpt','resource_id':'doc','label':'Housing detail',
         'description':'<Property value="Housing requires inspection"/>', 'source':'fixture'}]}))
    real = httpx.AsyncClient
    graph = {'nodes':[{'elementId':'p','properties':{'label':'Housing','definition':'A machined enclosure.','search_score':4}}], 'relationships':[]}
    monkeypatch.setattr(companion.httpx, 'AsyncClient', lambda **kw:real(transport=httpx.MockTransport(lambda _:httpx.Response(200,json=graph)),**kw))
    result = await companion.KnowledgeCompanion().ask('Housing', headers={})
    assert 'A machined enclosure.' in result['response']
    assert 'Housing requires inspection' in result['response']
    assert '<Property' not in result['response']


@pytest.mark.asyncio
async def test_page_records_are_rendered_as_business_text_not_json(monkeypatch):
    monkeypatch.setattr(companion_context, '_read_json', AsyncMock(return_value=({'products':[
        {'id':'p','name':'Housing','status':'approved','version':'1.0'}]}, 'http://fixture')))
    result = await companion_context.page_context('show products', page='catalog', headers={})
    detail = result['evidence'][1]['description']
    assert 'approved' in detail and '1.0' in detail
    assert '{' not in detail and '"status"' not in detail


@pytest.mark.asyncio
async def test_selected_business_identity_is_reloaded_once_and_preserves_scope_aliases(monkeypatch):
    monkeypatch.setenv('COMPANION_LLM_ENABLED','false')
    monkeypatch.setattr(companion_context,'mapping_context',AsyncMock(return_value={'status':'not_requested','evidence':[]}))
    monkeypatch.setattr(companion_context,'page_context',AsyncMock(return_value={'status':'not_requested','evidence':[]}))
    monkeypatch.setattr(companion_context,'document_context',AsyncMock(return_value={'status':'no_evidence','evidence':[]}))
    graph={'root_node_id':'selected','nodes':[
        {'elementId':'selected','properties':{'label':'Housing','source_ontology':'o','ontology_prefix':'p','description':'Machined enclosure'}},
        {'elementId':'req','properties':{'label':'Inspection requirement','source_ontology':'o','ontology_prefix':'p'}}],
        'relationships':[{'elementId':'r','start':'selected','end':'req','type':'HAS_REQUIREMENT'}]}
    read=AsyncMock(return_value=(graph,'http://graph/business-context'))
    monkeypatch.setattr(companion_context,'business_context',read)
    result=await companion.KnowledgeCompanion().ask('Tell me more',headers={},ontology_id='o',ontology_prefix='p',page='modeling',node_id='selected')
    assert read.await_count==1
    assert read.call_args.args==('selected',)
    assert result['retrieval']['business_context_status']=='available'
    assert 'Machined enclosure' in result['response']


def test_history_cannot_cross_selected_business_objects():
    from backend.agentic_service.context_scope import same_companion_scope
    assert not same_companion_scope({'node_id':'one'}, {'node_id':'two'})
    assert same_companion_scope({}, {'node_id':''})


def test_selected_node_identity_reaches_typed_business_query(monkeypatch):
    from backend.graph_service.plm_answers import retrieve
    monkeypatch.delenv('DEPO_DATABASE_URL',raising=False);monkeypatch.delenv('DATABASE_URL',raising=False)
    publisher=Mock(_session_rows=Mock(return_value=[]))
    retrieve(publisher,query='Which parts have PMI?',node_id='selected')
    assert publisher._session_rows.call_args.kwargs['node_id']=='selected'
    assert 'elementId(p)=$node_id' in publisher._session_rows.call_args.args[0]


def test_business_values_and_units_survive_safe_projection():
    import json
    from backend.agentic_service.companion import descriptive_properties
    result=descriptive_properties({'rdf_properties':json.dumps({
        'urn:product/material':[{'value':'Steel'}], 'urn:product/value':[{'value':5}],
        'urn:product/unit':[{'value':'mm'}], 'urn:product/password':[{'value':'hidden'}]})})
    assert result['material']=='Steel' and result['value']=='5' and result['unit']=='mm'
    assert 'hidden' not in str(result)


def test_followup_reuses_business_subject_without_appending_old_question():
    from backend.agentic_service.companion_memory import retrieval_query
    query=retrieval_query('Which specifications are linked to it?',
        [{'user_request':'Show product details for Housing.', 'graph_context':{'page':'graph'}}], {'page':'graph'})
    assert query=='Which specifications are linked to Housing?'
    assert requirement_subject(query)=='Housing'


def test_selected_object_pronoun_does_not_become_a_literal_name_filter(monkeypatch):
    from backend.graph_service.plm_answers import retrieve
    monkeypatch.delenv('DEPO_DATABASE_URL',raising=False);monkeypatch.delenv('DATABASE_URL',raising=False)
    publisher=Mock(_session_rows=Mock(return_value=[]))
    retrieve(publisher,query='Does it have PMI?',node_id='housing-id')
    assert publisher._session_rows.call_args.kwargs['node_id']=='housing-id'
    assert publisher._session_rows.call_args.kwargs['subject']==''


def test_short_requirement_followup_retains_a_routable_business_subject():
    from backend.agentic_service.companion_memory import retrieval_query
    query=retrieval_query('And its requirements?',
        [{'user_request':'Show product details for Housing.','graph_context':{'page':'graph'}}],{'page':'graph'})
    assert intent(query)=='associated_requirements'
    assert requirement_subject(query)=='Housing'


@pytest.mark.asyncio
async def test_business_evidence_cannot_change_a_selected_node_with_the_same_name(monkeypatch):
    monkeypatch.setattr(companion_context,'_read_json',AsyncMock(return_value=({
        'evidence_type':'business_answer','source':'graph-service:typed-business-read',
        'resource_id':'business-answer:test','intent':'parts_with_pmi','rows':[
            {'part':'Housing','part_id':'different-id','pmi':'Diameter','association_status':'recorded_association'}]},'http://fixture')))
    with pytest.raises(ValueError,match='selected business object'):
        await companion_context.plm_context('Does it have PMI?',headers={},node_id='selected-id')


def test_vocabulary_is_scoped_and_conflicting_labels_are_not_selected():
    from backend.graph_service.vocabulary_evidence import read_vocabulary, unique_label
    publisher=Mock(_session_rows=Mock(return_value=[{'iri':'urn:uses','label':'Uses'},{'iri':'urn:uses','label':'Contains'}]))
    vocabulary=read_vocabulary(publisher,['urn:uses'],ontology_id='selected',ontology_prefix='product')
    assert unique_label(vocabulary,'urn:uses') is None
    assert publisher._session_rows.call_args.kwargs['scope']=='selected'
    assert 'NOT term:StagedOntologyResource' in publisher._session_rows.call_args.args[0]


@pytest.mark.asyncio
async def test_empty_business_result_does_not_ask_the_model_to_invent_facts(monkeypatch):
    from backend.agentic_service import local_llm
    monkeypatch.setenv('COMPANION_LLM_ENABLED','true')
    monkeypatch.setattr(companion_context,'mapping_context',AsyncMock(return_value={'status':'not_requested','evidence':[]}))
    monkeypatch.setattr(companion_context,'document_context',AsyncMock(return_value={'status':'no_evidence','evidence':[]}))
    monkeypatch.setattr(companion_context,'plm_context',AsyncMock(return_value={
        'evidence_type':'business_answer','resource_id':'business-answer:empty','intent':'parts_with_pmi',
        'label':'Business evidence','rows':[],'source':'graph-service:typed-business-read'}))
    summarize=AsyncMock();monkeypatch.setattr(local_llm,'summarize',summarize)
    result=await companion.KnowledgeCompanion().ask('Which parts have PMI?',headers={})
    summarize.assert_not_called()
    assert result['generation']['status']=='not_requested'
    assert 'could not verify' in result['response']


@pytest.mark.parametrize('returned_id,answerable',[('selected-id',True),('foreign-id',False)])
def test_http_chat_round_trip_preserves_selected_identity_and_retains_the_validated_answer(monkeypatch, returned_id, answerable):
    from types import SimpleNamespace
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from backend.agentic_service import router as routes
    monkeypatch.setenv('COMPANION_LLM_ENABLED','false')
    async def io(fn,*args,**kwargs):return fn(*args,**kwargs)
    original_authorization=routes.graph_read_identity
    monkeypatch.setattr(routes,'graph_read_identity',lambda _: 'reader')
    monkeypatch.setattr(routes,'_agent_io',io)
    monkeypatch.setattr(routes,'_session_turns',lambda *_:[])
    monkeypatch.setattr(routes,'downstream_headers',lambda *a,**k:{'Authorization':'Bearer read-fixture'})
    monkeypatch.setattr(routes,'sessions',SimpleNamespace(open_session=lambda *_:{'session_id':'s','owner':'reader','expires_at':'2030-01-01T00:00:00+00:00'},memory_id=lambda _:'m',owner=lambda *_:'reader'))
    monkeypatch.setattr(routes,'telemetry',SimpleNamespace(start=lambda **_ :({'run_id':'r'},0)))
    monkeypatch.setattr(routes,'_finish_observation',lambda *a,**k:None)
    monkeypatch.setattr(routes,'AgentMemoryService',SimpleNamespace(enabled=lambda:False))
    retained=Mock();monkeypatch.setattr(routes,'companion_job_store',SimpleNamespace(put=retained))
    monkeypatch.setattr(companion_context,'mapping_context',AsyncMock(return_value={'status':'not_requested','evidence':[]}))
    monkeypatch.setattr(companion_context,'document_context',AsyncMock(return_value={'status':'no_evidence','evidence':[]}))
    seen=[];real=httpx.AsyncClient
    def handle(request):
        seen.append(request)
        if request.url.path.endswith('/semantic-evidence'):
            return httpx.Response(200,json={'ontology_id':'o','status':'not_checked'})
        return httpx.Response(200,json={'evidence_type':'business_answer','source':'graph-service:typed-business-read',
            'resource_id':'business-answer:fixture','intent':'parts_with_pmi','rows':[
                {'part':'Housing','part_id':returned_id,'pmi':'Diameter 5 mm','source':'o','prefix':'p',
                 'association':'Recorded typed association','association_status':'recorded_association'}]})
    monkeypatch.setattr(companion_context.httpx,'AsyncClient',lambda **kw:real(transport=httpx.MockTransport(handle),**kw))
    app=FastAPI();app.include_router(routes.router)
    app.dependency_overrides[original_authorization]=lambda:'reader'
    response=TestClient(app).post('/api/v1/chat',json={'message':'Does it have PMI?',
        'graph_context':{'ontology':'o','ontology_prefix':'p','page':'graph','node_id':'selected-id'}})
    assert response.status_code==200
    body=response.json();assert body['answerable'] is answerable
    reads=[request for request in seen if request.url.path.endswith('/business-answer')]
    assert len(reads)==1 and reads[0].url.params['node_id']=='selected-id'
    assert all(request.headers['authorization']=='Bearer read-fixture' for request in seen)
    stored=retained.call_args.args[1]
    assert stored['context_envelope']['scope']['node_id']=='selected-id'
    assert stored['graph_context']['node_id']=='selected-id'
    if answerable:assert '| Housing | Diameter 5 mm |' in body['response']
    else:assert 'could not verify' in body['response']
