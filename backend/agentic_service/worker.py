"""Run the PostgreSQL workflow worker using protected server configuration."""
import asyncio
from .durable_workflows import worker_loop
from .mcp_transport import start_pool, close_pool


async def main():
    start_pool()
    try:
        await worker_loop()
    finally:
        await close_pool()


if __name__ == '__main__':
    asyncio.run(main())
