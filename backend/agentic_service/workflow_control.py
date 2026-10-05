"""Cooperative workflow controls. They never interrupt or undo an in-flight tool."""
import asyncio


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
