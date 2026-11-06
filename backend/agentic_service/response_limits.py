"""Compatibility entry points for shared bounded response readers."""
from backend.core.payload_limits import response_byte_limit, read_bounded_response_sync


async def read_bounded_response(response, *, limit=None):
    from backend.core.payload_limits import read_bounded_response as read
    return await read(response, limit=response_byte_limit() if limit is None else limit)
