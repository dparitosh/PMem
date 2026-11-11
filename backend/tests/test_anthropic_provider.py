import asyncio
import json
import os
from unittest.mock import patch

import httpx
import pytest

from backend.core import llm_providers as lp

KEY = 'sk-ant-test-key-1234567890'


@pytest.fixture
def anthropic_env():
    with patch.dict(os.environ, {'ANTHROPIC_API_KEY': KEY, 'ANTHROPIC_MODEL': 'claude-haiku-5-5'}, clear=False):
        yield


def test_anthropic_is_a_configurable_chat_provider_without_embeddings(anthropic_env):
    settings = lp.cloud_settings('anthropic')
    assert settings.base_url == 'https://api.anthropic.com/v1'
    assert settings.model == 'claude-haiku-5-5'
    assert 'sk-ant' not in repr(settings)
    with pytest.raises(ValueError, match='no embeddings API'):
        lp.cloud_settings('anthropic', embeddings=True)


def test_missing_anthropic_key_is_named_without_leaking_values(anthropic_env):
    with patch.dict(os.environ, {'ANTHROPIC_API_KEY': ''}):
        with pytest.raises(ValueError, match='ANTHROPIC_API_KEY'):
            lp.cloud_settings('anthropic')


def test_text_blocks_are_joined_and_truncation_is_refused():
    assert lp._anthropic_text({'stop_reason': 'end_turn', 'content': [{'type': 'text', 'text': 'Hello '}, {'type': 'text', 'text': 'world'}]}) == 'Hello world'
    with pytest.raises(lp.IncompleteProviderResponse):
        lp._anthropic_text({'stop_reason': 'max_tokens', 'content': [{'type': 'text', 'text': 'cut'}]})
    with pytest.raises(ValueError, match='Unsupported provider content block'):
        lp._anthropic_text({'stop_reason': 'end_turn', 'content': [{'type': 'tool_use', 'name': 'x'}]})


def test_system_prompt_is_a_separate_field_and_turns_start_with_user():
    system, turns = lp._anthropic_split([
        {'role': 'system', 'content': 'Be brief.'},
        {'role': 'assistant', 'content': 'earlier'},
        {'role': 'user', 'content': 'question'},
    ])
    assert system == 'Be brief.'
    assert turns[0] == {'role': 'user', 'content': 'Continue.'}
    assert turns[-1] == {'role': 'user', 'content': 'question'}


def test_post_cloud_chat_sends_messages_api_request_and_returns_pipeline_shape(anthropic_env):
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen['url'] = str(request.url)
        seen['headers'] = dict(request.headers)
        seen['body'] = json.loads(request.content)
        return httpx.Response(200, json={'stop_reason': 'end_turn', 'content': [{'type': 'text', 'text': 'answer'}]})

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await lp.post_cloud_chat(client, 'anthropic', {
                'messages': [{'role': 'system', 'content': 'Sys'}, {'role': 'user', 'content': 'Q'}],
                'options': {'num_predict': 64},
            })

    result = asyncio.run(run())
    assert result == {'done': True, 'message': {'content': 'answer', 'tool_calls': []}}
    assert seen['url'] == 'https://api.anthropic.com/v1/messages'
    assert seen['headers']['x-api-key'] == KEY
    assert seen['headers']['anthropic-version'] == lp.ANTHROPIC_VERSION
    assert seen['body']['system'] == 'Sys'
    assert seen['body']['max_tokens'] == 64
    assert seen['body']['messages'] == [{'role': 'user', 'content': 'Q'}]


def test_post_cloud_chat_refuses_tool_requests(anthropic_env):
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(500))) as client:
            return await lp.post_cloud_chat(client, 'anthropic', {'messages': [{'role': 'user', 'content': 'Q'}], 'tools': [{'type': 'function'}]})

    with pytest.raises(ValueError, match='tool calling is not enabled'):
        asyncio.run(run())


def test_langchain_adapter_converts_messages(anthropic_env):
    from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
    chat = lp.cloud_chat('anthropic')
    payload = chat._payload([SystemMessage(content='Sys'), HumanMessage(content='Hi'), AIMessage(content='Yo'), HumanMessage(content='Again')])
    assert payload['system'] == 'Sys'
    assert [m['role'] for m in payload['messages']] == ['user', 'assistant', 'user']
    assert chat._llm_type == 'anthropic'
