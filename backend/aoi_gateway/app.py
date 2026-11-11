"""Small authenticated OpenAI-compatible surface over the unchanged AOI wrapper."""
from contextlib import asynccontextmanager
import hmac
import json
import time
from typing import Literal
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, ConfigDict, Field

from .settings import Settings
from .worker import GatewayFailure, Worker


class Message(BaseModel):
    model_config = ConfigDict(extra='forbid')
    role: Literal['system', 'developer', 'user', 'assistant']
    content: str = Field(max_length=32768)


class Chat(BaseModel):
    model_config = ConfigDict(extra='forbid')
    model: str
    messages: list[Message] = Field(min_length=1, max_length=64)
    stream: Literal[False] = False
    temperature: float = Field(default=0, ge=0, le=2, allow_inf_nan=False)
    max_tokens: int = Field(default=1024, ge=1, le=8192)
    n: Literal[1] = 1
    tools: list[dict] | None = None
    tool_choice: str | dict | None = None
    response_format: dict | None = None


class Embeddings(BaseModel):
    model_config = ConfigDict(extra='forbid')
    model: str
    input: str | list[str]
    encoding_format: Literal['float'] = 'float'
    dimensions: int | None = Field(default=None, ge=1, le=8192)


def reject_constant(value):
    raise ValueError('Nonfinite JSON constant')


class TooLarge(HTTPException):
    def __init__(self):
        super().__init__(413, 'gateway_request_too_large')


class BodyLimit:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        total, started = 0, False

        async def bounded_receive():
            nonlocal total
            message = await receive()
            if message['type'] == 'http.request':
                total += len(message.get('body', b''))
                if total > 131072:
                    raise TooLarge()
            return message

        async def observed_send(message):
            nonlocal started
            if message['type'] == 'http.response.start':
                started = True
            await send(message)

        try:
            await self.app(scope, bounded_receive, observed_send)
        except TooLarge:
            if not started:
                await JSONResponse({'detail': 'gateway_request_too_large'}, status_code=413)(scope, receive, send)


def create_app(settings=None, manager=None):
    selected = settings or Settings.from_env()
    worker = manager or Worker(selected)

    @asynccontextmanager
    async def lifespan(app):
        yield
        worker.close()

    app = FastAPI(title='PMem AOI LLM Gateway', lifespan=lifespan, docs_url=None, redoc_url=None)
    app.add_middleware(BodyLimit)

    def authorize(request: Request):
        value = request.headers.get('authorization', '')
        if not hmac.compare_digest(value.encode(), ('Bearer '+selected.token).encode()):
            raise HTTPException(401, 'Invalid gateway token')

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request, exc):
        return JSONResponse({'detail': 'invalid_gateway_request'}, status_code=422)

    @app.exception_handler(GatewayFailure)
    async def failure(request, exc):
        return JSONResponse({'detail': exc.code}, status_code=exc.status,
                            headers={'Retry-After': '1'} if exc.status == 429 else {})

    @app.exception_handler(TooLarge)
    async def too_large(request, exc):
        return JSONResponse({'detail': 'gateway_request_too_large'}, status_code=413)

    @app.get('/healthz')
    def health():
        return {'status': 'ok', 'service': 'aoi-gateway', 'inference_verified': False}

    @app.get('/readyz', dependencies=[Depends(authorize)])
    async def ready():
        return await worker.execute('ready')

    @app.get('/v1/models', dependencies=[Depends(authorize)])
    def models():
        # Configured aliases, not evidence of model availability.
        return {'object': 'list', 'data': [{'id': name, 'object': 'model', 'owned_by': 'aoi-gateway'}
                                         for name in (selected.model, selected.embedding_model)]}

    @app.get('/v1/capabilities', dependencies=[Depends(authorize)])
    def capabilities():
        return {'generation': 'unverified', 'json_object': 'validated-after-generation',
                'native_tool_calling': 'unsupported', 'streaming': 'unsupported',
                'vision': 'unsupported', 'embeddings': 'unverified',
                'missing_settings': selected.missing(), 'request_timeout_seconds': selected.timeout}

    @app.post('/v1/chat/completions', dependencies=[Depends(authorize)])
    async def chat(body: Chat):
        if body.model != selected.model:
            raise HTTPException(404, 'Unknown configured model alias')
        if body.tools or body.tool_choice not in (None, 'none'):
            raise HTTPException(501, 'Native tool calling is not exposed by this gateway; use structured proposals')
        messages = [item.model_dump() for item in body.messages]
        if body.response_format is not None:
            if body.response_format != {'type': 'json_object'}:
                raise HTTPException(501, 'Only JSON-object validation is supported; constrained schema decoding is unverified')
            messages.insert(0, {'role': 'system', 'content': 'Return only a valid JSON object, without code fences.'})
        result = await worker.execute('chat', {'messages': messages, 'temperature': body.temperature,
                                               'max_tokens': body.max_tokens})
        if body.response_format:
            try:
                valid = isinstance(json.loads(result['content'], parse_constant=reject_constant), dict)
            except (ValueError, TypeError):
                valid = False
            if not valid:
                raise HTTPException(502, 'AOI did not return a valid JSON object')
        return {'id': 'aoi-'+uuid4().hex, 'object': 'chat.completion', 'created': int(time.time()),
                'model': selected.model, 'choices': [{'index': 0,
                    'message': {'role': 'assistant', 'content': result['content']},
                    'finish_reason': result['finish_reason']}]}

    @app.post('/v1/embeddings', dependencies=[Depends(authorize)])
    async def embeddings(body: Embeddings):
        if body.model != selected.embedding_model:
            raise HTTPException(404, 'Unknown configured embedding alias')
        texts = [body.input] if isinstance(body.input, str) else body.input
        if not 1 <= len(texts) <= 32 or any(not text.strip() or len(text) > 8192 for text in texts):
            raise HTTPException(422, 'Use 1–32 nonempty text inputs, at most 8192 characters each')
        if body.dimensions is not None and body.dimensions != selected.embedding_dimensions:
            raise HTTPException(422, 'Requested dimensions differ from the configured embedding space')
        vectors = await worker.execute('embeddings', {'input': texts})
        return {'object': 'list', 'model': selected.embedding_model,
                'data': [{'object': 'embedding', 'index': index, 'embedding': vector}
                         for index, vector in enumerate(vectors)]}

    return app
