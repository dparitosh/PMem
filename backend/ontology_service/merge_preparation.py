"""Prepare a merge in a terminable process, including parsing and reasoning."""
import pickle
import subprocess
import sys
import time
from pathlib import Path


def prepare(service, payload):
    from backend.depo_platform.network import bounded_timeout_seconds
    from backend.depo_platform.operations import current_operation
    from backend.depo_platform.upload_limits import ontology_upload_limit
    budget = bounded_timeout_seconds('MERGE_VALIDATION_TIMEOUT_SECONDS', default=180, maximum=900)
    operation = current_operation()
    if operation: budget = operation.timeout(budget)
    started = time.monotonic()
    identifiers = payload.get('source_ontology_ids', [])
    if not isinstance(identifiers, list) or not 2 <= len(identifiers) <= 16 or not all(isinstance(key, str) and key.strip() for key in identifiers):
        raise ValueError('Select 2 to 16 distinct ontology IDs')
    identifiers = list(dict.fromkeys(key.strip() for key in identifiers))
    if len(identifiers) < 2: raise ValueError('Select at least two distinct ontology IDs')
    payload = {**payload, 'source_ontology_ids': identifiers}
    sources, total = {}, 0
    for key in identifiers:
        if service.catalog.get(key) is not None:
            metadata, content = service.catalog.read_artifact(key)
        else:
            from .domain.reasoning import OntologyReasoningService
            context = OntologyReasoningService.semantic_context(key)
            metadata = {**context['meta'], 'original_filename': context['file_path'].name}
            with context['file_path'].open('rb') as stream: content = stream.read(ontology_upload_limit() + 1)
        total += len(content)
        if total > ontology_upload_limit():
            raise ValueError('Combined merge sources exceed ONTOLOGY_MAX_UPLOAD_BYTES; partition the merge')
        sources[key] = (metadata, content)
        if time.monotonic() - started >= budget: raise ValueError('Merge source preparation exceeded its deadline')
    encoded = pickle.dumps((sources, payload), protocol=pickle.HIGHEST_PROTOCOL)
    remaining = budget - (time.monotonic() - started)
    if remaining <= 0: raise ValueError('Merge preparation exceeded its deadline')
    try:
        result = subprocess.run([sys.executable, '-m', 'backend.ontology_service.merge_preparation'],
            input=encoded, capture_output=True, timeout=remaining, cwd=str(Path(__file__).resolve().parents[2]))
    except subprocess.TimeoutExpired as exc:
        raise ValueError('Merge preparation timed out; its parsing and validation worker was terminated') from exc
    if result.returncode != 0: raise ValueError('Merge preparation worker failed; check source RDF, shapes and installed reasoning dependencies')
    response = pickle.loads(result.stdout)  # Only trusted local child output.
    if 'error' in response: raise ValueError(response['error'])
    if time.monotonic() - started > budget: raise ValueError('Merge preparation exceeded its deadline')
    return response['record']


def main():
    from contextlib import redirect_stdout
    from types import SimpleNamespace
    from .catalog import OntologyCatalog
    from .merge_service import GovernedMergeService
    from . import merge_semantics
    # This entire process is terminable. Run validation here rather than spawning
    # a grandchild that could survive termination of the preparation worker.
    merge_semantics.validate_merge = merge_semantics._validate_merge
    sources, payload = pickle.loads(sys.stdin.buffer.read())
    service = object.__new__(GovernedMergeService)
    service.catalog = SimpleNamespace(get=lambda key: sources.get(key, (None,))[0],
        read_artifact=lambda key: sources[key], _parse_ontology=OntologyCatalog._parse_ontology)
    service.registry = None
    retained = {}
    service._load = lambda: {}
    service._save = lambda values, key: retained.update(record=values[key])
    try:
        with redirect_stdout(sys.stderr): service._preview(payload)
        response = retained
    except ValueError as exc:
        response = {'error': str(exc)}
    sys.stdout.buffer.write(pickle.dumps(response, protocol=pickle.HIGHEST_PROTOCOL))


if __name__ == '__main__': main()
