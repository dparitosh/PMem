"""Run the PostgreSQL workflow worker using protected server configuration."""
import asyncio
from .durable_workflows import worker_loop

if __name__ == '__main__':
    asyncio.run(worker_loop())
