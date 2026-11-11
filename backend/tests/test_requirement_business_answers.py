from unittest.mock import AsyncMock, Mock
import pytest
from backend.depo_platform.plm_questions import intent, requirement_subject
from backend.graph_service.plm_answers import retrieve
from backend.agentic_service.business_answers import render

QUESTION = 'what are thee requirements specification associated with induction motor'


def test_customer_question_routes_to_instance_associations():
    assert intent(QUESTION) == 'associated_requirements'
    assert requirement_subject(QUESTION) == 'induction motor'
    assert intent('What ontology schema represents requirements for a motor?') == ''


def test_requirement_answer_uses_scoped_paths_and_business_table(monkeypatch):
    monkeypatch.delenv('DEPO_DATABASE_URL', raising=False)
    monkeypatch.delenv('DATABASE_URL', raising=False)
    publisher = Mock(_session_rows=Mock(return_value=[{'subject':'Motor', 'subject_id':'part-1',
        'requirement':'Motor speed requirement', 'requirement_id':'req-1', 'detail':'Rated speed 1500 rpm',
        'path':[{'id':'link-1','type':'HAS_REQUIREMENT'}], 'source':'plm', 'prefix':'splm'}]))
    result = retrieve(publisher, query=QUESTION, ontology_id='plm', ontology_prefix='splm')
    call = publisher._session_rows.call_args
    assert call.kwargs['subject'] == 'induction motor'
    assert call.kwargs['scope'] == 'plm' and call.kwargs['prefix'] == 'splm'
    assert 'nodes(path)' in call.args[0] and '$schema_types' in call.args[0]
    assert 'LIMIT 21' in call.args[0]
    text = render([result])
    assert '| Business object | Requirement / specification |' in text
    assert 'Motor speed requirement | Rated speed 1500 rpm' in text
    assert 'do not by themselves prove satisfaction' in text


def test_no_paths_does_not_substitute_schema_definitions(monkeypatch):
    monkeypatch.delenv('DEPO_DATABASE_URL', raising=False)
    monkeypatch.delenv('DATABASE_URL', raising=False)
    result = retrieve(Mock(_session_rows=Mock(return_value=[])), query=QUESTION)
    assert 'could not verify' in render([result])
    assert 'Matching graph resources' not in render([result])


def test_vocabulary_label_is_used_instead_of_relationship_code(monkeypatch):
    monkeypatch.delenv('DEPO_DATABASE_URL', raising=False)
    monkeypatch.delenv('DATABASE_URL', raising=False)
    rows = [{'subject':'Motor', 'requirement':'Speed requirement', 'detail':'<Description>Rated <Value>1500 rpm</Value></Description>',
             'path':[{'type':'HAS_REQUIREMENT','predicate':'https://example.test/hasRequirement'}]}]
    publisher = Mock(_session_rows=Mock(side_effect=[rows,[{'iri':'https://example.test/hasRequirement','label':'is governed by requirement','description':'Recorded requirement link'}]]))
    result = retrieve(publisher, query=QUESTION)
    text = render([result])
    assert 'is governed by requirement' in text and 'HAS_REQUIREMENT' not in text
    assert '1500 rpm' in text and '<Description>' not in text
    assert result['vocabulary'][0]['description'] == 'Recorded requirement link'


def test_serialized_property_values_render_as_business_text():
    from backend.agentic_service.business_answers import cell
    assert cell('{"name":"Speed","value":1500,"unit":"rpm"}') == 'Speed; 1500; rpm'
    assert cell('<UserValue value="1500 rpm"/>') == '1500 rpm'
    assert cell('Speed < 1600 rpm') == 'Speed < 1600 rpm'


@pytest.mark.parametrize('body', ['<Specification>metadata</Specification> [evidence:one]',
    '```json\n{"value":1500}\n``` [evidence:one]', 'Specification minOccurs=0 [evidence:one]'])
def test_model_serialization_is_rejected_before_display(body):
    from backend.agentic_service.prompt_security import validate_summary
    with pytest.raises(ValueError, match='business answers'):
        validate_summary(body,['one'])


@pytest.mark.asyncio
async def test_generic_business_read_excludes_legacy_schema_matches(monkeypatch):
    import httpx
    from backend.agentic_service import companion, companion_context
    monkeypatch.setattr(companion_context,'mapping_context',AsyncMock(return_value={'status':'not_requested','evidence':[]}))
    monkeypatch.setattr(companion_context,'document_context',AsyncMock(return_value={'status':'no_evidence','evidence':[]}))
    requests = []
    def reply(request):
        requests.append(request)
        return httpx.Response(200,json={'nodes':[{'elementId':'schema-property', 'labels':['OntologyResource'],
            'properties':{'kind':'objectproperty','label':'Specification','definition':'minOccurs=0','search_score':99}}], 'relationships':[]})
    real = httpx.AsyncClient
    monkeypatch.setattr(companion.httpx,'AsyncClient',lambda **kwargs:real(transport=httpx.MockTransport(reply),**kwargs))
    result = await companion.KnowledgeCompanion().ask('Details of the motor',headers={})
    assert result['answerable'] is False
    assert 'minOccurs' not in result['response'] and 'Specification' not in result['response']
    assert requests[0].url.params['business_only'] == 'true'


@pytest.mark.asyncio
async def test_unavailable_business_service_never_falls_back_to_word_matches(monkeypatch):
    from backend.agentic_service import companion, companion_context, local_llm
    monkeypatch.setattr(companion_context,'mapping_context',AsyncMock(return_value={'status':'not_requested','evidence':[]}))
    monkeypatch.setattr(companion_context,'document_context',AsyncMock(return_value={'status':'no_evidence','evidence':[]}))
    monkeypatch.setattr(companion_context,'plm_context',AsyncMock(side_effect=RuntimeError('unavailable')))
    summary = AsyncMock()
    monkeypatch.setattr(local_llm,'summarize',summary)
    monkeypatch.setenv('COMPANION_LLM_ENABLED','true')
    result = await companion.KnowledgeCompanion().ask(QUESTION, headers={})
    assert result['answerable'] is False and result['status'] == 'unavailable'
    assert result['evidence'] == []
    assert 'could not verify' in result['response']
    summary.assert_not_awaited()
