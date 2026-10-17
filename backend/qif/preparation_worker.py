"""Deadline-isolated pure schema preparation using the same registered agent tools."""
import os
import pickle
import threading
import subprocess
import sys
import time
from pathlib import Path
from tempfile import TemporaryDirectory
from backend.depo_platform.execution_guard import ensure_execution_allowed
from backend.depo_platform.operations import current_operation
from backend.depo_platform.network import bounded_timeout_seconds


def run_stage(stage, **arguments):
    budget = bounded_timeout_seconds('QIF_TASK_TIMEOUT_SECONDS', default=900, maximum=86400)
    operation = current_operation()
    if operation:
        budget = operation.timeout(budget)
    deadline = time.monotonic() + budget
    ensure_execution_allowed()
    with TemporaryDirectory(prefix='depo-qif-stage-') as directory:
        result_path = Path(directory) / 'result.pickle'
        payload = pickle.dumps((stage, arguments, time.time() + budget), protocol=pickle.HIGHEST_PROTOCOL)
        process = subprocess.Popen([sys.executable, '-m', 'backend.qif.preparation_worker', str(result_path)],
            stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            cwd=str(Path(__file__).resolve().parents[2]), **({'creationflags': subprocess.CREATE_NO_WINDOW} if sys.platform == 'win32' else {}))
        try:
            first = True
            while True:
                ensure_execution_allowed()
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError('Schema preparation exceeded its deadline; worker terminated')
                try:
                    process.communicate(payload if first else None, timeout=min(.1, remaining))
                    break
                except subprocess.TimeoutExpired:
                    first = False
            ensure_execution_allowed()
            if time.monotonic() >= deadline:
                raise TimeoutError('Schema preparation exceeded its deadline')
            if process.returncode != 0 or not result_path.is_file():
                raise RuntimeError('Schema preparation worker failed; inspect the retained source schema')
            if result_path.stat().st_size > 128 * 1024 * 1024:
                raise ValueError('Schema preparation result exceeds the 128 MiB worker response limit')
            # This pickle is produced only by our child program in a private
            # temporary directory. Uploaded content is never unpickled.
            result = pickle.loads(result_path.read_bytes())
            if result.get('error'):
                raise ValueError(result['error'])
            ensure_execution_allowed()
            if time.monotonic() >= deadline:
                raise TimeoutError('Schema preparation exceeded its deadline during reconstruction')
            return result['value']
        finally:
            if process.poll() is None:
                process.kill()
            process.communicate(timeout=5)


def main():
    stage, arguments, deadline = pickle.loads(sys.stdin.buffer.read())
    remaining = deadline - time.time()
    if remaining <= 0:
        raise SystemExit(124)
    # Retain an independent deadline even if the service is forcibly stopped
    # before its parent-side finally block can terminate this pure CPU worker.
    timer = threading.Timer(remaining, lambda: os._exit(124))
    timer.daemon = True
    timer.start()
    try:
        from .agent_registry import registry
        tools = registry.resolve_tools('SchemaSet_Ontology')
        if stage == 'inspect':
            value = tools['inspect_schema_set'](arguments['paths'])
        elif stage == 'validate':
            from .ontology_builder import validate_schema_set
            value = validate_schema_set(arguments['inspection'], arguments['paths'])
        elif stage == 'generate':
            value = tools['build_ontology_turtle'](arguments['inspection'], arguments['prefix'])
        else:
            raise ValueError('Unknown schema preparation stage')
        result = {'value': value}
    except Exception as exc:
        result = {'error': type(exc).__name__ + ': ' + str(exc)}
    try:
        Path(sys.argv[1]).write_bytes(pickle.dumps(result, protocol=pickle.HIGHEST_PROTOCOL))
    finally:
        timer.cancel()


if __name__ == '__main__':
    main()
