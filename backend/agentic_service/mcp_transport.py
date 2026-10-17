"""Bounded stdio MCP transport for operator-configured servers only.

Protocol: https://modelcontextprotocol.io/specification/2025-06-18/basic/transports
"""
import asyncio
import json
import os
import sys
import math
import time
import logging
from uuid import uuid4
import hashlib
import weakref


async def _invoke(server, method, params=None, *, timeout_seconds=None, session=None):
    if server.get('transport') != 'stdio':
        raise ValueError('Only configured stdio MCP servers are supported')
    command = server['command']
    if command == 'python':
        command = sys.executable
    env = {key: os.environ[key] for key in ('PATH', 'SYSTEMROOT', 'WINDIR', 'TEMP', 'TMP', *server.get('environment', []))
           if key in os.environ}
    limit = int(os.getenv('AGENTIC_MAX_RESPONSE_BYTES', str(8 * 1024 * 1024)))
    from backend.depo_platform.network import bounded_timeout_seconds
    from backend.depo_platform.operations import current_operation
    operation = current_operation()
    timeout = timeout_seconds if timeout_seconds is not None else bounded_timeout_seconds('AGENTIC_TOOL_TIMEOUT_SECONDS', default=30)
    if operation:
        timeout = operation.timeout(timeout)
    process = session.get("process") if session is not None else None
    healthy = False
    async with asyncio.timeout(timeout):
        try:
            if process is not None and process.returncode is not None:
                raise ValueError("MCP session ended; retained workflow must handle session loss before continuing")
            fresh = process is None
            if fresh:
                process = await asyncio.create_subprocess_exec(command, *server.get('args', []),
                    stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.DEVNULL, env=env, limit=limit)
                if session is not None:
                    session['process'] = process
            sequence = session.get('sequence', 0) if session is not None else 0
            consumed = 0

            async def send(message):
                payload = json.dumps({'jsonrpc': '2.0', **message}).encode() + b'\n'
                if len(payload) > limit:
                    raise ValueError('MCP request exceeds the byte limit')
                process.stdin.write(payload)
                await process.stdin.drain()

            async def request(name, arguments):
                nonlocal sequence, consumed
                sequence += 1
                if session is not None:
                    session["sequence"] = sequence
                identifier = sequence
                progress_token = uuid4().hex if name == 'tools/call' else None
                if progress_token:
                    arguments = {**arguments, '_meta': {'progressToken': progress_token}}
                await send({'id': identifier, 'method': name, 'params': arguments})
                last_progress, reported_at = -1, float('-inf')
                while True:
                    line = await process.stdout.readline()
                    consumed += len(line)
                    if not line or consumed > limit:
                        raise ValueError('MCP server closed or exceeded the response limit')
                    message = json.loads(line)
                    if not isinstance(message, dict) or message.get('jsonrpc') != '2.0':
                        raise ValueError('Invalid MCP response')
                    if message.get('method') == 'notifications/progress':
                        value = message.get('params', {})
                        if not isinstance(value, dict) or not progress_token or value.get('progressToken') != progress_token:
                            continue
                        progress, total = value.get('progress'), value.get('total')
                        valid_number = lambda number: isinstance(number, (int, float)) and not isinstance(number, bool) and math.isfinite(number)
                        if (not valid_number(progress) or progress < 0 or progress <= last_progress
                                or (total is not None and (not valid_number(total) or total < progress))):
                            raise ValueError('Invalid MCP progress metadata')
                        last_progress = progress
                        if operation and operation.on_progress and time.monotonic() - reported_at >= 1:
                            # Persist numeric progress only; untrusted free text may
                            # contain prompts, credentials or upstream response data.
                            try:
                                await operation.on_progress({'current': progress, 'total': total, 'source': 'mcp'})
                            except Exception:
                                logging.getLogger(__name__).warning('MCP progress persistence unavailable')
                            reported_at = time.monotonic()
                        continue
                    if 'method' in message and 'id' in message:
                        # No sampling, elicitation, roots or tool authorization delegated.
                        await send({'id': message['id'], 'error': {'code': -32601, 'message': 'Client capability not supported'}})
                        continue
                    if message.get('id') != identifier:
                        continue
                    if 'error' in message:
                        raise ValueError('MCP server rejected the operation')
                    result = message.get('result')
                    if not isinstance(result, dict):
                        raise ValueError('MCP result must be an object')
                    return result

            if fresh:
                initialized = await request('initialize', {'protocolVersion': '2025-06-18',
                    'capabilities': {}, 'clientInfo': {'name': 'depo-agentic', 'version': '1.0'}})
                if initialized.get('protocolVersion') not in {'2024-11-05', '2025-03-26', '2025-06-18'}:
                    raise ValueError('Unsupported MCP protocol version')
                if 'tools' not in initialized.get('capabilities', {}):
                    raise ValueError('MCP server does not advertise tools')
                await send({'method': 'notifications/initialized'})
            result = await request(method, params or {})
            if method == 'tools/list':
                tools, cursors = [], set()
                while True:
                    rows = result.get('tools')
                    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
                        raise ValueError('Invalid MCP tool list')
                    tools.extend(rows)
                    cursor = result.get('nextCursor')
                    if not cursor:
                        result = {**result, 'tools': tools}
                        result.pop('nextCursor', None)
                        break
                    if not isinstance(cursor, str) or len(cursor) > 1024 or cursor in cursors or len(cursors) >= 99:
                        raise ValueError('Invalid or excessive MCP discovery pagination')
                    cursors.add(cursor)
                    result = await request('tools/list', {'cursor': cursor})
            if result.get('isError'):
                raise ValueError('MCP tool execution failed')
            healthy = True
            return result
        finally:
            if process is not None and (session is None or not healthy):
                await _close_process({'process': process})


_pools = weakref.WeakKeyDictionary()


async def _close_process(session):
    process = session.pop('process', None)
    if process is None:
        return
    if process.stdin:
        process.stdin.close()
    if process.returncode is None:
        try:
            process.terminate()
        except ProcessLookupError:
            pass
        try:
            await asyncio.wait_for(process.wait(), 1)
        except TimeoutError:
            try:
                process.kill()
            except ProcessLookupError:
                pass
            await asyncio.wait_for(process.wait(), 1)


def start_pool():
    """Enable bounded process reuse on this service event loop."""
    loop = asyncio.get_running_loop()
    if loop in _pools:
        return
    from backend.depo_platform.qos import positive_capacity
    from backend.depo_platform.network import bounded_timeout_seconds
    capacity = positive_capacity('AGENTIC_MCP_MAX_SESSIONS', 4)
    if capacity > 32:
        raise ValueError('AGENTIC_MCP_MAX_SESSIONS must be between 1 and 32')
    pool = {'sessions': {}, 'capacity': capacity,
            'idle': bounded_timeout_seconds('AGENTIC_MCP_IDLE_SECONDS', default=60, maximum=3600)}
    _pools[loop] = pool
    async def reap():
        while True:
            await asyncio.sleep(min(pool['idle'], 5))
            for key, session in list(pool['sessions'].items()):
                if not session['lock'].locked() and time.monotonic() - session['used'] >= pool['idle']:
                    pool['sessions'].pop(key, None)
                    await _close_process(session)
    pool['reaper'] = asyncio.create_task(reap())


async def close_pool():
    pool = _pools.pop(asyncio.get_running_loop(), None)
    if pool is None:
        return
    pool['reaper'].cancel()
    await asyncio.gather(pool['reaper'], return_exceptions=True)
    await asyncio.gather(*(_close_process(item) for item in pool['sessions'].values()))
    pool['sessions'].clear()


async def invoke(server, method, params=None, *, timeout_seconds=None):
    pool = _pools.get(asyncio.get_running_loop())
    if pool is None:
        return await _invoke(server, method, params, timeout_seconds=timeout_seconds)
    # Configuration and credential changes select a new session. Values remain
    # in server environment only; the pool key contains their digest.
    from backend.depo_platform.operations import current_operation
    owner = current_operation()
    # Server state must never cross workflow/request authorization boundaries.
    if owner is None:
        return await _invoke(server, method, params, timeout_seconds=timeout_seconds)
    fingerprint = {'operation_id': owner.operation_id, 'context_identity': id(owner), 'server': server,
                   'environment': {key: os.environ.get(key) for key in server.get('environment', [])}}
    key = hashlib.sha256(json.dumps(fingerprint, sort_keys=True).encode()).hexdigest()
    from backend.depo_platform.network import bounded_timeout_seconds
    from backend.depo_platform.operations import current_operation
    timeout = timeout_seconds if timeout_seconds is not None else bounded_timeout_seconds('AGENTIC_TOOL_TIMEOUT_SECONDS', default=30)
    operation = current_operation()
    if operation:
        timeout = operation.timeout(timeout)
    async with asyncio.timeout(timeout):
        sessions = pool['sessions']
        if key not in sessions:
            if len(sessions) >= pool['capacity']:
                idle = next(((k, v) for k, v in sessions.items() if not v['lock'].locked()), None)
                if idle is None:
                    raise RuntimeError('MCP session capacity is busy')
                sessions.pop(idle[0])
                sessions[key] = {'lock': asyncio.Lock(), 'used': time.monotonic(), 'owner': owner}
                await _close_process(idle[1])
            else:
                sessions[key] = {'lock': asyncio.Lock(), 'used': time.monotonic()}
        session = sessions.get(key)
        if session is None:
            raise RuntimeError('MCP session changed before dispatch; no tool was called')
        async with session['lock']:
            # A waiting caller may hold an evicted session reference.
            if sessions.get(key) is not session:
                raise RuntimeError('MCP session changed before dispatch; no tool was called')
            try:
                return await _invoke(server, method, params, timeout_seconds=timeout, session=session)
            except BaseException:
                sessions.pop(key, None)
                await _close_process(session)
                raise
            finally:
                session['used'] = time.monotonic()
