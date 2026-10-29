"""Explicit, offline application reset. Never drops a PostgreSQL schema.

Only the dedicated maintenance host may execute this operation. Ordinary
service startup cannot enable it; workers and the publication poller must stop.
Cross-store failures are journalled and never advertised as an atomic reset.
"""
import hashlib
import json
import logging
import os
import re
from pathlib import Path
import shutil
import uuid
from datetime import datetime, timezone

logger = logging.getLogger(__name__)
PRESERVED = ('browser_credential_sessions', 'maintenance_state', 'admin_cleanup_runs_v1',
             'vanilla_reset_receipts_v1', 'sparql_federation_peers', 'ontology_semantic_policies')
TABLES = ('depo_metadata_outbox', 'depo_metadata_events', 'depo_metadata_assets',
          'depo_chat_messages', 'depo_runtime_state', 'depo_rate_limits')
DATA_FOLDERS = ('artifacts', 'products', 'ontology_service', 'domain_models', 'business_object_models', 'parser_outputs')


def assert_isolated(root):
    if os.getenv('DEPO_VANILLA_MAINTENANCE') != 'true':
        raise ValueError('Enter isolated reset maintenance using infra/windows/open-vanilla-maintenance.ps1 first. Normal services must be stopped.')
    import psutil
    root = Path(root).resolve()
    for process in psutil.process_iter(['pid', 'name']):
        if process.pid == os.getpid() or 'python' not in (process.info['name'] or '').lower():
            continue
        try:
            executable = Path(process.exe()).resolve()
            command = process.cmdline()
            owned = executable.is_relative_to(root) or Path(process.cwd()).resolve() == root
            if not owned:
                continue
            # A static frontend can remain available for the maintenance page.
            if 'backend.depo_platform.frontend_server' in command:
                continue
            raise ValueError('Another application Python process is running. Stop all application services/workers before reset.')
        except psutil.NoSuchProcess:
            continue
        except psutil.AccessDenied as exc:
            raise ValueError('Cannot verify Python process ownership. Run maintenance from an authorized Windows session.') from exc


def storage_paths(root):
    root = Path(root).absolute()
    candidates = [root / 'uploads', root / 'ontology_uploads', *(root / 'data' / name for name in DATA_FOLDERS)]
    external_paths = set()
    configured_artifacts = os.getenv('ARTIFACT_STORAGE', '')
    artifact_root = Path(configured_artifacts) if configured_artifacts else root / 'data/artifacts'
    if not artifact_root.is_absolute():
        artifact_root = root / artifact_root
    if artifact_root.resolve() != (root / 'data/artifacts').resolve():
        # A separately configured artifact volume is supported only in the
        # application's content-addressed layout. Never remove its root or
        # unrelated siblings, and never infer ownership from a folder name.
        if any(item.is_symlink() or getattr(item, 'is_junction', lambda: False)() for item in (artifact_root, *artifact_root.parents)):
            raise ValueError('Configured artifact store contains a link or junction')
        if artifact_root.exists():
            if any(item.name not in {'sha256', 'products'} for item in artifact_root.iterdir()):
                raise ValueError('Configured artifact store contains unrecognized entries; an operator-reviewed reset plan is required')
            for directory in (artifact_root / 'sha256').glob('*'):
                metadata = directory / 'metadata.json'
                if directory.is_symlink() or getattr(directory, 'is_junction', lambda: False)() or metadata.is_symlink() or not directory.is_dir() or not re.fullmatch('[0-9a-f]{64}', directory.name) or not metadata.is_file() or metadata.stat().st_size > 1024 * 1024:
                    raise ValueError('Configured artifact store contains unverified content')
                record = json.loads(metadata.read_text(encoding='utf-8'))
                if not isinstance(record, dict) or record.get('sha256') != directory.name or record.get('legal_hold', False) is not False:
                    raise ValueError('Configured artifact metadata is invalid or under legal hold')
            products = artifact_root / 'products'
            if products.exists():
                if not products.is_dir() or any(item.name != 'packages' for item in products.iterdir()):
                    raise ValueError('Configured product storage contains unrecognized entries')
                for product in (products / 'packages').glob('*'):
                    if not product.is_dir() or product.is_symlink():
                        raise ValueError('Configured product storage contains unverified packages')
                    for version in product.iterdir():
                        manifest = version / 'manifest.json'
                        if not manifest.is_file() or manifest.is_symlink() or manifest.stat().st_size > 8 * 1024 * 1024:
                            raise ValueError('Configured product storage contains unverified packages')
                        package = json.loads(manifest.read_text(encoding='utf-8'))
                        if not isinstance(package, dict) or package.get('product_id') != product.name or package.get('version') != version.name or not re.fullmatch('[0-9a-f]{64}', str(package.get('publication_digest', ''))) or package.get('legal_hold', False) is not False:
                            raise ValueError('Configured product package identity is invalid or under legal hold')
        external_paths = {artifact_root / 'sha256', artifact_root / 'products'}
        candidates.extend(sorted(external_paths))
    # Custom storage is intentionally refused until its ownership is explicit.
    defaults = {'ONTOLOGY_SERVICE_STORAGE': root / 'data/ontology_service',
                'WORKFLOW_ARTIFACT_ROOT': root / 'uploads/workflow_artifacts',
                'ONTOLOGY_STORAGE_DIR': root / 'ontology_uploads',
                'DATA_PRODUCT_STORAGE': artifact_root / 'products' if configured_artifacts else root / 'data/products',
                'QIF_TASK_ROOT': root / 'uploads/qif_workflows'}
    if os.getenv('QIF_TASK_STORAGE', 'local').lower() != 'local' or os.getenv('DEPO_SPARK_OUTPUT_ROOT'):
        raise ValueError('Shared QIF or Spark output storage requires an operator-reviewed reset plan; no data was deleted.')
    for key, expected in defaults.items():
        configured = Path(os.environ[key]) if os.getenv(key) else expected
        if not configured.is_absolute(): configured = root / configured
        if os.getenv(key) and configured.resolve() != expected.resolve():
            raise ValueError(f'Custom {key} requires an operator-reviewed reset plan; no data was deleted.')
    for path in candidates:
        # Junctions and symlinks can escape a verified parent on Windows.
        for item in (path, *path.parents):
            if item == root.parent:
                break
            if item.is_symlink() or getattr(item, 'is_junction', lambda: False)():
                raise ValueError('Reset storage contains a link or junction')
        if (not path.resolve().is_relative_to(root.resolve()) and path not in external_paths) or path.resolve() == root.resolve():
            raise ValueError('Reset storage escaped the application directory')
        if path.exists():
            for item in path.rglob('*'):
                if item.is_symlink() or getattr(item, 'is_junction', lambda: False)():
                    raise ValueError('Reset storage contains a link or junction')
    return candidates


def inventory(db, root):
    paths = storage_paths(root)
    with db.cursor() as cursor:
        cursor.execute('SELECT namespace,count(*) FROM depo_registry WHERE NOT(namespace=ANY(%s)) GROUP BY namespace ORDER BY namespace', (list(PRESERVED),))
        namespaces = dict(cursor.fetchall())
        cursor.execute("SELECT count(*) FROM depo_registry WHERE NOT(namespace=ANY(%s)) AND lower(coalesce(value->>'legal_hold','false')) <> 'false'", (list(PRESERVED),))
        if cursor.fetchone()[0]:
            raise ValueError('Records under legal hold prevent vanilla reset')
        cursor.execute("SELECT count(*) FROM depo_metadata_assets WHERE lower(coalesce(value->>'legal_hold','false')) <> 'false'")
        if cursor.fetchone()[0]:
            raise ValueError('Metadata under legal hold prevents vanilla reset')
        tables = {}
        for table in TABLES:
            cursor.execute(f'SELECT count(*) FROM {table}')  # Static table allowlist.
            tables[table] = cursor.fetchone()[0]
    files = {str(path.relative_to(root)) if path.is_relative_to(root) else str(path):
             sum(1 for item in path.rglob('*') if item.is_file()) for path in paths}
    payload = {'registry_records': namespaces, 'table_rows': tables, 'retained_files': files,
               'preserved': ['service credentials and credential audit', 'browser access', 'schema migrations and indexes',
                             'embedded foundation and reasoner', 'environment files', 'reset receipts and installation logs'],
               'graph': 'All application graph nodes and relationships; operational indexes retained.'}
    payload['preview_digest'] = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    return payload


def reset(db, root, *, expected_digest, graph_reset, isolation=assert_isolated):
    """Caller holds the exclusive ontology-maintenance lock, in isolated mode."""
    root = Path(root)
    isolation(root)
    plan = inventory(db, root)
    if expected_digest != plan['preview_digest']:
        raise ValueError('Reset inventory changed. Preview again before confirming.')
    receipt = {'run_id': 'vanilla-' + uuid.uuid4().hex, 'status': 'running',
               'started_at': datetime.now(timezone.utc).isoformat(), 'preview': plan,
               'phases': {}, 'automatic_replay_allowed': False}
    directory = root / 'logs/vanilla-reset'
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / (receipt['run_id'] + '.json')
    active = directory / 'active.json'
    def save():
        temporary = target.with_suffix('.tmp')
        with temporary.open('w', encoding='utf-8') as handle:
            json.dump(receipt, handle, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
    save()  # A durable receipt is mandatory before the first deletion.
    with active.open('w', encoding='utf-8') as handle:
        json.dump({'run_id': receipt['run_id'], 'status': 'requires_verification'}, handle)
        handle.flush()
        os.fsync(handle.fileno())
    try:
        result = graph_reset()
        if str(result.get('status', '')).upper() != 'SUCCESS':
            raise RuntimeError('Graph reset did not verify completion')
        receipt['phases']['graph'] = 'completed'
        save()
        # Isolated host prevents workers and other services from restoring old
        # state. The maintenance middleware rejects all non-reset mutations.
        with db.transaction(), db.cursor() as cursor:
            for table in plan['table_rows']:
                cursor.execute(f'DELETE FROM {table}')
            cursor.execute('DELETE FROM depo_registry WHERE NOT(namespace=ANY(%s))', (list(PRESERVED),))
        receipt['phases']['postgres'] = 'completed'
        save()
        for path in storage_paths(root):
            if path.exists():
                shutil.rmtree(path)
            path.mkdir(parents=True, exist_ok=True)
        receipt['phases']['files'] = 'completed'
        from .maintenance import invalidate_shared_caches
        invalidate_shared_caches()
        receipt['status'] = 'completed'
    except Exception as exc:
        logger.exception('Vanilla reset incomplete run_id=%s', receipt['run_id'])
        receipt['status'] = 'partial'
        receipt['error_type'] = type(exc).__name__
        receipt['message'] = 'Reset is incomplete. Keep maintenance isolated and inspect the receipt and service log before recovery.'
    receipt['finished_at'] = datetime.now(timezone.utc).isoformat()
    save()
    if receipt['status'] == 'completed':
        active.unlink()
    return receipt
