"""Fleet request admission, elapsed-time budgets and bounded QoS telemetry."""
import asyncio
from collections import Counter
from datetime import datetime, timedelta, timezone
import json
import logging
import os
import threading
import time
from .operations import OperationContext, current_operation, operation_scope, remaining_seconds
from .network import bounded_timeout_seconds
from .postgres_pool import PoolBusy


def positive_capacity(name, default, maximum=1024):
    value = int(os.getenv(name, str(default)))
    if not 1 <= value <= maximum:
        raise ValueError(f'{name} must be between 1 and {maximum}')
    return value


def request_budget(path):
    from .network import (graph_dispatch_timeout_seconds, ontology_publication_timeout_seconds,
                          engineering_workflow_timeout_seconds, agent_run_timeout_seconds)
    if path.startswith(('/auth/', '/healthz', '/readyz', '/qos/')):
        return bounded_timeout_seconds('DEPO_CONTROL_REQUEST_TIMEOUT_SECONDS', default=15, maximum=60)
    if '/graph/ontologies/publish' in path or '/publications/graph' in path:
        return graph_dispatch_timeout_seconds() + 30
    if '/engineering-workflows' in path:
        return engineering_workflow_timeout_seconds() + 30
    if path.endswith('/publish') and '/ontologies/' in path:
        return ontology_publication_timeout_seconds() + 30
    # Merge preparation performs bounded RDF parsing and SHACL/OWL-RL work.
    # Its outer HTTP deadline must not truncate that worker at the generic
    # 90-second request limit. Keep unrelated ontology reads on that limit.
    merge_path = path.rstrip('/')
    merge_root = '/api/v1/ontologies/merges/'
    if merge_path.startswith(merge_root):
        operation = merge_path[len(merge_root):].split('/')
        validation = bounded_timeout_seconds('MERGE_VALIDATION_TIMEOUT_SECONDS', default=180, maximum=900)
        if operation == ['preview']:
            return validation + 30
        if len(operation) == 2 and operation[0] and operation[1] in {'apply', 'apply-automatic'}:
            return validation + ontology_publication_timeout_seconds() + 30
    if '/workflow-runs' in path or '/runs' in path or '/chat' in path or '/suggest' in path:
        return agent_run_timeout_seconds() + 30
    if '/pipeline/' in path and path.endswith('/run'):
        return bounded_timeout_seconds('DEPO_PIPELINE_JOB_TIMEOUT_SECONDS', default=900, maximum=86400) + 30
    return bounded_timeout_seconds('DEPO_REQUEST_TIMEOUT_SECONDS', default=90, maximum=86400)


class QoSState:
    buckets = (.1, .5, 1, 5, 15, 30, 60, 180, 900, float('inf'))

    def __init__(self):
        self.capacities = {'work': positive_capacity('DEPO_MAX_INFLIGHT_REQUESTS', 64),
                           'control': positive_capacity('DEPO_MAX_INFLIGHT_CONTROL_REQUESTS', 16)}
        self.active = Counter()
        self.rejected = Counter()
        self.routes = {}
        self.lock = threading.Lock()

    def enter(self, lane):
        with self.lock:
            if self.active[lane] >= self.capacities[lane]:
                self.rejected[lane] += 1
                return False
            self.active[lane] += 1
            return True

    def finish(self, lane, route, status, elapsed):
        with self.lock:
            self.active[lane] -= 1
            if route not in self.routes and len(self.routes) >= 256:
                route = '<other>'
            item = self.routes.setdefault(route, {'count':0, 'seconds_sum':0, 'statuses':Counter(), 'buckets':Counter()})
            item['count'] += 1
            item['seconds_sum'] += elapsed
            item['statuses'][str(status)] += 1
            for bucket in self.buckets:
                if elapsed <= bucket:
                    item['buckets'][str(bucket)] += 1

    def snapshot(self):
        with self.lock:
            return {'capacity':dict(self.capacities), 'inflight':dict(self.active), 'rejected':dict(self.rejected),
                    'routes':{key:{**value, 'statuses':dict(value['statuses']), 'buckets':dict(value['buckets'])}
                              for key,value in self.routes.items()}}


class QoSMiddleware:
    def __init__(self, app, state):
        self.app, self.state = app, state

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        path = scope.get('path', '')
        lane = 'control' if path.startswith(('/auth/', '/healthz', '/readyz', '/qos/')) else 'work'
        async def failure(status, message):
            from starlette.responses import JSONResponse
            await JSONResponse({'detail':message, 'request_id':scope.get('state', {}).get('request_id', '')},
                               status_code=status, headers={'Retry-After':'5'} if status == 503 else {})(scope, receive, send)
        if not self.state.enter(lane):
            return await failure(503, 'Service capacity is busy; retry later. Retained jobs are unaffected.')
        started, status, response_started, content_type = time.monotonic(), 500, False, b''
        async def tracked(message):
            nonlocal status, response_started, content_type
            if message['type'] == 'http.response.start':
                status, response_started = message['status'], True
                content_type = dict(message.get('headers', [])).get(b'content-type', b'')
            await send(message)
        try:
            budget = request_budget(path)
            inherited = current_operation()
            if inherited:
                budget = inherited.timeout(budget)
            deadline = (datetime.now(timezone.utc) + timedelta(seconds=budget)).isoformat()
            supplied = dict(scope.get('headers', [])).get(b'x-depo-deadline')
            if supplied:
                try:
                    seconds = remaining_seconds(supplied.decode('ascii'))
                    if seconds < budget:
                        deadline = supplied.decode('ascii')
                except (UnicodeError, ValueError):
                    status = 400
                    return await failure(status, 'Invalid operation deadline')
            context = OperationContext(scope.get('state', {}).get('request_id', 'request'), deadline)
            with operation_scope(context):
                async with asyncio.timeout(remaining_seconds(deadline)):
                    await self.app(scope, receive, tracked)
        except (TimeoutError, PoolBusy) as exc:
            status = 503 if isinstance(exc, PoolBusy) else 504
            if response_started:
                # Headers are already on the wire; terminate an SSE stream with
                # explicit failure rather than inventing a successful completion.
                body = b''
                if b'text/event-stream' in content_type:
                    body = ('data: ' + json.dumps({'error':'Service deadline exceeded; inspect the retained run before retrying.',
                                                  'done':True, 'status':'timed_out'}) + '\n\n').encode()
                await send({'type':'http.response.body', 'body':body, 'more_body':False})
            else:
                await failure(status, 'Service capacity is busy; retry later.' if status == 503 else
                              'Operation deadline exceeded. Verify any retained write outcome before retrying.')
        except Exception:
            status = 500
            raise
        finally:
            route = getattr(scope.get('route'), 'path', '<unmatched>')
            self.state.finish(lane, scope.get('method', '') + ' ' + route, status, time.monotonic()-started)
