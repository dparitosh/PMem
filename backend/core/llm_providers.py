"""Explicit cloud provider adapters. Ollama stays local; never fall back to cloud."""
from dataclasses import dataclass, field
import asyncio
import json
import os
from urllib.parse import urlsplit

CLOUD_PROVIDERS = ('openai', 'mistral', 'aoi')
PROVIDERS = ('ollama', 'azure', *CLOUD_PROVIDERS)
DEFAULT_BASES = {'openai': 'https://api.openai.com/v1', 'mistral': 'https://api.mistral.ai/v1'}


@dataclass(frozen=True)
class CloudSettings:
    provider: str
    model: str
    base_url: str
    api_key: str = field(repr=False)


def cloud_settings(provider, *, embeddings=False, unstructured=False):
    if provider not in CLOUD_PROVIDERS:
        raise ValueError('Select openai, mistral, or aoi')
    if provider == 'aoi' and unstructured:
        raise ValueError('AOI gateway supports text only; select another unstructured provider')
    prefix = provider.upper()
    model_key = prefix + ('_EMBED_MODEL' if embeddings else '_MODEL')
    if unstructured:
        model_key = 'UNSTRUCTURED_' + model_key
    model = os.getenv(model_key, '').strip()
    key_name = 'AOI_GATEWAY_TOKEN' if provider == 'aoi' else prefix + '_API_KEY'
    key = os.getenv(key_name, '').strip()
    missing = [name for name, value in ((model_key, model), (key_name, key)) if not value or '<' in value]
    if missing:
        raise ValueError('Missing provider settings: ' + ', '.join(missing))
    if any(ord(char) < 32 for char in key):
        raise ValueError('Invalid ' + key_name)
    base_key = prefix + '_BASE_URL'
    base = os.getenv(base_key, DEFAULT_BASES.get(provider, '')).strip().rstrip('/')
    try:
        parsed = urlsplit(base)
        loopback = parsed.hostname in {'127.0.0.1', 'localhost', '::1'}
        valid = ((parsed.scheme == 'https' or (provider == 'aoi' and parsed.scheme == 'http' and loopback)) and parsed.hostname and not parsed.username
                 and not parsed.password and not parsed.query and not parsed.fragment)
        parsed.port
    except ValueError:
        valid = False
    if not valid:
        raise ValueError('Invalid ' + base_key + ': an HTTPS API root is required (AOI also permits HTTP on loopback)')
    if provider == 'aoi' and (len(key) < 32 or any(c.isspace() for c in key)):
        raise ValueError('Invalid AOI_GATEWAY_TOKEN')
    if provider == 'aoi' and embeddings:
        try:
            dimensions = int(os.getenv('EMBEDDING_VECTOR_DIMENSIONS', ''))
            if not 1 <= dimensions <= 8192: raise ValueError()
        except ValueError:
            raise ValueError('Set EMBEDDING_VECTOR_DIMENSIONS to the AOI embedding space') from None
    return CloudSettings(provider, model, base, key)


def cloud_chat(provider, *, unstructured=False):
    from langchain_openai import ChatOpenAI
    from backend.core.ollama_auth import ollama_timeout
    settings = cloud_settings(provider, unstructured=unstructured)
    kwargs = dict(model=settings.model, api_key=settings.api_key, base_url=settings.base_url,
                  timeout=ollama_timeout(), max_retries=0)
    # Responses is the OpenAI interface; Mistral exposes Chat Completions.
    kwargs['use_responses_api'] = provider == 'openai'
    if provider == 'aoi':
        import httpx
        kwargs.update(http_client=httpx.Client(trust_env=False), http_async_client=httpx.AsyncClient(trust_env=False))
    return ChatOpenAI(**kwargs)


def cloud_embeddings(provider):
    from langchain_openai import OpenAIEmbeddings
    from backend.core.ollama_auth import ollama_timeout
    settings = cloud_settings(provider, embeddings=True)
    # Send the original strings, not OpenAI tokenizer IDs, to Mistral.
    clients = {}
    if provider == 'aoi':
        import httpx
        clients = {'http_client': httpx.Client(trust_env=False), 'http_async_client': httpx.AsyncClient(trust_env=False), 'chunk_size': 32, 'dimensions': int(os.environ['EMBEDDING_VECTOR_DIMENSIONS'])}
    return OpenAIEmbeddings(**clients, model=settings.model, api_key=settings.api_key,
        base_url=settings.base_url, check_embedding_ctx_length=False,
        request_timeout=ollama_timeout(), max_retries=0,
        model_kwargs={"encoding_format": "float"})


async def post_cloud_chat(client, provider, body):
    """Translate the review pipeline's message contract without granting tool execution."""
    settings = cloud_settings(provider)
    messages = body.get('messages')
    if messages is None:
        messages = [{'role': 'system', 'content': body.get('system', '')},
                    {'role': 'user', 'content': body.get('prompt', '')}]
    payload = {'model': settings.model, 'messages': list(messages), 'stream': False}
    token_key = 'max_completion_tokens' if provider == 'openai' else 'max_tokens'
    payload[token_key] = body.get('options', {}).get('num_predict', 1024)
    if body.get('tools'):
        payload['tools'] = body['tools']
        payload['tool_choice'] = 'required'
    elif body.get('format'):
        payload['response_format'] = {'type': 'json_object'}
        payload['messages'] = [{'role': 'system', 'content':
            'Return only JSON conforming to this schema: ' + json.dumps(body['format'])}] + payload['messages']
    from backend.agentic_service.prompt_limits import bounded_prompt_json
    bounded_prompt_json(payload)
    from backend.core.payload_limits import check_model_budget
    check_model_budget({**payload, 'options': {'num_predict': payload[token_key]}})
    from backend.core.ollama_auth import ollama_timeout
    from backend.depo_platform.operations import current_operation
    from backend.core.ollama_limits import request_slot
    endpoint = settings.base_url + '/chat/completions'
    operation = current_operation()
    budget = operation.timeout(ollama_timeout()) if operation else ollama_timeout()
    async with asyncio.timeout(budget), request_slot(endpoint), client.stream('POST', endpoint,
            headers={'Authorization': 'Bearer ' + settings.api_key}, json=payload) as response:
        response.raise_for_status()
        from backend.agentic_service.response_limits import read_bounded_response
        result = json.loads(await read_bounded_response(response))
    choices = result.get('choices') if isinstance(result, dict) else None
    if not isinstance(choices, list) or len(choices) != 1 or not isinstance(choices[0], dict):
        raise ValueError('Invalid provider response')
    choice = choices[0]
    if choice.get('finish_reason') not in {'stop', 'tool_calls'}:
        raise ValueError('Incomplete provider response')
    message = choice.get('message')
    if not isinstance(message, dict) or message.get('refusal'):
        raise ValueError('Provider returned no usable answer')
    content = message.get('content') or ''
    if not isinstance(content, str):
        raise ValueError('Invalid provider content')
    calls = []
    for call in message.get('tool_calls') or []:
        function = call['function']
        calls.append({'function': {'name': function['name'], 'arguments': json.loads(function['arguments'])}})
    return {'done': True, 'message': {'content': content, 'tool_calls': calls}}


def embedding_identity():
    """Secret-free cache identity including the effective provider, endpoint and model."""
    provider = os.getenv('USE_EMBEDDER', os.getenv('USE_LLM', 'ollama')).strip().lower()
    if provider in CLOUD_PROVIDERS:
        selected = cloud_settings(provider, embeddings=True)
        model, endpoint = selected.model, selected.base_url
    elif provider == 'ollama':
        from backend.core.ollama_auth import ollama_base_url
        model = os.getenv('EMBED_MODEL_NAME', 'nomic-embed-text:latest').strip()
        endpoint = ollama_base_url()
    elif provider == 'azure':
        model = os.getenv('AZURE_OPENAI_EMBEDDINGS_DEPLOYMENT', '').strip()
        endpoint = os.getenv('AZURE_OPENAI_EMBEDDINGS_ENDPOINT', '').strip()
    else:
        raise ValueError('Invalid USE_EMBEDDER')
    return json.dumps({'provider': provider, 'model': model, 'endpoint': endpoint,
                      'dimensions': os.getenv('EMBEDDING_VECTOR_DIMENSIONS', '768')}, sort_keys=True)
