"""Reviewed connector inventory, not a generic dynamic plugin executor.

Library importability does not imply PMem registration, scheduling or publication.
Keep optional SDKs out of baseline service dependencies until an adapter exists.
"""
from importlib.metadata import PackageNotFoundError, version
import os
from backend.depo_platform.semantica_ingestors import INGESTORS, load_ingestor

NAMES = INGESTORS
NATIVE = {
    'File': ('#/import', 'Retained uploads and format-specific parsers'),
    'XML': ('#/import', 'Engineering XML parsing and approved XML analytics jobs'),
    'Ontology': ('#/ontology', 'RDFLib parsing and Semantica structural validation'),
}


def capabilities():
    try:
        installed = version('semantica')
    except PackageNotFoundError:
        installed = None
    rows = []
    for name in NAMES:
        wired = name not in NATIVE
        native = NATIVE.get(name)
        rows.append({
            'id': name.lower(), 'name': name + 'Ingestor',
            'integration': 'configured-adapter' if wired else 'native-workflow' if native else 'not-integrated',
            'configurable': wired,
            'workspace': '#/admin' if wired else native[0] if native else None,
            'description': ('Bounded HTTP(S) GET acquisition with server-referenced credentials' if name=='REST' else 'Worker acquisition from operator-configured profiles and resource aliases; requires the matching SDK and source access') if wired else native[1],
            'job_type': ('rest-source-ingest' if name=='REST' else 'registered-source-ingest') if wired else None,
            'postgres_namespace': ('rest_sources' if name=='REST' else 'connector_sources') if wired else None,
            'storage': 'depo_registry(namespace, key, value)' if wired else None,
            'runtime_profile': 'ontology (isolated) or shared' if wired else None,
            'installation': 'semantica==0.6.7 in shared/ontology locks; bounded child uses the semantic runtime' if wired else 'Optional adapter and dependency review required; library presence alone does not enable acquisition',
        })
    return {'contract': 'ingestor-capabilities-v1', 'semantica_version': installed,
            'acquisition_runtime': 'ontology' if os.getenv('DEPO_SERVICE_RUNTIME_MODE', '').strip().lower() == 'isolated' else 'shared',
            'runtime_probe': 'not_run', 'ingestors': rows}


def check_required_adapter():
    # Exercise the lazy export missing from a service OpenAPI/import-only smoke.
    RESTIngestor = load_ingestor('REST')
    if not callable(getattr(RESTIngestor, 'ingest_endpoint', None)):
        raise RuntimeError('Semantica RESTIngestor contract is unavailable')
    return {'status': 'ok', 'adapter': 'RESTIngestor'}


def check_acquisition_runtime():
    import subprocess
    import json
    from pathlib import Path
    from .rest_sources import _worker_command
    result = subprocess.run(_worker_command() + ['--check'], capture_output=True,
                            text=True, timeout=20, cwd=str(Path(__file__).resolve().parents[2]),
                            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    lines = [line[12:] for line in result.stdout.splitlines() if line.startswith('DEPO_RESULT:')]
    if result.returncode or not lines or json.loads(lines[-1]).get('status') != 'ok':
        raise RuntimeError('Configured REST acquisition runtime failed its adapter import check')
    return {'status': 'ok', 'adapter': 'RESTIngestor', 'execution': 'bounded-child'}


if __name__ == '__main__':
    import json
    print(json.dumps(check_required_adapter()))
