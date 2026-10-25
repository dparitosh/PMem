from pathlib import Path
from unittest.mock import Mock
import xml.etree.ElementTree as ET
import pytest

from backend.Services.xmi_validation import validate_xmi_root, local_reference
from backend.depo_platform.plm_questions import intent
from backend.agentic_service.business_answers import render
from backend.agentic_service.prompt_security import validate_summary
from backend.graph_service.plm_answers import retrieve


def test_magicdraw_snapshots_are_not_primary_model_identity_collisions():
    root=ET.fromstring('<x:XMI xmlns:x="http://www.omg.org/XMI"><Model x:id="one"/><x:Extension extender="MagicDraw UML 2021x"><filePart><Model x:id="one"/></filePart></x:Extension></x:XMI>')
    assert validate_xmi_root(root)['excluded_tool_file_parts']==1
    assert len(list(root.iter()))==3


def test_real_model_duplicates_still_fail():
    root=ET.fromstring('<x:XMI xmlns:x="http://www.omg.org/XMI"><Model x:id="one"/><Model x:id="one"/></x:XMI>')
    with pytest.raises(ValueError,match='Duplicate XMI identifier'):validate_xmi_root(root)


def test_standard_primitives_do_not_enable_network_or_arbitrary_external_models():
    assert local_reference('http://www.omg.org/spec/SysML/20181001/SysML.xmi#SysML_dataType.Real',standard_primitives=True)=='Real'
    with pytest.raises(ValueError):local_reference('http://evil.test/SysML.xmi#SysML_dataType.Real',standard_primitives=True)


def test_question_routing_separates_schema_and_business_instances():
    assert intent('Which parts have PMI?')=='parts_with_pmi'
    assert intent('Find product and assembly information with source references.')=='product_assembly'
    assert intent('Which ontology classes represent parts and PMI?')==''
    assert intent('Which parts are affected by this change?')==''


def test_unknown_pmi_ownership_is_a_useful_answer_not_schema_metadata():
    text=render([{'resource_id':'query-1','intent':'parts_with_pmi','rows':[]}])
    assert 'could not verify' in text
    assert 'PMI annotations alone' in text
    assert 'Matching graph resources' not in text


def test_source_trace_is_not_presented_as_pmi_ownership(monkeypatch):
    monkeypatch.delenv('DEPO_DATABASE_URL',raising=False);monkeypatch.delenv('DATABASE_URL',raising=False)
    publisher=Mock(_session_rows=Mock(return_value=[{'part':'Motor','part_id':'p','pmi':'Tolerance','pmi_id':'a',
        'relationship_id':'r','relationship':'TRACE_TO','predicate':None,'source':'selected'}]))
    result=retrieve(publisher,query='Which parts have PMI?',ontology_id='selected')
    assert result['rows'][0]['association']=='Source reference; ownership unverified'
    assert publisher._session_rows.call_args.kwargs['scope']=='selected'
    assert '| Part | PMI |' in render([result])


def test_factual_summary_table_rows_need_citations():
    validate_summary('| Part | Evidence |\n|---|---|\n| Motor | [evidence:p] |',['p'])
    with pytest.raises(ValueError,match='table row'):
        validate_summary('| Part | Evidence |\n|---|---|\n| Motor | [evidence:p] |\n| Invented | none |',['p'])


@pytest.mark.asyncio
async def test_business_reply_prefers_table_and_emits_one_answer(monkeypatch):
    import httpx
    from unittest.mock import AsyncMock
    from backend.agentic_service import companion, companion_context, local_llm
    monkeypatch.setenv('COMPANION_LLM_ENABLED','true')
    monkeypatch.setattr(companion_context,'mapping_context',AsyncMock(return_value={'status':'not_requested','evidence':[]}))
    monkeypatch.setattr(companion_context,'document_context',AsyncMock(return_value={'status':'no_evidence','evidence':[]}))
    monkeypatch.setattr(companion_context,'plm_context',AsyncMock(return_value={'evidence_type':'business_answer',
        'resource_id':'business-answer:test','intent':'product_assembly','label':'Product evidence','rows':[{'name':'Motor','kind':'Part','source':'selected'}],
        'source':'graph-service:typed-business-read'}))
    monkeypatch.setattr(local_llm,'summarize',AsyncMock(return_value='Motor is a retained part. [evidence:business-answer:test]'))
    real=httpx.AsyncClient
    monkeypatch.setattr(companion.httpx,'AsyncClient',lambda **kw:real(transport=httpx.MockTransport(lambda req:httpx.Response(200,json={'nodes':[],'relationships':[]})),**kw))
    messages=[]
    async def emit(text):messages.append(text)
    result=await companion.KnowledgeCompanion().ask('Find products',headers={},on_token=emit)
    assert result['response']=='Motor is a retained part. [evidence:business-answer:test]'
    assert messages==[result['response']]
    assert 'Matching graph resources' not in result['response']
