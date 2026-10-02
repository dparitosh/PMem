"""Bound decoded downstream responses before buffering or persisting them."""
import os

async def read_bounded_response(response):
    limit = int(os.getenv('AGENTIC_MAX_RESPONSE_BYTES', str(8 * 1024 * 1024)))
    if limit <= 0:
        raise ValueError('AGENTIC_MAX_RESPONSE_BYTES must be positive')
    chunks, total = [], 0
    async for chunk in response.aiter_bytes():
        total += len(chunk)
        if total > limit:
            raise ValueError('Downstream tool response exceeds AGENTIC_MAX_RESPONSE_BYTES; narrow the request')
        chunks.append(chunk)
    return b''.join(chunks)
