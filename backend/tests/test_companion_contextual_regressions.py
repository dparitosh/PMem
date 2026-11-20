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


@pytest.mark.parametrize('selected_id,returned_id,answerable',[('selected-id','selected-id',True),('selected-id','foreign-id',False),('new-selection','new-selection',True),('', 'recalled-id', True),('', 'wrong-recalled-id', False)])
def test_http_chat_round_trip_preserves_selected_identity_and_retains_the_validated_answer(monkeypatch, selected_id, returned_id, answerable):
    from types import SimpleNamespace
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from backend.agentic_service import router as routes
    monkeypatch.setenv('COMPANION_LLM_ENABLED','false')
    async def io(fn,*args,**kwargs):return fn(*args,**kwargs)
    original_authorization=routes.graph_read_identity
    monkeypatch.setattr(routes,'graph_read_identity',lambda _: 'reader')
    monkeypatch.setattr(routes,'_agent_io',io)
    selected_scope={'ontology':'o','ontology_prefix':'p','page':'graph','node_id':selected_id}
    history={'user_request':'Show product details for Housing.', 'resolved_query':'Show product details for Housing.',
             'answerable':True, 'graph_context':selected_scope,
             'retrieval':{'grounding':{'resolved_identity':{'resource_id':'recalled-id','ontology_id':'o','ontology_prefix':'p','label':'Housing'}}}}
    monkeypatch.setattr(routes,'_session_turns',lambda *_:[history])
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
        'graph_context':{'ontology':'o','ontology_prefix':'p','page':'graph','node_id':selected_id}})
    assert response.status_code==200
    body=response.json();assert body['answerable'] is answerable
    reads=[request for request in seen if request.url.path.endswith('/business-answer')]
    assert len(reads)==1 and reads[0].url.params['node_id']==(selected_id or 'recalled-id')
    assert 'requirements' not in reads[0].url.params.get('query', '').lower()
    assert all(request.headers['authorization']=='Bearer read-fixture' for request in seen)
    stored=retained.call_args.args[1]
    assert stored['context_envelope']['scope'].get('node_id','')==selected_id
    assert stored['graph_context']['node_id']==selected_id
    if answerable:
        assert '| Housing | Diameter 5 mm |' in body['response']
        assert stored['retrieval']['grounding']['resolved_identity']['resource_id']==returned_id
    else:assert 'could not verify' in body['response']


def test_selected_model_attribute_followup_does_not_become_product_requirements(monkeypatch):
    from backend.agentic_service import companion_memory
    recall = Mock(side_effect=AssertionError('Selected identity needs no text-based subject substitution'))
    monkeypatch.setattr(companion_memory, 'recall_turns', recall)
    scope = {'page':'modeling', 'node_id':'requirement-47', 'ontology':'model'}
    assert companion_memory.retrieval_query('And its requirement number?', [], scope) == 'And its requirement number?'
    recall.assert_not_called()


def test_long_this_part_followup_preserves_scoped_subject():
    from backend.agentic_service.companion_memory import retrieval_query
    question = 'What geometry and PMI tolerances are recorded for this part?'
    turns = [{'user_request': 'Show product details for Housing.', 'graph_context': {'page': 'graph'}}]
    assert retrieval_query(question, turns, {'page': 'graph'}) == 'What geometry and PMI tolerances are recorded for Housing?'
    assert retrieval_query(question, turns, {'page': 'home'}) == question


def test_instance_details_retains_requested_values_without_description():
    from backend.agentic_service.business_answers import instance_details
    text = instance_details({'partNumber': '684', 'revision': 'B', 'geometryType': 'Solid',
                             'measuredValue': 0, 'verificationStatus': False, 'unit': 'mm'})
    for expected in ('684', 'B', 'Solid', '0', 'False', 'mm'):
        assert expected in text
    assert 'Not recorded' not in text
    assert instance_details({}) == ''


@pytest.mark.parametrize('node', [
    {'properties': {'kind': 'class'}},
    {'labels': ['OntologyPublication'], 'properties': {}},
    {'properties': {'rdf_types': ['http://www.w3.org/2002/07/owl#Class']}},
    {'properties': {'rdf_types': ['http://www.w3.org/1999/02/22-rdf-syntax-ns#Property']}},
])
def test_schema_and_infrastructure_are_not_business_results(node):
    assert not companion.is_business_result(node)


def test_typed_part_is_a_business_result():
    assert companion.is_business_result({'properties': {
        'rdf_types': ['https://depo.example.org/ceim/0.1/Part'], 'partNumber': '684'}})



def test_same_name_master_references_are_distinct_and_aliases_deduplicated():
    from backend.agentic_service.business_answers import render_instance_connections
    rows = [
        {'evidence_type': 'graph_resource', 'resource_id': 'revision', 'label': 'mBOM_Rotor Shaft', 'properties': {'revision': 'A'}},
        {'evidence_type': 'graph_resource', 'resource_id': 'master', 'label': 'mBOM_Rotor Shaft', 'properties': {'part_number': '684'}},
        *[{'evidence_type': 'graph_relationship', 'source_id': 'revision', 'target_id': 'master', 'relationship': relation}
          for relation in ('MASTER_REF', 'MASTERREF')],
        {'evidence_type': 'graph_relationship', 'source_id': 'revision', 'target_id': 'master', 'relationship': 'https://unknown/relation'},
    ]
    text = render_instance_connections(rows)
    assert text.count('References source master record') == 1
    assert 'mBOM_Rotor Shaft (A, source record 1)' in text
    assert 'mBOM_Rotor Shaft (684, source record 2)' in text
    assert 'Source-record references' in text
    assert 'Business relationships' not in text
    assert 'Recorded connection' not in text
    assert '[evidence:revision] [evidence:master]' in text
    assert text.splitlines()[-1].endswith(' |')


def test_business_projection_preserves_direct_instance_values_and_excludes_secrets():
    from backend.graph_service.search_evidence import search_properties
    from backend.graph_service.query_repository import LEGACY_SEARCH, ONTOLOGY_SEARCH_NODES
    projected = search_properties({'business_properties': {'part_number': '684', 'revision': 'A', 'mass': 0, 'password': 'hidden'}})
    assert projected['part_number'] == '684'
    assert projected['mass'] == '0'
    assert 'password' not in projected
    for query in (LEGACY_SEARCH, ONTOLOGY_SEARCH_NODES):
        assert '.part_number' in query and '.revision' in query
        assert 'AS business_properties' in query
        assert '.password' not in query


@pytest.mark.parametrize('question, expected', [
    ('Show the recorded part number, revision and description for mBOM_Rotor Shaft. Cite source records.', 'mBOM_Rotor Shaft'),
    ('What geometry and PMI tolerances are recorded for this part?', ''),
    ('Show the recorded revision for Rotor Shaft Machined.', 'Rotor Shaft Machined'),
    ('Explain ontology mappings for Housing.', ''),
])
def test_explicit_property_subject_does_not_include_instructions(question, expected):
    from backend.depo_platform.plm_questions import property_subject
    assert property_subject(question) == expected


@pytest.mark.asyncio
async def test_explicit_named_instance_does_not_return_partial_word_matches(monkeypatch):
    monkeypatch.setenv('COMPANION_LLM_ENABLED', 'false')
    monkeypatch.setattr(companion_context, 'mapping_context', AsyncMock(return_value={'status':'not_requested','evidence':[]}))
    monkeypatch.setattr(companion_context, 'document_context', AsyncMock(return_value={'status':'no_evidence','evidence':[]}))
    graph = {'nodes': [
        {'elementId':'unrelated','properties':{'label':'Rotor','modelType':'Block','search_score':20}},
        {'elementId':'assembly','properties':{'label':'mBOM_Rotor Shaft assembly','description':'Assembly','search_score':20}},
        {'elementId':'correct','properties':{'label':'mBOM_Rotor Shaft','revision':'A','part_number':'684','search_score':5}},
    ], 'relationships':[]}
    requests=[]
    def transport(request):
        requests.append(request)
        return httpx.Response(200,json=graph)
    real=httpx.AsyncClient
    monkeypatch.setattr(companion.httpx,'AsyncClient',lambda **kw:real(transport=httpx.MockTransport(transport),**kw))
    result=await companion.KnowledgeCompanion().ask('Show part number and revision for mBOM_Rotor Shaft. Cite source records.',headers={})
    assert requests[0].url.params['query']=='mBOM_Rotor Shaft'
    assert [item['resource_id'] for item in result['evidence'] if item['evidence_type']=='graph_resource']==['correct']
    assert '684' in result['response'] and 'Revision: A' in result['response']
    assert 'Block' not in result['response']


def test_typed_grounding_retains_part_and_pmi_without_inventing_a_selection():
    from backend.agentic_service.companion_memory import evidence_grounding
    evidence=[{'evidence_type':'business_answer','intent':'parts_with_pmi', 'rows':[
        {'part_id':'part-A','part':'Bearing A','pmi_id':'pmi-A','pmi':'Bore 25 mm',
         'source':'bearing-v1','publication_revision':'publication-1','relationship_id':'edge-A'}]}]
    assert evidence_grounding(evidence)['resolved_identity'] is None  # matching PMI rows alone cannot resolve a name
    grounding=evidence_grounding(evidence,root_id='part-A')
    assert {(r['resource_id'],r['ontology_id']) for r in grounding['resources']}=={('part-A','bearing-v1'),('pmi-A','bearing-v1')}
    assert grounding['resolved_identity']['resource_id']=='part-A'
    assert grounding['resolved_identity']['publication_revision']=='publication-1'
    assert grounding['relationship_ids']==['edge-A']
    assert grounding['semantic_entailment_verified'] is False


def test_ambiguous_or_truncated_business_reads_never_resolve_a_unique_identity():
    from backend.agentic_service.companion_memory import evidence_grounding
    item={'evidence_type':'business_answer','intent':'product_assembly','rows':[
        {'node_id':'a','name':'Bearing','source':'v1'},{'node_id':'b','name':'Bearing','source':'v2'}]}
    assert evidence_grounding([item])['resolved_identity'] is None
    item['rows']=item['rows'][:1];item['coverage']={'has_more':True}
    assert evidence_grounding([item])['resolved_identity'] is None


def test_pronoun_followup_reloads_exact_observed_identity_and_preserves_search_scope():
    from backend.agentic_service.companion_memory import followup_context
    scope={'page':'home'}
    turn={'graph_context':scope,'answerable':True,'retrieval':{'grounding':{'resolved_identity':
        {'resource_id':'bearing-A','ontology_id':'release-1','label':'Bearing A'}}}}
    selected=followup_context('What PMI is recorded for it?', [turn], scope)
    assert selected['node_id']=='bearing-A' and selected['ontology']=='release-1'
    assert scope=={'page':'home'}
    assert followup_context('Show PMI for Shaft.',[turn],scope)==scope
    assert followup_context('What PMI is recorded for it?',[turn],{'page':'home','ontology':'release-2'})=={'page':'home','ontology':'release-2'}
    assert followup_context('What PMI is recorded for it?',[turn],{'page':'home','node_id':'new'})['node_id']=='new'


def test_unresolved_latest_turn_cannot_reuse_an_older_resolved_subject():
    from backend.agentic_service.companion_memory import followup_context
    scope={'page':'home'}
    older={'graph_context':scope,'answerable':True,'retrieval':{'grounding':{'resolved_identity':
        {'resource_id':'a','ontology_id':'v1'}}}}
    assert followup_context('What PMI is recorded for it?', [{'graph_context':scope,'answerable':True},older], scope)==scope


@pytest.mark.asyncio
async def test_unknown_explicit_part_cannot_be_answered_from_unrelated_excerpts(monkeypatch):
    from backend.agentic_service import local_llm
    monkeypatch.setenv('COMPANION_LLM_ENABLED','true')
    monkeypatch.setattr(companion_context,'mapping_context',AsyncMock(return_value={'status':'not_requested','evidence':[]}))
    monkeypatch.setattr(companion_context,'document_context',AsyncMock(return_value={'status':'available','evidence':[
        {'evidence_type':'document_excerpt','resource_id':'old','label':'Old bearing note','description':'Bearing steel','source':'fixture'}]}))
    real=httpx.AsyncClient
    monkeypatch.setattr(companion.httpx,'AsyncClient',lambda **kw:real(transport=httpx.MockTransport(lambda _:httpx.Response(200,json={'nodes':[],'relationships':[]})),**kw))
    summary=AsyncMock();monkeypatch.setattr(local_llm,'summarize',summary)
    result=await companion.KnowledgeCompanion().ask('Show the recorded part number and revision for NO-SUCH-PART-99999.',headers={})
    assert result['status']=='unresolved_identity' and result['answerable'] is False
    assert 'NO-SUCH-PART-99999' in result['response']
    assert result['evidence']==[] and result['retrieval']['context_invalidated'] is True
    summary.assert_not_called()


def test_unknown_new_subject_blocks_old_subject_recall_but_not_a_new_explicit_selection():
    from backend.agentic_service.companion_memory import retrieval_query,followup_context,followup_needs_subject
    scope={'page':'home'}
    turns=[{'user_request':'NO-SUCH-PART-99999','answerable':False,'graph_context':scope,
            'retrieval':{'context_invalidated':True}},
           {'user_request':'Show product details for Bearing A.','answerable':True,'graph_context':scope,
            'retrieval':{'grounding':{'resolved_identity':{'resource_id':'bearing-A','ontology_id':'v1'}}}}]
    question='What PMI values are recorded for it?'
    assert retrieval_query(question,turns,scope)==question
    assert followup_context(question,turns,scope)==scope
    assert followup_needs_subject(question,turns,scope)
    assert not followup_needs_subject('Show PMI for Shaft.',turns,scope)
    assert not followup_needs_subject(question,turns,{'page':'home','node_id':'new'})


@pytest.mark.asyncio
async def test_named_product_inventory_miss_also_invalidates_old_subject(monkeypatch):
    monkeypatch.setattr(companion_context,'mapping_context',AsyncMock(return_value={'status':'not_requested','evidence':[]}))
    monkeypatch.setattr(companion_context,'document_context',AsyncMock(return_value={'status':'no_evidence','evidence':[]}))
    monkeypatch.setattr(companion_context,'plm_context',AsyncMock(return_value={
        'evidence_type':'business_answer','resource_id':'business-answer:empty','intent':'product_assembly',
        'label':'Business evidence','rows':[],'source':'graph-service:typed-business-read'}))
    result=await companion.KnowledgeCompanion().ask('Show product details for NO-SUCH-PART-99999.',headers={})
    assert result['status']=='unresolved_identity' and result['retrieval']['context_invalidated']


def test_http_orphan_followup_never_calls_graph_or_model_and_retains_clarification(monkeypatch):
    from types import SimpleNamespace
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from backend.agentic_service import router as routes
    monkeypatch.setenv('COMPANION_LLM_ENABLED','false')
    async def io(fn,*args,**kwargs):return fn(*args,**kwargs)
    auth=routes.graph_read_identity
    monkeypatch.setattr(routes,'graph_read_identity',lambda _: 'reader')
    monkeypatch.setattr(routes,'_agent_io',io)
    def turns(session,limit,scope,successful_only):
        assert successful_only is False
        return [{'graph_context':{'page':'home'},'answerable':False,'retrieval':{'context_invalidated':True}}]
    monkeypatch.setattr(routes,'_session_turns',turns)
    monkeypatch.setattr(routes,'downstream_headers',lambda *a,**k:{'Authorization':'Bearer read-fixture'})
    monkeypatch.setattr(routes,'sessions',SimpleNamespace(open_session=lambda *_:{'session_id':'s','owner':'reader','expires_at':'2030-01-01T00:00:00+00:00'},memory_id=lambda _:'m',owner=lambda *_:'reader'))
    monkeypatch.setattr(routes,'telemetry',SimpleNamespace(start=lambda **_:({'run_id':'r'},0)))
    monkeypatch.setattr(routes,'_finish_observation',lambda *a,**k:None)
    monkeypatch.setattr(routes,'AgentMemoryService',SimpleNamespace(enabled=lambda:False))
    retained=Mock();monkeypatch.setattr(routes,'companion_job_store',SimpleNamespace(put=retained))
    ask=AsyncMock(side_effect=AssertionError('Orphan pronoun must not start retrieval'))
    monkeypatch.setattr(routes.companion,'ask',ask)
    app=FastAPI();app.include_router(routes.router);app.dependency_overrides[auth]=lambda:'reader'
    response=TestClient(app).post('/api/v1/chat',json={'message':'What PMI is recorded for it?','graph_context':{'page':'home'}})
    assert response.status_code==200 and response.json()['status']=='needs_subject'
    assert response.json()['answerable'] is False
    assert retained.call_args.args[1]['retrieval']['context_invalidated'] is True
    ask.assert_not_called()


def test_initial_pronoun_without_a_selected_or_retained_subject_requires_clarification():
    from backend.agentic_service.companion_memory import followup_needs_subject
    assert followup_needs_subject('What PMI is recorded for it?',[],{'page':'home'})
    assert not followup_needs_subject('Show PMI for Bearing A.',[],{'page':'home'})


@pytest.mark.parametrize('question', [
    'For IM-1500 bearing investigation INV-2026-031, compare options A, B, C and D.',
    'Compare the test results for the recorded alternatives.',
    'Show details for the selected part and then recommend an alternative.',
])
def test_decision_tasks_are_not_misread_as_exact_property_subjects(question):
    from backend.depo_platform.plm_questions import property_subject
    assert property_subject(question) == ''


@pytest.mark.asyncio
async def test_selected_graph_record_does_not_inherit_unrelated_page_inventory(monkeypatch):
    monkeypatch.setenv('COMPANION_LLM_ENABLED','false')
    monkeypatch.setattr(companion_context,'mapping_context',AsyncMock(return_value={'status':'not_requested','evidence':[]}))
    monkeypatch.setattr(companion_context,'document_context',AsyncMock(return_value={'status':'no_evidence','evidence':[]}))
    page_read=AsyncMock()
    monkeypatch.setattr(companion_context,'page_context',page_read)
    graph={'nodes':[{'elementId':'selected','labels':['OntologyResource'],'properties':{
        'label':'Bearing investigation','rdf_types':['https://depo.example.org/ceim/0.1/Document'],
        'description':'Recorded bearing finding'}}], 'relationships':[], 'inclusion':{}, 'view':{'truncated':False}}
    monkeypatch.setattr(companion_context,'business_context',AsyncMock(return_value=(graph,'graph-service:selected-context')))
    result=await companion.KnowledgeCompanion().ask('Show the selected investigation finding.',headers={},page='graph',node_id='selected')
    page_read.assert_not_awaited()
    assert 'Recorded bearing finding' in result['response']
    assert '0 business objects' not in result['response']
    assert 'PostgreSQL-backed semantic analysis' not in result['response']
