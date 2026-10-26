"""The unchanged AOI helper runs only in a killable, serial gateway worker."""
import asyncio
import math
import multiprocessing
import os
import sys
import time


class GatewayFailure(Exception):
    def __init__(self, status, code):
        self.status, self.code = status, code
        super().__init__(code)


def _completion(response):
    message = getattr(response, 'message', None)
    content = response if isinstance(response, str) else getattr(message, 'content', None)
    if not isinstance(content, str) or not content.strip() or len(content) > 64000:
        raise ValueError('Invalid model content')
    raw = getattr(response, 'raw', None)
    choices = raw.get('choices', []) if isinstance(raw, dict) else getattr(raw, 'choices', [])
    reason = None
    if choices:
        reason = choices[0].get('finish_reason') if isinstance(choices[0], dict) else getattr(choices[0], 'finish_reason', None)
    if reason is None:
        reason = (getattr(response, 'additional_kwargs', None) or {}).get('finish_reason')
    # A missing completion marker is not evidence that the model finished.
    return {'content': content, 'finish_reason': reason if reason in {'stop', 'length', 'content_filter'} else 'unknown'}


def worker_main(pipe, settings):
    # Vendor code may print account data; discard its console output, not secrets
    # into a file. Only allowlisted result fields cross the private IPC pipe.
    sys.dont_write_bytecode = True
    with open(os.devnull, 'w') as sink:
        os.dup2(sink.fileno(), 1)
        os.dup2(sink.fileno(), 2)
    try:
        from .vendor import verify
        verify(settings.vendor_dir)
        os.chdir(settings.vendor_dir)  # Dedicated child only, never the API/IIF process.
        sys.path.insert(0, str(settings.vendor_dir))
        from CustomAOI_helper import InitAOI
        models = InitAOI(__name__, settings.username, settings.password,
                         [settings.upstream_model], [settings.deployment],
                         settings.upstream_embedding_model, settings.embedding_deployment)
        pipe.send({'ok': True})
        while True:
            operation, payload = pipe.recv()
            try:
                if operation == 'chat':
                    # evaluate=False avoids turning a generation into evaluation calls.
                    result = _completion(models.chat(payload['messages'], llm_index=0, evaluate=False,
                                                     temperature=payload['temperature'], max_tokens=payload['max_tokens']))
                elif operation == 'embeddings':
                    result = models.embedder.get_text_embedding_batch(payload['input'])
                    if len(result) != len(payload['input']):
                        raise ValueError('Invalid embedding count')
                    for vector in result:
                        if len(vector) != settings.embedding_dimensions or any(isinstance(x, bool) or not isinstance(x, (float, int)) or not math.isfinite(x) for x in vector):
                            raise ValueError('Invalid embedding vector')
                else:
                    raise ValueError('Unsupported worker operation')
                pipe.send({'ok': True, 'result': result})
            except Exception:
                pipe.send({'ok': False, 'code': 'aoi_inference_failed'})
    except Exception:
        try:
            pipe.send({'ok': False, 'code': 'aoi_initialization_failed'})
        except (OSError, EOFError):
            pass
    finally:
        pipe.close()


class Worker:
    def __init__(self, settings, context=None):
        self.settings = settings
        self.context = context or multiprocessing.get_context('spawn')
        self.process, self.pipe = None, None
        self.lock = asyncio.Lock()

    def close(self):
        if self.process is not None:
            if self.process.is_alive():
                self.process.terminate()
            self.process.join(2)
            if self.process.is_alive():
                self.process.kill()
                self.process.join(2)
            self.process.close()
        if self.pipe is not None:
            self.pipe.close()
        self.process, self.pipe = None, None

    def _receive(self, deadline):
        if not self.pipe.poll(max(0, deadline-time.monotonic())):
            raise GatewayFailure(504, 'aoi_deadline_exceeded')
        result = self.pipe.recv()
        if not isinstance(result, dict) or result.get('ok') is not True:
            code = result.get('code') if isinstance(result, dict) else None
            code = code if code in {'aoi_initialization_failed', 'aoi_inference_failed'} else 'aoi_request_failed'
            raise GatewayFailure(503 if code == 'aoi_initialization_failed' else 502, code)
        return result.get('result')

    def _call(self, operation, payload):
        deadline = time.monotonic()+self.settings.timeout
        try:
            if self.process is None or not self.process.is_alive():
                self.close()
                self.pipe, child = self.context.Pipe()
                self.process = self.context.Process(target=worker_main, args=(child, self.settings), daemon=True)
                self.process.start()
                child.close()
                self._receive(min(deadline, time.monotonic()+self.settings.startup_timeout))
            if operation == 'ready':
                return {'status': 'initialized', 'inference_verified': False}
            self.pipe.send((operation, payload))
            return self._receive(deadline)
        except GatewayFailure:
            self.close()
            raise
        except Exception:
            self.close()
            raise GatewayFailure(502, 'aoi_worker_unavailable') from None

    async def execute(self, operation, payload=None):
        if self.settings.missing():
            raise GatewayFailure(503, 'aoi_configuration_missing')
        if self.lock.locked():
            raise GatewayFailure(429, 'aoi_gateway_busy')
        async with self.lock:
            pending = asyncio.create_task(asyncio.to_thread(self._call, operation, payload or {}))
            try:
                return await asyncio.shield(pending)
            except asyncio.CancelledError:
                # Keep the serial slot until the bounded worker call completes;
                # cancellation must not allow a second credential session/call.
                # Disconnect and server shutdown may cancel the same task twice.
                # Neither may release this slot while its thread still uses IPC.
                while not pending.done():
                    try:
                        await asyncio.shield(pending)
                    except asyncio.CancelledError:
                        continue
                    except Exception:
                        break
                if pending.done() and not pending.cancelled():
                    pending.exception()  # Consume failures after a disconnected request.
                raise
