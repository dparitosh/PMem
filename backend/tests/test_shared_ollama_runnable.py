"""Actual LangChain composition over the bounded native APIM transport."""
import asyncio
import json
from datetime import datetime,timedelta,timezone
import httpx
import pytest
from langchain_core.runnables import RunnableLambda
from backend.core.ollama_runnable import OllamaRestRunnable,prompt_messages,native_content
from backend.depo_platform.operations import OperationContext,operation_scope


@pytest.mark.parametrize('operation',['chat','generate'])
def test_exact_gateway_url_headers_payload_and_langchain_composition(operation):
    endpoint='https://gateway.example/ollama-clone/custom-'+operation
    seen=[]
    def handle(request):
        seen.append(request)
        return httpx.Response(200,json={'done':True,'message':{'content':'OK'},'response':'OK'})
    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
            model=OllamaRestRunnable(endpoint=endpoint,headers={'api-key':'fixture-key'},client=client)
            chain=model | RunnableLambda(lambda result:native_content(result,operation))
            body={'model':'fixture','stream':False,'messages':prompt_messages('Literal {policy}', 'Evidence {value}')} if operation=='chat' else {'model':'fixture','stream':False,'system':'policy','prompt':'evidence'}
            assert await chain.ainvoke(body)=='OK'
            assert str(seen[0].url)==endpoint
            assert seen[0].headers['api-key']=='fixture-key'
            assert json.loads(seen[0].content)==body
            assert len(seen)==1
    asyncio.run(scenario())


def test_structured_and_native_tool_fields_are_preserved():
    schema={'type':'object','properties':{'ok':{'type':'boolean'}}}
    body={'model':'fixture','stream':False,'format':schema,'tools':[{'type':'function','function':{'name':'inspect','parameters':schema}}],'messages':prompt_messages('policy','data')}
    async def scenario():
        def handle(request):
            assert json.loads(request.content)==body
            return httpx.Response(200,json={'done':True,'message':{'tool_calls':[{'function':{'name':'inspect','arguments':{'ok':True}}}]}})
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
            result=await OllamaRestRunnable(endpoint='https://gateway.example/chat',headers={},client=client).ainvoke(body)
        assert result['message']['tool_calls'][0]['function']['arguments']=={'ok':True}
    asyncio.run(scenario())


def test_bounded_response_is_checked_before_json_decode(monkeypatch):
    monkeypatch.setenv('AGENTIC_MAX_RESPONSE_BYTES','20')
    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request:httpx.Response(200,content=b'x'*21))) as client:
            with pytest.raises(ValueError,match='byte limit'):
                await OllamaRestRunnable(endpoint='https://gateway.example/large',headers={},client=client).ainvoke({'model':'fixture','stream':False})
    asyncio.run(scenario())


def test_slow_stream_obeys_operation_deadline():
    class Body(httpx.AsyncByteStream):
        async def __aiter__(self):
            for _ in range(50):
                await asyncio.sleep(.02)
                yield b'{"message":{"content":"x"},"done":false}\n'
    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request:httpx.Response(200,stream=Body()))) as client:
            model=OllamaRestRunnable(endpoint='https://gateway.example/slow',headers={},client=client)
            deadline=(datetime.now(timezone.utc)+timedelta(seconds=.07)).isoformat()
            with operation_scope(OperationContext('slow',deadline)),pytest.raises(TimeoutError):
                async for _ in model.astream({'model':'fixture','stream':True}): pass
    asyncio.run(scenario())


def test_incomplete_stream_is_rejected_and_split_unicode_is_preserved():
    class Body(httpx.AsyncByteStream):
        def __init__(self,complete): self.complete=complete
        async def __aiter__(self):
            data=json.dumps({'message':{'content':'café'},'done':self.complete},ensure_ascii=False).encode()+b'\n'
            for byte in data: yield bytes([byte])
    async def scenario():
        for complete in (True,False):
            async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request:httpx.Response(200,stream=Body(complete)))) as client:
                stream=OllamaRestRunnable(endpoint='https://gateway.example/unicode',headers={},client=client).astream({'model':'fixture','stream':True})
                if complete:
                    rows=[row async for row in stream]
                    assert rows[0]['message']['content']=='café'
                else:
                    with pytest.raises(ValueError,match='completion'):
                        async for _ in stream: pass
    asyncio.run(scenario())


def test_prompt_values_are_literal_and_preserve_roles():
    assert prompt_messages('Policy {unchanged}', '{"evidence":"{not_a_variable}"}')==[
        {'role':'system','content':'Policy {unchanged}'},
        {'role':'user','content':'{"evidence":"{not_a_variable}"}'}]


def test_optional_runtime_load_does_not_block_or_cancel_other_callers(monkeypatch):
    import threading
    from types import SimpleNamespace
    from backend.core import llm_runtime
    release=threading.Event(); started=threading.Event(); calls=[]
    module=SimpleNamespace(name='loaded')
    original=llm_runtime.importlib.import_module
    def load(name):
        if name!='backend.core.ollama_runnable': return original(name)
        calls.append(name); started.set()
        assert release.wait(3)
        return module
    monkeypatch.setattr(llm_runtime,'_loaded',None)
    monkeypatch.setattr(llm_runtime.importlib,'import_module',load)
    async def scenario():
        first=second=None
        try:
            expired=(datetime.now(timezone.utc)+timedelta(seconds=.02)).isoformat()
            with operation_scope(OperationContext('expiring',expired)):
                first=asyncio.create_task(llm_runtime.load_ollama_interface())
            second=asyncio.create_task(llm_runtime.load_ollama_interface())
            for _ in range(50):
                if started.is_set(): break
                await asyncio.sleep(.001)
            assert started.is_set() and not second.done()
            with pytest.raises(TimeoutError): await first
            assert not second.done()
            release.set()
            assert await asyncio.wait_for(second,2) is module
            assert calls==['backend.core.ollama_runnable']
        finally:
            release.set()
            await asyncio.gather(*(task for task in (first,second) if task is not None),return_exceptions=True)
    asyncio.run(scenario())
