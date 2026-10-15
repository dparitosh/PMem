"""Bounded HTTP peer calls for synchronous data-service adapters."""
import asyncio


def peer_response(method, endpoint, *, headers, budget, **kwargs):
    from backend.core.sync_async import call_async
    from .operations import current_operation
    operation = current_operation()
    if operation: budget = operation.timeout(budget)
    async def request():
        import httpx
        from .network import http_timeout
        from backend.agentic_service.response_limits import read_bounded_response
        async with asyncio.timeout(budget), httpx.AsyncClient(timeout=http_timeout(budget),trust_env=False) as client:
            async with client.stream(method, endpoint, headers=headers, **kwargs) as response:
                content = await read_bounded_response(response)
                return httpx.Response(response.status_code,content=content,headers=response.headers,request=response.request)
    return call_async(request)
