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
