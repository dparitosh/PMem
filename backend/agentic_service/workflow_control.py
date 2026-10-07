"""Cooperative workflow controls. They never interrupt or undo an in-flight tool."""
import asyncio
import logging
from contextlib import asynccontextmanager, suppress
from datetime import datetime, timezone


@asynccontextmanager
async def execution_heartbeat(store, key):
    async def pulse():
        while True:
            try:
                await asyncio.to_thread(store.put, key, {'updated_at': datetime.now(timezone.utc).isoformat()})
            except Exception:
                logging.getLogger(__name__).warning('Workflow heartbeat persistence failed')
            await asyncio.sleep(10)
    task = asyncio.create_task(pulse())
    try:
        yield
    finally:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task


def last_activity(record, heartbeat):
    return max(record['updated_at'], (heartbeat or {}).get('updated_at', record['updated_at']))


class WorkflowCancelled(Exception):
    pass


async def checkpoint(store, run_id):
    while True:
        control = await asyncio.to_thread(store.get, run_id) or {}
        action = control.get("action", "resume")
        if action == "cancel":
            raise WorkflowCancelled("Workflow cancelled at a tool boundary")
        if action != "pause":
            return
        await asyncio.sleep(0.5)
