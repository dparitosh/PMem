"""Bound decoded downstream responses before buffering or persisting them."""
import os

def response_byte_limit():
    limit = int(os.getenv('AGENTIC_MAX_RESPONSE_BYTES', str(8 * 1024 * 1024)))
    if limit <= 0:
        raise ValueError('AGENTIC_MAX_RESPONSE_BYTES must be positive')
    return limit


async def read_bounded_response(response):
    limit = response_byte_limit()
    chunks, total = [], 0
    async for chunk in response.aiter_bytes():
        total += len(chunk)
        if total > limit:
            raise ValueError('Downstream tool response exceeds AGENTIC_MAX_RESPONSE_BYTES; narrow the request')
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
