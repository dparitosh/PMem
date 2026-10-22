import asyncio
from unittest.mock import AsyncMock
import pytest
from pydantic import ValidationError
from backend.agentic_service.chat_request import ChatRequest
from backend.agentic_service import companion_context as context
from backend.agentic_service.companion_memory import retrieval_query


@pytest.mark.parametrize('page,path,key',[('catalog','/catalog/products','products'),('data-products','/data-products','products'),('data-flow','/pipeline/jobs/runs','runs')])
def test_page_uses_owning_read_service_and_discards_private_payloads(monkeypatch,page,path,key):
    read=AsyncMock(return_value=({key:[{'id':'item','name':'Example','status':'completed','execution_payload':{'password':'private'}}],'total':1},'http://owner/api/v1'+path))
    monkeypatch.setattr(context,'_read_json',read)
    result=asyncio.run(context.page_context('show records',page=page,headers={'Authorization':'Bearer reader'}))
    assert read.call_args.args[2]==path
    assert result['status']=='available'
    assert 'private' not in str(result)
    assert 'completed' in str(result)


def test_semantica_context_uses_existing_search_and_does_not_discard_scope(monkeypatch):
    read=AsyncMock(return_value=({'results':[{'node':{'id':'part','type':'Product','properties':{'content':'Motor','secret':'private'}}}]},'http://ontology/context'))
    monkeypatch.setattr(context,'_read_json',read)
    result=asyncio.run(context.page_context('motor',page='modeling',headers={}))
    assert 'Motor' in str(result) and 'private' not in str(result)
    assert read.call_args.args[2]=='/ontologies/business-context/search'
    read.reset_mock()
    result=asyncio.run(context.page_context('motor',page='modeling',headers={},ontology_id='specific-version'))
    assert result['status']=='not_requested'
    read.assert_not_called()


def test_page_is_a_validated_hint_and_history_does_not_cross_pages():
    with pytest.raises(ValidationError):ChatRequest(message='test',graph_context={'page':'https://untrusted'})
    assert retrieval_query('its status',[{'user_request':'Product','graph_context':{'page':'catalog'}}],{'page':'data-flow'})=='its status'


def test_unsupported_page_does_not_invent_a_service_connector(monkeypatch):
    read=AsyncMock();monkeypatch.setattr(context,'_read_json',read)
    assert asyncio.run(context.page_context('status',page='admin',headers={}))['status']=='not_requested'
    read.assert_not_called()
