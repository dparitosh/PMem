"""Synchronous adapters for cancellable async inference, with bounded buffering."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from queue import Queue, Full
from threading import Event, Thread


def call_async(factory):
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(factory())
    # A synchronous LangChain caller may itself live on an event-loop thread.
    with ThreadPoolExecutor(max_workers=1) as executor:
        return executor.submit(lambda: asyncio.run(factory())).result()


def iterate_async(factory):
    messages = Queue(maxsize=1)
    stopped = Event()
    state = {}

    async def produce():
        state.update(loop=asyncio.get_running_loop(), task=asyncio.current_task())

        async def emit(kind, value):
            while not stopped.is_set():
                try:
                    messages.put_nowait((kind, value))
                    return
                except Full:
                    await asyncio.sleep(.01)

        iterator = factory()
        try:
            async for value in iterator:
                await emit('value', value)
        except asyncio.CancelledError:
            if not stopped.is_set():
                await emit('error', asyncio.CancelledError())
        except Exception as exc:
            await emit('error', exc)
        finally:
            try:
                await iterator.aclose()
            except Exception as exc:
                await emit('error', exc)
            finally:
                await emit('done', None)

    def run_producer():
        try:
            asyncio.run(produce())
        except asyncio.CancelledError:
            if not stopped.is_set():
                raise

    worker = Thread(target=run_producer, daemon=True)
    worker.start()
    try:
        while True:
            kind, value = messages.get()
            if kind == 'done':
                return
            if kind == 'error':
                raise value
            yield value
    finally:
        stopped.set()
        loop, task = state.get('loop'), state.get('task')
        if loop and task:
            try:
                loop.call_soon_threadsafe(task.cancel)
            except RuntimeError:
                pass  # Producer already closed its loop.
        worker.join(timeout=1)
