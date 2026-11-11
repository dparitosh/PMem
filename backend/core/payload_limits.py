"""Bound UTF-8 prompt payloads before sending or retaining them."""
import json
import os


class PromptBudgetExceeded(ValueError):
    """Safe diagnostic: the selected model cannot receive this evidence envelope."""


def check_model_budget(body):
    """Conservative UTF-8 token upper bound with completion/framing reserve.

    Operators must set this to the verified usable context of their provider/model.
    This intentionally prefers rejecting an oversized request to silent truncation.
    """
    context = int(os.getenv('AGENTIC_MODEL_CONTEXT_TOKENS', '32768'))
    if not 1024 <= context <= 2097152:
        raise ValueError('AGENTIC_MODEL_CONTEXT_TOKENS must be between 1024 and 2097152')
    completion = (body.get('options') or {}).get('num_predict', 1024)
    if type(completion) is not int or completion <= 0:
        raise ValueError('A positive bounded model completion budget is required')
    size = len(json.dumps(body, ensure_ascii=False, allow_nan=False).encode('utf-8'))
    if size + completion + 2048 > context:
        raise PromptBudgetExceeded('Prompt exceeds the configured model context budget; narrow evidence or tool selection')


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
