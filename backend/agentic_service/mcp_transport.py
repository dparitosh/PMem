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


async def invoke(server, method, params=None, *, timeout_seconds=None):
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
    process = None
    async with asyncio.timeout(timeout):
        try:
            process = await asyncio.create_subprocess_exec(command, *server.get('args', []),
                stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL, env=env, limit=limit)
            sequence = 0
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

            initialized = await request('initialize', {'protocolVersion': '2025-06-18',
                'capabilities': {}, 'clientInfo': {'name': 'depo-agentic', 'version': '1.0'}})
            if initialized.get('protocolVersion') not in {'2024-11-05', '2025-03-26', '2025-06-18'}:
                raise ValueError('Unsupported MCP protocol version')
            if 'tools' not in initialized.get('capabilities', {}):
                raise ValueError('MCP server does not advertise tools')
            await send({'method': 'notifications/initialized'})
            result = await request(method, params or {})
            if result.get('isError'):
                raise ValueError('MCP tool execution failed')
            return result
        finally:
            if process is not None:
                if process.stdin:
                    process.stdin.close()
                if process.returncode is None:
                    try:
                        await asyncio.wait_for(process.wait(), 1)
                    except TimeoutError:
                        try:
                            process.terminate()
                        except ProcessLookupError:
                            pass
                        try:
                            await asyncio.wait_for(process.wait(), 1)
                        except TimeoutError:
                            process.kill()
                            await process.wait()
