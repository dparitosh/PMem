"""AOI gateway contracts without importing vendor code or using customer credentials."""
import asyncio
import hashlib
import importlib.util
import json
import os
import threading
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from fastapi.testclient import TestClient
import httpx
import pytest

from backend.aoi_gateway.app import create_app
from backend.aoi_gateway.settings import Settings
from backend.aoi_gateway.vendor import prepare, verify
from backend.aoi_gateway.worker import GatewayFailure, Worker, _completion
from backend.core.llm_providers import cloud_settings, post_cloud_chat, embedding_identity

TOKEN = 'gateway-fixture-token-32-characters-long'


def settings(tmp_path):
    return Settings(token=TOKEN, vendor_dir=tmp_path, username='fixture', password='fixture',
                    deployment='fixture-chat', embedding_deployment='fixture-embed', embedding_dimensions=2)


@pytest.fixture
def gateway(tmp_path):
    manager = Mock(execute=AsyncMock(return_value={'content': 'Grounded answer', 'finish_reason': 'stop'}))
    with TestClient(create_app(settings(tmp_path), manager)) as client:
        yield client, manager


def headers():
    return {'Authorization': 'Bearer '+TOKEN}


def body(**overrides):
    return {'model': 'aoi-chat', 'messages': [{'role': 'user', 'content': 'Find the part'}], **overrides}


def test_authentication_precedes_wrapper_execution(gateway):
    client, manager = gateway
    assert client.post('/v1/chat/completions', json=body()).status_code == 401
    assert client.get('/readyz').status_code == 401
    assert client.get('/healthz').json()['inference_verified'] is False
    manager.execute.assert_not_called()


def test_chat_preserves_roles_and_completions(gateway):
    client, manager = gateway
    response = client.post('/v1/chat/completions', json=body(), headers=headers())
    assert response.status_code == 200
    assert response.json()['choices'][0]['finish_reason'] == 'stop'
    args = manager.execute.call_args.args
    assert args[0] == 'chat' and args[1]['messages'][0]['role'] == 'user'
    assert client.post('/v1/chat/completions', json=body(model='unconfigured'), headers=headers()).status_code == 404


@pytest.mark.parametrize('extra,code', [({'tools': [{'type': 'function'}]},501), ({'stream':True},422),
    ({'response_format':{'type':'json_schema'}},501)])
def test_unsupported_capabilities_fail_explicitly(gateway, extra, code):
    client, manager = gateway
    assert client.post('/v1/chat/completions', json=body(**extra), headers=headers()).status_code == code
    manager.execute.assert_not_called()


def test_json_mode_checks_actual_output(gateway):
    client, manager = gateway
    response = client.post('/v1/chat/completions', json=body(response_format={'type':'json_object'}), headers=headers())
    assert response.status_code == 502
    manager.execute.return_value = {'content': '{"ok":true}', 'finish_reason': 'stop'}
    assert client.post('/v1/chat/completions', json=body(response_format={'type':'json_object'}), headers=headers()).status_code == 200


def test_request_body_and_embedding_limits(gateway):
    client, manager = gateway
    response = client.post('/v1/chat/completions', content=json.dumps(body(messages=[{'role':'user','content':'x'*140000}])),
                           headers={**headers(),'Content-Type':'application/json'})
    assert response.status_code == 413
    assert client.post('/v1/embeddings',json={'model':'aoi-embedding','input':['x']*33},headers=headers()).status_code == 422
    assert client.post('/v1/embeddings',json={'model':'aoi-embedding','input':'x','dimensions':1536},headers=headers()).status_code == 422
    manager.execute.assert_not_called()


def test_embedding_response_is_openai_compatible(gateway):
    client, manager = gateway
    manager.execute.return_value = [[.1,.2],[.3,.4]]
    response=client.post('/v1/embeddings',json={'model':'aoi-embedding','input':['a','b'],'dimensions':2},headers=headers())
    assert response.status_code==200
    assert [item['index'] for item in response.json()['data']]==[0,1]


def test_upstream_errors_do_not_expose_credentials(gateway):
    client, manager=gateway
    manager.execute.side_effect=GatewayFailure(502,'aoi_request_failed')
    response=client.post('/v1/chat/completions',json=body(),headers=headers())
    assert response.status_code==502 and TOKEN not in response.text
    assert response.json()=={'detail':'aoi_request_failed'}


def test_no_completion_marker_is_not_fabricated():
    assert _completion('Answer')['finish_reason']=='unknown'
    response=SimpleNamespace(message=SimpleNamespace(content='Part'),raw={'choices':[{'finish_reason':'length'}]})
    assert _completion(response)['finish_reason']=='length'


def test_vendor_copy_is_exact_and_source_unchanged(tmp_path):
    source=tmp_path/'iif';target=tmp_path/'gateway'
    (source/'sample_package').mkdir(parents=True);(source/'lib').mkdir()
    (source/'sample_package/CustomAOI_helper.py').write_text('# vendor fixture\n')
    for name in ('CustomAOI','CustomAOI_Core'):
        (source/f'lib/{name}.cpython-312.pyc').write_bytes(importlib.util.MAGIC_NUMBER+b'fixture')
    before={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in source.rglob('*') if p.is_file()}
    prepare(source,target);verify(target)
    assert before=={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in source.rglob('*') if p.is_file()}
    with pytest.raises(ValueError):prepare(source,source/'private')
    (target/'CustomAOI_helper.py').write_text('# changed')
    with pytest.raises(ValueError):verify(target)


@pytest.mark.asyncio
async def test_busy_worker_rejects_parallel_calls_and_configuration_is_explicit(tmp_path):
    worker=Worker(settings(tmp_path))
    await worker.lock.acquire()
    try:
        with pytest.raises(GatewayFailure) as error:await worker.execute('ready')
        assert error.value.status==429
    finally:worker.lock.release()
    missing=Worker(Settings(token=TOKEN,vendor_dir=tmp_path))
    with pytest.raises(GatewayFailure) as error:await missing.execute('ready')
    assert error.value.status==503


def test_worker_timeout_terminates_before_slot_reuse(tmp_path):
    process=Mock();process.is_alive.return_value=True
    pipe=Mock();pipe.poll.return_value=False
    context=Mock();context.Pipe.return_value=(pipe,Mock());context.Process.return_value=process
    worker=Worker(settings(tmp_path),context)
    with pytest.raises(GatewayFailure) as error:worker._call('chat',{})
    assert error.value.status==504
    process.terminate.assert_called_once();process.kill.assert_called_once()
    assert worker.process is None and worker.pipe is None


AOI_ENV={'USE_LLM':'aoi','AOI_MODEL':'aoi-chat','AOI_EMBED_MODEL':'aoi-embedding',
         'AOI_GATEWAY_TOKEN':TOKEN,'AOI_BASE_URL':'http://127.0.0.1:8020/v1','EMBEDDING_VECTOR_DIMENSIONS':'2'}


def test_pmem_aoi_settings_are_explicit_and_isolated():
    with patch.dict(os.environ,AOI_ENV,clear=True):
        assert cloud_settings('aoi').api_key==TOKEN
        assert TOKEN not in repr(cloud_settings('aoi'))
        assert '"provider": "aoi"' in embedding_identity()
        with pytest.raises(ValueError):cloud_settings('aoi',unstructured=True)
    with patch.dict(os.environ,{**AOI_ENV,'AOI_BASE_URL':'http://10.0.2.16:8020/v1'},clear=True):
        with pytest.raises(ValueError,match='HTTPS'):cloud_settings('aoi')


@pytest.mark.asyncio
async def test_pmem_calls_gateway_instead_of_cloud(gateway):
    from backend.agentic_service.local_llm import failure_status
    captured=[]
    async def handler(request):
        captured.append(request)
        return httpx.Response(200,json={'choices':[{'finish_reason':'stop','message':{'content':'Part'}}]})
    with patch.dict(os.environ,AOI_ENV,clear=True), httpx.MockTransport(handler) as transport:
        async with httpx.AsyncClient(transport=transport) as client:
            result=await post_cloud_chat(client,'aoi',{'messages':[{'role':'user','content':'Find a part'}]})
    assert result['done'] is True and len(captured)==1
    assert captured[0].url.host=='127.0.0.1'
    assert captured[0].headers['authorization']=='Bearer '+TOKEN
    exc=httpx.HTTPStatusError('unsupported',request=captured[0],response=httpx.Response(501))
    assert failure_status(exc)=='capability_unsupported'


@pytest.mark.asyncio
async def test_pmem_chat_reaches_gateway_contract(tmp_path):
    manager=Mock(execute=AsyncMock(return_value={'content':'Verified part evidence','finish_reason':'stop'}))
    transport=httpx.ASGITransport(app=create_app(settings(tmp_path),manager))
    with patch.dict(os.environ,AOI_ENV,clear=True):
        async with httpx.AsyncClient(transport=transport) as client:
            result=await post_cloud_chat(client,'aoi',{'messages':[{'role':'user','content':'Which part has PMI?'}]})
    assert result['done'] is True
    assert 'Verified part evidence' in str(result)
    manager.execute.assert_awaited_once()


def test_invalid_temperature_does_not_echo_prompt(gateway):
    client,manager=gateway
    response=client.post('/v1/chat/completions',headers=headers(),content=json.dumps(body(temperature=float('nan'))))
    assert response.status_code==422
    assert 'Find the part' not in response.text
    manager.execute.assert_not_called()


@pytest.mark.asyncio
async def test_repeated_cancellation_retains_worker_slot(tmp_path):
    worker=Worker(settings(tmp_path))
    started=threading.Event()
    release=threading.Event()
    def call(*args):
        started.set()
        release.wait(5)
        return {'content':'done'}
    worker._call=call
    task=asyncio.create_task(worker.execute('chat'))
    try:
        assert await asyncio.to_thread(started.wait,2)
        task.cancel()
        await asyncio.sleep(0)
        task.cancel()
        await asyncio.sleep(0)
        assert worker.lock.locked()
        with pytest.raises(GatewayFailure) as error:
            await worker.execute('chat')
        assert error.value.status==429
    finally:
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert not worker.lock.locked()


@pytest.mark.asyncio
async def test_langchain_chat_and_embedding_requests_match_gateway(tmp_path):
    from backend.core.llm_providers import cloud_chat,cloud_embeddings
    manager=Mock(execute=AsyncMock())
    app=create_app(settings(tmp_path),manager)
    with patch.dict(os.environ,AOI_ENV,clear=True):
        chat=cloud_chat('aoi')
        embeddings=cloud_embeddings('aoi')
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app)) as client:
            # SDK-created HTTP clients normally use the real network; replace
            # their transports to exercise serialization without credentials.
            chat.root_async_client._client=client
            manager.execute.return_value={'content':'Part with PMI','finish_reason':'stop'}
            answer=await chat.ainvoke('Which part has PMI?')
            assert answer.content=='Part with PMI'
            embeddings.async_client._client._client=client
            manager.execute.return_value=[[0.25,0.75]]
            assert await embeddings.aembed_query('Part')==[0.25,0.75]
