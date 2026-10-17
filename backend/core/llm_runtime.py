"""Load optional model composition off the request event loop, once per runtime."""
import asyncio
import importlib
import weakref
from .ollama_auth import ollama_timeout
from backend.depo_platform.operations import current_operation

_loaded = None
_loading = weakref.WeakKeyDictionary()


async def load_ollama_interface():
    global _loaded
    if _loaded is not None:
        return _loaded
    budget = ollama_timeout()
    operation = current_operation()
    if operation:
        budget = operation.timeout(budget)
    loop = asyncio.get_running_loop()
    task = _loading.get(loop)
    if task is None:
        task = asyncio.create_task(asyncio.to_thread(importlib.import_module, 'backend.core.ollama_runnable'))
        _loading[loop] = task
        def finished(result):
            global _loaded
            _loading.pop(loop, None)
            if not result.cancelled() and result.exception() is None:
                _loaded = result.result()
        task.add_done_callback(finished)
    # One caller timing out must not cancel initialization for other callers.
    async with asyncio.timeout(budget):
        return await asyncio.shield(task)
