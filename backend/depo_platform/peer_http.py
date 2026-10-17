"""Bounded HTTP peer calls; socket activity never extends the operation deadline."""
import asyncio


async def async_peer_response(method, endpoint, *, headers, budget, response_limit=None, **kwargs):
    import httpx
    from .operations import current_operation
    from .network import http_timeout, operation_headers
    from backend.agentic_service.response_limits import read_bounded_response
    operation = current_operation()
    if operation:
        budget = operation.timeout(budget)
    async with asyncio.timeout(budget), httpx.AsyncClient(timeout=http_timeout(budget), trust_env=False,
                                                        follow_redirects=False) as client:
        async with client.stream(method, endpoint, headers={**headers, **operation_headers()}, **kwargs) as response:
            content = await read_bounded_response(response, limit=response_limit)
            return httpx.Response(response.status_code, content=content, headers=response.headers, request=response.request)


def peer_response(method, endpoint, *, headers, budget, response_limit=None, **kwargs):
    from backend.core.sync_async import call_async
    return call_async(lambda: async_peer_response(method, endpoint, headers=headers, budget=budget,
                                                  response_limit=response_limit, **kwargs))
