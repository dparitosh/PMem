"""Plan and stage immutable ontology upgrade drafts; never approve or publish."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import time
from pathlib import Path
from backend.depo_platform.ontology_namespace import ontology_prefix
from backend.depo_platform.upload_limits import ontology_upload_limit
REVISION = 2


class UpgradeInventoryUnavailable(RuntimeError):
    pass


def inventory_endpoint():
    from backend.depo_platform.service_urls import service_url
    host = os.getenv('DEPO_SERVICE_HOST', '').strip() or '127.0.0.1'
    if host == '0.0.0.0': host = '127.0.0.1'
    if host == '::': host = '[::1]'
    if ':' in host and not host.startswith('['): host = '[' + host + ']'
    endpoint = service_url('ONTOLOGY_SERVICE_URL', f'http://{host}:8011/api/v1')
    return endpoint if endpoint.endswith('/api/v1') else endpoint + '/api/v1'


def inventory_page(client, endpoint, headers, offset):
    """Retry bounded inventory reads only; never retry a registration write."""
    import httpx
    deadline = time.monotonic() + 30
    for attempt in range(3):
        remaining = deadline - time.monotonic()
        if remaining <= 0: break
        try:
            response = client.get(endpoint + '/ontologies', headers=headers,
                params={'limit':200,'offset':offset}, timeout=httpx.Timeout(min(10,remaining), connect=min(5,remaining), pool=min(5,remaining)))
            if response.status_code not in {502,503,504}:
                if response.status_code in {401,403}:
                    raise UpgradeInventoryUnavailable('Ontology inventory access was rejected. Verify GRAPH_READ_TOKEN and the configured ontology service credentials; do not rotate keys or resubmit publications to resolve this read failure.')
                response.raise_for_status()
                return response.json()
        except (httpx.ConnectError, httpx.TimeoutException):
            pass
        if attempt < 2:
            time.sleep(min(attempt+1, max(0,deadline-time.monotonic())))
    raise UpgradeInventoryUnavailable(
        f'Ontology inventory could not be reached at {endpoint}. Verify ONTOLOGY_SERVICE_URL matches DEPO_SERVICE_HOST and the running ontology listener (normally port 8011). '
        'Inspect logs/windows-services/ontology.err.log and ontology.out.log, then rerun the same repository-root update/install command. Existing publications and the previous review plan are retained.')

def digest(content):
    return hashlib.sha256(content).hexdigest()

def read_source(metadata, root):
    """Read only a retained source, bounded and within its configured storage."""
    from backend.artifact_store import ArtifactStore
    name = metadata.get('source_filename') or metadata.get('original_filename') or ''
    artifact = (metadata.get('engineering_artifacts') or {}).get('source')
    if artifact:
        _, path = ArtifactStore().resolve(artifact)
    else:
        path = Path(metadata.get('file_path') or metadata.get('artifact_path') or '')
        stores = [Path(os.getenv('ONTOLOGY_STORAGE_DIR') or root / 'ontology_uploads'),
                  Path(os.getenv('ONTOLOGY_SERVICE_STORAGE') or root / 'data/ontology_service')]
        if not any(path.resolve().is_relative_to(store.resolve()) for store in stores):
            raise ValueError('Retained source lies outside configured ontology storage')
    with path.open('rb') as stream:
        content = stream.read(ontology_upload_limit() + 1)
    if not content or len(content) > ontology_upload_limit():
        raise ValueError('Retained source missing or above configured limit')
    if metadata.get('source_sha256') and digest(content) != metadata['source_sha256']:
        raise ValueError('Retained source digest mismatch')
    return name or path.name, content

def proposed_update(metadata, filename, content):
    if metadata.get('ontology_upgrade_revision', 0) >= REVISION:
        return None
    suffix = Path(filename).suffix.lower()
    namespace = ''
    if suffix == '.xsd':
        from defusedxml import ElementTree as ET
        namespace = ET.fromstring(content).get('targetNamespace') or ''
        reason = 'Regenerate XSD classes, hierarchy and namespace identities with current converter'
    elif suffix in {'.ttl', '.rdf', '.owl'}:
        from rdflib import Graph, URIRef
        from rdflib.namespace import RDF, OWL
        if b'<!doctype' in content.replace(b'\x00', b'').lower() or b'<!entity' in content.replace(b'\x00', b'').lower():
            raise ValueError('DTD/entities are not permitted')
        graph = Graph()
        formats = ['turtle'] if suffix == '.ttl' else ['xml', 'turtle']
        for fmt in formats:
            try:
                graph = Graph().parse(data=content, format=fmt)
                break
            except Exception:
                if fmt == formats[-1]: raise ValueError('Retained RDF syntax is invalid') from None
        declarations = sorted({str(s) for s in graph.subjects(RDF.type, OWL.Ontology) if isinstance(s, URIRef)})
        if len(declarations) != 1:
            raise ValueError('One declared ontology namespace is required for automatic prefix repair')
        namespace = declarations[0]
        reason = 'Align the default prefix with the retained ontology namespace; RDF terms unchanged'
    else:
        return None
    if not namespace:
        raise ValueError('No source namespace; manual review required')
    prefix = ontology_prefix(namespace)
    if suffix != '.xsd' and prefix == metadata.get('prefix'):
        return None
    return {'ontology_id': metadata['ontology_id'], 'old_prefix': metadata.get('prefix', ''),
            'prefix': prefix, 'namespace': namespace, 'filename': filename,
            'source_sha256': digest(content), 'reason': reason, 'status': 'review_required'}

def retained_dependencies(metadata):
    dependencies = {}
    total = 0
    directory = Path(metadata.get('file_path') or '').parent / 'schema_sources'
    for item in metadata.get('retained_schema_sources') or []:
        path = Path(item['path'])
        if not path.resolve().is_relative_to(directory.resolve()): raise ValueError('Companion source outside retained schema set')
        with path.open('rb') as stream: data = stream.read(ontology_upload_limit() + 1)
        total += len(data)
        if total > ontology_upload_limit(): raise ValueError('Companions exceed configured upload limit')
        if item.get('sha256') and digest(data) != item['sha256']: raise ValueError('Companion source digest mismatch')
        dependencies[item['relative_path']] = data
    for key, artifact in (metadata.get('engineering_artifacts') or {}).items():
        if not key.startswith('dependency:'): continue
        from backend.artifact_store import ArtifactStore
        _, path = ArtifactStore().resolve(artifact)
        with path.open('rb') as stream: data = stream.read(ontology_upload_limit() + 1)
        total += len(data)
        if total > ontology_upload_limit(): raise ValueError('Companions exceed configured upload limit')
        dependencies[key[len('dependency:'):]] = data
    return dependencies

def stage_draft(metadata, update, content, backup, client, endpoint, headers, root, dependencies):
    backup.mkdir(parents=True, exist_ok=True)
    (backup / 'metadata.json').write_text(json.dumps(metadata, indent=2), encoding='utf-8')
    (backup / 'source').write_bytes(content)
    filename = update['filename']
    if Path(filename).suffix.lower() == '.xsd':
        from backend.Services.schema_upload_paths import validate_schema_upload
        from backend.Services.owl_generation_service import OWLGenerationService
        validate_schema_upload(filename, content, dependencies)
        turtle, _ = OWLGenerationService.generate_owl(content, filename, schema_files=dependencies)
        payload = turtle.encode('utf-8')
        artifact_name = 'corrected.ttl'
    else:
        payload, artifact_name = content, filename
    # Persist the full recovery source before registering any new draft.
    for index, (name, data) in enumerate(sorted(dependencies.items())):
        (backup / ('companion-' + str(index))).write_bytes(data)
    (backup / 'companions.json').write_text(json.dumps(list(sorted(dependencies))), encoding='utf-8')
    identity = digest(json.dumps([REVISION, update, sorted((n, digest(d)) for n,d in dependencies.items())], sort_keys=True).encode())
    response = client.post(endpoint + '/ontologies/register', headers=headers,
        data={'ontology_name': str(metadata.get('ontology_name') or update['ontology_id']) + ' - upgrade review',
              'prefix': update['prefix'], 'source': 'engineering-workflow:' + identity,
              'extra_metadata': json.dumps({'ontology_upgrade_revision': REVISION, 'upgrade_from': update['ontology_id'],
                                           'upgrade_source_sha256': update['source_sha256']})},
        files={'artifact': (artifact_name, payload, 'text/turtle' if artifact_name.endswith('.ttl') else 'application/rdf+xml')})
    response.raise_for_status()
    draft = response.json()
    if draft.get('lifecycle_status') != 'draft': raise ValueError('Upgrade registration did not return a draft; inspect retained receipt')
    return {'status':'draft_staged', 'draft_id':draft['ontology_id'], 'publication':'requires_review_and_approval'}

def run(root, *, stage=False):
    import httpx
    from backend.depo_platform.network import service_bearer_headers
    root = Path(root).resolve()
    endpoint = inventory_endpoint()
    print(json.dumps({'stage':'ontology_upgrade_inventory','endpoint':endpoint}), flush=True)
    readers = service_bearer_headers('GRAPH_READ_TOKEN', service_name='ontology upgrade inventory', endpoint=endpoint)
    writers = service_bearer_headers('ONTOLOGY_APPROVAL_TOKEN', service_name='ontology upgrade drafts', endpoint=endpoint) if stage else {}
    folder = root / 'logs/installation/ontology-upgrade-v2'
    folder.mkdir(parents=True, exist_ok=True)
    records = {}
    with httpx.Client(timeout=httpx.Timeout(3600, connect=10, pool=10), trust_env=False) as client:
        offset = 0
        while True:
            page = inventory_page(client, endpoint, readers, offset)
            for metadata in page.get('ontologies', []): records[metadata['ontology_id']] = metadata
            following = page.get('next_offset')
            if following is None: break
            if not isinstance(following,int) or following <= offset: raise ValueError('Invalid ontology inventory pagination')
            offset = following
        legacy = Path(os.getenv('ONTOLOGY_STORAGE_DIR') or root / 'ontology_uploads')
        for path in legacy.glob('*/metadata.json'):
            metadata = json.loads(path.read_text(encoding='utf-8-sig'))
            if metadata.get('is_latest', True): records[metadata['ontology_id']] = metadata
        report = {'revision':REVISION, 'mode':'existing_deployment', 'items':[]}
        for identifier, metadata in sorted(records.items()):
            if metadata.get('lifecycle_status') in {'retired','deprecated','rejected'} or metadata.get('status') == 'superseded': continue
            if metadata.get('ontology_upgrade_revision',0) >= REVISION: continue
            print(json.dumps({'ontology_id':identifier,'stage':'upgrade_review'}), flush=True)
            try:
                filename, content = read_source(metadata, root)
                update = proposed_update(metadata, filename, content)
                if update is None: continue
                # Never derive a recovery path from an unchecked persisted identifier.
                dependencies = retained_dependencies(metadata)
                update['input_fingerprint'] = digest(json.dumps([REVISION, update, sorted((n,digest(d)) for n,d in dependencies.items())],sort_keys=True).encode())
                key = digest((identifier + update['input_fingerprint']).encode())[:24]
                receipt_path = folder / key / 'receipt.json'
                if receipt_path.exists():
                    try: receipt = json.loads(receipt_path.read_text())
                    except (ValueError, OSError): receipt = {}
                    if receipt.get('input_fingerprint') == update['input_fingerprint'] and receipt.get('draft_id'):
                        current = client.get(endpoint + '/ontologies/' + receipt['draft_id'], headers=readers)
                        if current.status_code == 200 and current.json().get('upgrade_from') == identifier:
                            report['items'].append(receipt)
                            continue
                        if current.status_code != 404: current.raise_for_status()
                if stage:
                    update.update(stage_draft(metadata, update, content, folder/key, client, endpoint, writers, root, dependencies))
                    temporary_receipt = receipt_path.with_suffix('.tmp')
                    temporary_receipt.write_text(json.dumps(update,indent=2),encoding='utf-8')
                    temporary_receipt.replace(receipt_path)
                report['items'].append(update)
            except Exception as exc:
                # Keep errors useful without including authenticated URLs or credentials.
                report['items'].append({'ontology_id':identifier,'status':'manual_review_required','error_type':type(exc).__name__, 'action':str(exc)[:400] if isinstance(exc, ValueError) else 'Restore retained sources or inspect service logs before retrying'})
    target = folder / 'plan.json'
    temporary = folder / 'plan.json.tmp'
    temporary.write_text(json.dumps(report,indent=2),encoding='utf-8')
    temporary.replace(target)
    print(json.dumps({'mode':'existing_deployment','review_items':len(report['items']),'plan':str(target),'manual_review_items':sum(item['status']=='manual_review_required' for item in report['items']),'published':False}))
    return report

def review_ceim_mappings(root, *, store=None, limit=5000):
    """Inventory retained AP242 run digests; never replay, approve or publish."""
    from backend.ceim.contract import contract
    from backend.mesh_store import PostgresRegistry
    if not 1 <= limit <= 5000:
        raise ValueError('CEIM upgrade inventory limit must be between 1 and 5000')
    selected = contract.mapping_pack('ap242')
    registry = store if store is not None else PostgresRegistry('data_job_runs')
    items, seen, scanned, total, active, failed = [], set(), 0, 0, 0, 0
    while scanned < limit:
        total, rows = registry.page(limit=min(100, limit-scanned), offset=scanned)
        if not rows:
            break
        scanned += len(rows)
        for row in rows:
            if not isinstance(row, dict):
                continue
            output = row.get('output_manifest') if isinstance(row.get('output_manifest'), dict) else {}
            if str(row.get('source_standard') or output.get('source_standard') or '').lower() != 'ap242':
                continue
            if row.get('status') in {'queued', 'running'}:
                active += 1
                continue
            if row.get('status') in {'failed', 'cancelled', 'canceled', 'timed_out', 'interrupted'}:
                failed += 1
                continue
            identifier = str(row.get('run_id') or '')[:256]
            if not identifier or identifier in seen:
                continue
            seen.add(identifier)
            old = output.get('mapping_digest')
            if old == selected['digest']:
                continue
            items.append({'run_id': identifier, 'run_status': str(row.get('status') or 'unknown')[:64],
                'status': 'regeneration_required' if isinstance(old, str) and old.startswith('sha256:') else 'manual_review_required',
                'action': 'Retain the original run and publication. Regenerate from the complete original AP242 source, review new PMI associations and publish through the governed workflow. Do not replay old normalized output or edit mapping provenance.',
                'publication': 'not_attempted'})
        if scanned >= total:
            break
    report = {'status': 'review_required' if items else 'no_mismatches_in_scanned_records',
        'mapping_pack': selected['id'], 'mapping_version': selected['version'], 'mapping_digest': selected['digest'],
        'coverage': {'scanned_runs': scanned, 'total_runs_observed': total, 'limit': limit,
                     'truncated': scanned < total, 'atomic_snapshot': False, 'active_ap242_runs_skipped': active, 'unsuccessful_ap242_runs_skipped': failed},
        'items': items, 'published': False,
        'limitations': 'Retained data-job metadata only; legacy imports and graphs without run metadata require manual review. Concurrent run updates can change this bounded inventory. Large batches still require supported partitioning.'}
    folder = Path(root).resolve() / 'logs/installation/ceim-upgrade-review'
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / 'plan.json'
    temporary = target.with_suffix('.tmp')
    temporary.write_text(json.dumps(report, indent=2), encoding='utf-8')
    temporary.replace(target)
    print(json.dumps({'mapping_version': selected['version'], 'review_items': len(items),
                      'plan': str(target), 'coverage': report['coverage'], 'published': False}))
    return report


def detect_deployment(root=None):
    import psycopg
    from backend.depo_platform.postgres_schema import configured_schema, connect_timeout_seconds
    url = os.getenv('DEPO_DATABASE_URL') or os.getenv('DATABASE_URL')
    if not url: raise ValueError('Database configuration is required for deployment detection')
    schema = configured_schema()
    relation = '"' + schema.replace('"','""') + '".depo_schema_migrations'
    with psycopg.connect(url, connect_timeout=connect_timeout_seconds(), options='-c statement_timeout=10000') as connection:
        with connection.cursor() as cursor:
            cursor.execute('SELECT to_regclass(%s), to_regclass(%s)', (relation, '"' + schema.replace('"','""') + '".depo_registry'))
            exists = any(value is not None for value in cursor.fetchone())
    if root is not None:
        root = Path(root)
        stores = [Path(os.getenv('ONTOLOGY_STORAGE_DIR') or root/'ontology_uploads'), Path(os.getenv('ONTOLOGY_SERVICE_STORAGE') or root/'data/ontology_service')]
        exists = exists or any(any(store.glob('*/metadata.json')) for store in stores)
    return {'mode':'existing' if exists else 'new'}

if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--root',required=True)
    parser.add_argument('--stage',action='store_true')
    parser.add_argument('--detect',action='store_true')
    parser.add_argument('--ceim-review',action='store_true')
    args=parser.parse_args()
    if args.detect: print(json.dumps(detect_deployment(args.root)))
    elif args.ceim_review: review_ceim_mappings(args.root)
    else:
        try: run(args.root,stage=args.stage)
        except UpgradeInventoryUnavailable as exc:
            print(json.dumps({'status':'failed','stage':'ontology_upgrade_inventory','action':str(exc)}), flush=True)
            raise SystemExit(1)
