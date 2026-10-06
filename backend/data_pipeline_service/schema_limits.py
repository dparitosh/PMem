"""Bound retained schema reads before parsers allocate conversion structures."""
from pathlib import Path

SCHEMA_MAX_BYTES = 25 * 1024 * 1024


def read_schema_bytes(path: Path, *, remaining_bytes: int = SCHEMA_MAX_BYTES) -> bytes:
    limit = min(SCHEMA_MAX_BYTES, remaining_bytes)
    if limit < 0 or path.stat().st_size > limit:
        raise ValueError('Schema dependency closure exceeds 25 MiB')
    with path.open('rb') as stream:
        content = stream.read(limit + 1)
    if len(content) > limit:
        raise ValueError('Schema dependency closure exceeds 25 MiB')
    return content
