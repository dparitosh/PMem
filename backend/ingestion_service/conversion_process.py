"""Bound engineering conversion in a terminable child process."""
import pickle
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
from functools import lru_cache
from backend.depo_platform.network import bounded_timeout_seconds


class ResultLimitExceeded(ValueError):
    pass


class BoundedResultWriter:
    def __init__(self, stream, limit):
        self.stream, self.limit, self.written = stream, limit, 0

    def write(self, content):
        if self.written + len(content) > self.limit:
            raise ResultLimitExceeded()
        count = self.stream.write(content)
        self.written += count
        return count


def conversion_result_limit():
    name = 'ENGINEERING_CONVERSION_MAX_RESULT_BYTES'
    try:
        limit = int(os.getenv(name, str(256 * 1024 * 1024)))
        if not 1 <= limit <= 1024 * 1024 * 1024:
            raise ValueError()
        return limit
    except (TypeError, ValueError):
        raise ValueError(f'{name} must be an integer between 1 and 1073741824') from None


@lru_cache(maxsize=1)
def conversion_slots():
    try:
        capacity = int(os.getenv('ENGINEERING_CONVERSION_MAX_CONCURRENCY', '2'))
        if not 1 <= capacity <= 8:
            raise ValueError()
    except ValueError:
        raise ValueError('ENGINEERING_CONVERSION_MAX_CONCURRENCY must be between 1 and 8') from None
    return threading.BoundedSemaphore(capacity)


def convert_engineering(**inputs):
    # Generic HTTP capacity does not bound expensive parser subprocesses.
    # Reject before spawning rather than queueing dozens of large RDF jobs.
    slots = conversion_slots()
    if not slots.acquire(blocking=False):
        raise RuntimeError('Engineering conversion capacity is busy; retry the same schema set after active conversions finish')
    try:
        return _convert_engineering(**inputs)
    finally:
        slots.release()


def _convert_engineering(**inputs):
    from backend.depo_platform.network import engineering_workflow_timeout_seconds
    total = engineering_workflow_timeout_seconds()
    timeout = min(bounded_timeout_seconds('ENGINEERING_CONVERSION_TIMEOUT_SECONDS', default=180, maximum=900), max(1, total - 30))
    payload = pickle.dumps(inputs, protocol=pickle.HIGHEST_PROTOCOL)
    limit = conversion_result_limit()
    # Standards such as AP242 can legitimately generate more than 32 MiB.
    # Spool child output to disk and check its size before decoding rather than
    # retaining both a captured byte string and its decoded object in memory.
    with tempfile.TemporaryFile() as output, tempfile.TemporaryFile() as errors:
        try:
            result = subprocess.run([sys.executable, '-m', 'backend.ingestion_service.conversion_process'],
                input=payload, stdout=output, stderr=errors, timeout=timeout,
                cwd=str(Path(__file__).resolve().parents[2]))
        except subprocess.TimeoutExpired as exc:
            raise ValueError('Engineering conversion timed out; its worker was terminated. Narrow the schema set or adjust ENGINEERING_CONVERSION_TIMEOUT_SECONDS') from exc
        if result.returncode == 74:
            raise ValueError(f'Engineering conversion result exceeds ENGINEERING_CONVERSION_MAX_RESULT_BYTES={limit}; narrow the schema set or increase the configured limit within available server memory. No ontology was registered.')
        if result.returncode != 0:
            raise ValueError('Engineering conversion worker failed; check installed backend dependencies')
        size = output.seek(0, 2)
        if size > limit:
            raise ValueError(f'Engineering conversion result is {size} bytes, exceeding ENGINEERING_CONVERSION_MAX_RESULT_BYTES={limit}. Increase that server setting within available memory or narrow the schema set; no ontology was registered.')
        output.seek(0)
        try:
            value = pickle.load(output)  # trusted child output, never uploaded input
        except (EOFError, pickle.UnpicklingError):
            raise ValueError('Engineering conversion worker returned an incomplete result; no ontology was registered') from None
    if not value['ok']: raise ValueError(value['message'])
    return value['result']


if __name__ == '__main__':
    from contextlib import redirect_stdout
    inputs = pickle.loads(sys.stdin.buffer.read())
    try:
        with redirect_stdout(sys.stderr):
            from .schema_conversion import EngineeringSchemaConverter
            value = {'ok':True,'result':EngineeringSchemaConverter().convert(**inputs)}
    except ValueError as exc:
        value = {'ok':False,'message':str(exc)[:2000]}
    try:
        pickle.dump(value, BoundedResultWriter(sys.stdout.buffer, conversion_result_limit()), protocol=pickle.HIGHEST_PROTOCOL)
    except ResultLimitExceeded:
        raise SystemExit(74)
