"""LangChain Runnable for the configured native Ollama/APIM REST contract.

Transport has no authorization to execute proposed tools or publish graph data.
Exact routes, payload limits, circuit/admission policy and operation deadlines
remain application-owned. Import this module lazily on inference paths.
"""
import asyncio
import json
import logging
import os
import time
from contextlib import asynccontextmanager
import httpx
from langchain_core.runnables import Runnable
from .payload_limits import bounded_prompt_json, read_bounded_response
from .ollama_auth import ollama_headers, ollama_timeout
from .ollama_limits import request_slot
from backend.depo_platform.operations import current_operation


async def read_native_frames(response):
    """Bound NDJSON before decoding; handle frames split across network chunks."""
    import json
    limit = int(os.getenv('AGENTIC_MAX_RESPONSE_BYTES', str(8 * 1024 * 1024)))
    pending, total = b'', 0
    async for chunk in response.aiter_bytes():
        total += len(chunk)
        if total > limit:
            raise ValueError('Ollama stream exceeds the response byte limit')
        pending += chunk
        while b'\n' in pending:
            line, pending = pending.split(b'\n', 1)
            if len(line) > 65536:
                raise ValueError('Ollama stream frame exceeds the byte limit')
            if line.strip():
                yield json.loads(line)
        if len(pending) > 65536:
            raise ValueError('Ollama stream frame exceeds the byte limit')
    if pending.strip():
        yield json.loads(pending)


def native_content(result, operation):
    if not isinstance(result, dict) or result.get('error'):
        raise ValueError('Invalid Ollama result')
    if operation == 'generate':
        content = result.get('response', '')
    else:
        message = result.get('message', {})
        if not isinstance(message, dict):
            raise ValueError('Invalid Ollama chat message')
        content = message.get('content', '')
    if not isinstance(content, str):
        raise ValueError('Invalid Ollama content')
    return content



def prompt_messages(system, user):
    """Format literal policy/evidence values without interpreting their braces."""
    from langchain_core.prompts import ChatPromptTemplate
    template = ChatPromptTemplate.from_messages([('system', '{policy}'), ('human', '{evidence}')])
    messages = template.format_messages(policy=system, evidence=user)
    return [{'role': 'system' if message.type == 'system' else 'user', 'content': message.content}
            for message in messages]


class OllamaRestRunnable(Runnable):
    def __init__(self, *, endpoint, headers, client=None, frame_reader=None, timeout=None):
        self.endpoint, self.headers = endpoint, dict(headers)
        self.client, self.frame_reader = client, frame_reader or read_native_frames
        self.timeout = timeout

    def _budget(self, body):
        if not isinstance(body, dict):
            raise ValueError('Ollama input must be an object')
        if type(body.get('stream', False)) is not bool:
            raise ValueError('Ollama stream must be a boolean')
        bounded_prompt_json(body)
        ollama_headers(self.endpoint)
        budget = self.timeout if self.timeout is not None else ollama_timeout()
        operation = current_operation()
        return operation.timeout(budget) if operation else budget

    @asynccontextmanager
    async def _client(self, budget):
        if self.client is not None:
            yield self.client
        else:
            async with httpx.AsyncClient(timeout=budget, trust_env=False, follow_redirects=False) as client:
                yield client

    def invoke(self, input, config=None, **kwargs):
        if self.client is not None:
            raise ValueError("Use ainvoke with an injected asynchronous client")
        from .sync_async import call_async
        return call_async(lambda: self.ainvoke(input, config=config, **kwargs))

    async def ainvoke(self, input, config=None, **kwargs):
        budget = self._budget(input)
        if input.get('stream') is True:
            raise ValueError('Use astream for streaming inference')
        started = time.perf_counter()
        async with asyncio.timeout(budget), request_slot(self.endpoint), self._client(budget) as client:
            async with client.stream('POST', self.endpoint, headers=self.headers, json=input) as response:
                response.raise_for_status()
                result = json.loads(await read_bounded_response(response))
        if not isinstance(result, dict) or result.get('error') or result.get('done') is not True:
            raise ValueError('Ollama returned an invalid or incomplete result')
        metrics = {key: result[key] for key in ('prompt_eval_count', 'eval_count')
                   if type(result.get(key)) is int and result[key] >= 0}
        logging.getLogger(__name__).info('Ollama inference metrics %s', json.dumps({
            'model': input.get('model'), 'duration_ms': round((time.perf_counter()-started)*1000, 2),
            'proposal_mode': 'native' if 'tools' in input else 'structured' if 'format' in input else 'generation', **metrics}))
        return result

    async def astream(self, input, config=None, **kwargs):
        budget = self._budget(input)
        if input.get('stream') is not True:
            raise ValueError('Streaming inference requires stream=true')
        async with asyncio.timeout(budget), request_slot(self.endpoint), self._client(budget) as client:
            async with client.stream('POST', self.endpoint, headers=self.headers, json=input) as response:
                response.raise_for_status()
                complete = False
                async for frame in self.frame_reader(response):
                    if (not isinstance(frame, dict) or frame.get('error')
                            or type(frame.get('done', False)) is not bool):
                        raise ValueError('Invalid Ollama stream frame')
                    yield frame
                    if frame.get('done') is True:
                        complete = True
                        break
                if not complete:
                    raise ValueError('Ollama stream ended without completion')

    def stream(self, input, config=None, **kwargs):
        if self.client is not None:
            raise ValueError("Use astream with an injected asynchronous client")
        from .sync_async import iterate_async
        yield from iterate_async(lambda: self.astream(input, config=config, **kwargs))
