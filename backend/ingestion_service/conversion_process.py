"""Bound engineering conversion in a terminable child process."""
import pickle
from pathlib import Path
import subprocess
import sys
from backend.depo_platform.network import bounded_timeout_seconds


def convert_engineering(**inputs):
    total = bounded_timeout_seconds('ENGINEERING_WORKFLOW_TIMEOUT_SECONDS', default=300, maximum=3600)
    timeout = min(bounded_timeout_seconds('ENGINEERING_CONVERSION_TIMEOUT_SECONDS', default=180, maximum=900), max(1, total - 30))
    payload = pickle.dumps(inputs, protocol=pickle.HIGHEST_PROTOCOL)
    try:
        result = subprocess.run([sys.executable, '-m', 'backend.ingestion_service.conversion_process'],
            input=payload, capture_output=True, timeout=timeout, cwd=str(Path(__file__).resolve().parents[2]))
    except subprocess.TimeoutExpired as exc:
        raise ValueError('Engineering conversion timed out; its worker was terminated. Narrow the schema set or adjust ENGINEERING_CONVERSION_TIMEOUT_SECONDS') from exc
    if result.returncode != 0:
        raise ValueError('Engineering conversion worker failed; check installed backend dependencies')
    if len(result.stdout) > 32 * 1024 * 1024: raise ValueError('Engineering conversion result exceeds 32 MiB')
    value = pickle.loads(result.stdout)  # trusted child output, never uploaded input
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
    sys.stdout.buffer.write(pickle.dumps(value, protocol=pickle.HIGHEST_PROTOCOL))
