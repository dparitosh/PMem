"""Shared per-process admission and circuit controls for sync and async Ollama."""
import asyncio
import os
import threading
import time
from contextlib import asynccontextmanager, contextmanager

_lock = threading.Lock()
_states = {}


def _admit(endpoint):
    capacity = int(os.getenv('OLLAMA_MAX_CONCURRENCY', '4'))
    threshold = int(os.getenv('OLLAMA_FAILURE_THRESHOLD', '3'))
    cooldown = int(os.getenv('OLLAMA_CIRCUIT_COOLDOWN_SECONDS', '30'))
    if not 1 <= capacity <= 32 or not 1 <= threshold <= 20 or not 1 <= cooldown <= 300:
        raise ValueError('Invalid Ollama concurrency or circuit settings')
    with _lock:
        state = _states.setdefault(endpoint, {'active': 0, 'failures': 0, 'until': 0, 'generation': 0, 'probe': False})
        if time.monotonic() < state['until']:
            raise RuntimeError('Ollama circuit is open; retry after the cooldown')
        if state['until'] and state['probe']: return None
        if state['active'] >= capacity: return None
        probe = bool(state['until'])
        if probe: state['probe'] = True
        state['active'] += 1
        generation = state['generation']
    return state, threshold, cooldown, generation, probe


def _failure(state, threshold, cooldown, exc, generation):
    code = getattr(getattr(exc, 'response', None), 'status_code', getattr(exc, 'status_code', None))
    transport = type(exc).__module__.startswith(('httpx', 'requests', 'ollama'))
    # requests.HTTPError inherits OSError: explicit HTTP status must take precedence.
    transient = (code == 429 or code >= 500) if isinstance(code, int) else isinstance(exc, (TimeoutError, OSError)) or transport
    if transient:
        with _lock:
            if generation != state['generation']: return
            state['failures'] += 1
            if state['failures'] >= threshold:
                state['until'] = time.monotonic() + cooldown
                state['generation'] += 1


def _success(state, generation):
    with _lock:
        if generation != state['generation']: return
        state['failures'] = 0
        state['until'] = 0


@asynccontextmanager
async def request_slot(endpoint):
    from .ollama_auth import ollama_timeout
    deadline = time.monotonic() + ollama_timeout()
    while True:
        admitted = _admit(endpoint)
        if admitted: break
        if time.monotonic() >= deadline: raise TimeoutError('Ollama admission deadline exceeded')
        await asyncio.sleep(.05)
    state, threshold, cooldown, generation, probe = admitted
    try:
        yield
    except Exception as exc:
        _failure(state, threshold, cooldown, exc, generation)
        raise
    else: _success(state, generation)
    finally:
        with _lock:
            state['active'] -= 1
            if probe: state['probe'] = False


@contextmanager
def request_slot_sync(endpoint):
    from .ollama_auth import ollama_timeout
    deadline = time.monotonic() + ollama_timeout()
    while True:
        admitted = _admit(endpoint)
        if admitted: break
        if time.monotonic() >= deadline: raise TimeoutError('Ollama admission deadline exceeded')
        time.sleep(.05)
    state, threshold, cooldown, generation, probe = admitted
    try:
        yield
    except Exception as exc:
        _failure(state, threshold, cooldown, exc, generation)
        raise
    else: _success(state, generation)
    finally:
        with _lock:
            state['active'] -= 1
            if probe: state['probe'] = False
