"""Bound UTF-8 prompt payloads before sending or retaining them."""
import json
import os


def bounded_prompt_json(value):
    limit = int(os.getenv('AGENTIC_MAX_PROMPT_BYTES', '262144'))
    if not 16384 <= limit <= 1048576:
        raise ValueError('AGENTIC_MAX_PROMPT_BYTES must be between 16384 and 1048576')
    text = json.dumps(value, ensure_ascii=False, allow_nan=False)
    if len(text.encode('utf-8')) > limit:
        raise ValueError('Prompt exceeds AGENTIC_MAX_PROMPT_BYTES; narrow the evidence or tool selection')
    return text



def response_byte_limit():
    limit = int(os.getenv('AGENTIC_MAX_RESPONSE_BYTES', str(8 * 1024 * 1024)))
    if limit <= 0:
        raise ValueError('AGENTIC_MAX_RESPONSE_BYTES must be positive')
    return limit


async def read_bounded_response(response, *, limit=None):
    limit = response_byte_limit() if limit is None else limit
    if type(limit) is not int or limit <= 0:
        raise ValueError('Response byte limit must be a positive integer')
    chunks, total = [], 0
    async for chunk in response.aiter_bytes():
        total += len(chunk)
        if total > limit:
            raise ValueError('Downstream response exceeds its configured byte limit; narrow the request')
        chunks.append(chunk)
    return b''.join(chunks)


def read_bounded_response_sync(response):
    limit = response_byte_limit()
    chunks, total = [], 0
    for chunk in response.iter_content(chunk_size=65536):
        total += len(chunk)
        if total > limit:
            raise ValueError("Ollama response exceeds AGENTIC_MAX_RESPONSE_BYTES")
        chunks.append(chunk)
    return b"".join(chunks)
