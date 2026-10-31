"""Immutable PostgreSQL source registrations and bounded Semantica acquisition.

Acquisition retains records; it does not assert semantic validity or publish.
Outbound credentials are dedicated server environment references, never API keys
from DEPO's one-way credential verification table.
"""
import ipaddress
import json
import os
import re
import socket
import time
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit

from backend.mesh_store import PostgresRegistry
from backend.artifact_store import ArtifactStore

store = PostgresRegistry('rest_sources')
MAX_BYTES = 2 * 1024 * 1024
FETCH_TIMEOUT_SECONDS = 20


def endpoint_url(value):
    parts = urlsplit(value)
    if parts.scheme not in {'http', 'https'} or not parts.hostname or parts.username or parts.password or parts.query or parts.fragment:
        raise ValueError('Use an HTTP(S) endpoint without credentials, query string or fragment')
    if parts.port not in (None, 443 if parts.scheme == 'https' else 80):
        raise ValueError('REST sources use the standard HTTP or HTTPS port')
    hosts = {host.strip().lower() for host in os.getenv('DEPO_REST_ALLOWED_HOSTS', '').split(',') if host.strip()}
    if parts.hostname.lower() not in hosts:
        raise ValueError('Endpoint host is not in server DEPO_REST_ALLOWED_HOSTS')
    return value


def register(payload, actor):
    allowed = {'source_id', 'name', 'endpoint', 'credential_ref', 'auth_header', 'records_path', 'target_model', 'approval_token', 'approved_by'}
    if set(payload) - allowed:
        raise ValueError('Unsupported REST source fields')
    if any(not isinstance(value, str) for value in payload.values()):
        raise ValueError('REST source fields must be strings')
    source_id = str(payload.get('source_id', ''))
    if not re.fullmatch(r'[a-z][a-z0-9-]{2,62}', source_id):
        raise ValueError('Source ID must be 3–63 lowercase letters, digits or hyphens')
    record = {key: str(payload.get(key) or '').strip() for key in ('name', 'endpoint', 'credential_ref', 'records_path', 'target_model')}
    if not record['name'] or any(len(value) > 500 for value in record.values()):
        raise ValueError('A source name is required; fields must be at most 500 characters')
    endpoint_url(record['endpoint'])
    if record['credential_ref'] and not re.fullmatch(r'DEPO_REST_SECRET_[A-Z0-9_]{1,64}', record['credential_ref']):
        raise ValueError('Use a dedicated DEPO_REST_SECRET_ environment reference')
    record['auth_header'] = payload.get('auth_header') or 'Authorization'
    if record['auth_header'] not in {'Authorization', 'X-API-Key', 'api-key'}:
        raise ValueError('Choose Authorization, X-API-Key or api-key authentication header')
    if record['records_path'] and not re.fullmatch(r'[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+)*', record['records_path']):
        raise ValueError('Records path must be dot-separated object keys, for example data.items')
    from .job_definitions import now
    return store.create(source_id, {**record, 'source_id': source_id, 'created_by': actor, 'created_at': now(), 'kind': 'rest'})


def fetch(source, *, preview=False):
    """Bound DNS, connect and body reads in a killable process on Windows too."""
    return _isolated_fetch(source, preview=preview)


def _worker_command():
    return [sys.executable, '-m', 'backend.data_pipeline_service.rest_fetch_worker']


def _isolated_fetch(source, *, preview=False):
    from backend.depo_platform.operations import current_operation, remaining_seconds
    context = current_operation()
    timeout = min(FETCH_TIMEOUT_SECONDS, remaining_seconds(context.deadline_at)) if context else FETCH_TIMEOUT_SECONDS
    process = subprocess.Popen(_worker_command(), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, text=True, encoding='utf-8', cwd=str(Path(__file__).resolve().parents[2]),
        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    try:
        output, _ = process.communicate(json.dumps({'source': source, 'preview': preview}), timeout=timeout)
    except subprocess.TimeoutExpired:
        process.kill()
        process.communicate()
        raise ValueError('REST acquisition exceeded its absolute time limit') from None
    except BaseException:
        process.kill(); process.communicate()
        raise
    if process.returncode == 124:
        raise ValueError('REST acquisition exceeded its absolute time limit')
    try:
        message = json.loads(next(line[12:] for line in reversed(output.splitlines()) if line.startswith('DEPO_RESULT:')))
    except (ValueError, StopIteration):
        raise ValueError('REST acquisition worker returned no usable result') from None
    if process.returncode or 'error' in message:
        raise ValueError(message.get('error') or 'REST acquisition failed')
    return message['result']


def _fetch_in_process(source, *, preview=False):
    from semantica.ingest import RESTIngestor
    endpoint = endpoint_url(source['endpoint'])  # recheck operator policy on every run
    host = urlsplit(endpoint).hostname
    addresses = socket.getaddrinfo(host, 443 if urlsplit(endpoint).scheme == 'https' else 80, type=socket.SOCK_STREAM)
    for address in addresses:
        ip = ipaddress.ip_address(address[4][0])
        if not ip.is_global:
            raise ValueError('Endpoint resolves to a disallowed network address')
    credential = source.get('credential_ref')
    secret = os.getenv(credential, '') if credential else ''
    if credential and (not secret or '\r' in secret or '\n' in secret):
        raise ValueError('External source credential reference is not configured on this server')
    ingestor = RESTIngestor(config={'timeout': (5, 10), 'max_retries': 0, 'allow_private_ips': False})
    ingestor.session.trust_env = False
    deadline = time.monotonic() + 20

    def bounded_response(response, *args, **kwargs):
        try:
            if 300 <= response.status_code < 400:
                raise ValueError('REST redirects are disabled; register the final endpoint')
            content = bytearray()
            for chunk in response.iter_content(65536):
                content.extend(chunk)
                if len(content) > MAX_BYTES or time.monotonic() > deadline:
                    raise ValueError('REST response exceeds the 2 MiB or time limit')
            response._content = bytes(content)
            response._content_consumed = True
        finally:
            response.close()
        return response

    try:
        header = source.get('auth_header') or 'Authorization'
        if header not in {'Authorization', 'X-API-Key', 'api-key'}:
            raise ValueError('Invalid source authentication header')
        result = ingestor.ingest_endpoint(endpoint, method='GET', stream=True,
            headers={header: ('Bearer ' + secret) if header == 'Authorization' else secret} if secret else {}, hooks={'response': bounded_response})
        records = result.data
        for key in filter(None, source.get('records_path', '').split('.')):
            if not isinstance(records, dict) or key not in records:
                raise ValueError('Configured records path is absent from the response')
            records = records[key]
        if not isinstance(records, list) or len(records) > 1000 or any(not isinstance(row, dict) for row in records):
            raise ValueError('Response must contain an array of at most 1000 record objects')
        return {'records': records[:10] if preview else records, 'record_count': len(records), 'preview_only': preview}
    except ValueError:
        raise
    except Exception:
        # Provider exceptions can include request headers or response bodies.
        raise ValueError('REST retrieval failed; check endpoint, credentials and server connectivity') from None
    finally:
        ingestor.session.close()


def execute(runner, payload, *, correlation_id):
    source = store.get(str(payload.get('source_id') or ''))
    if not source:
        raise ValueError('Registered REST source was not found')
    result = fetch(source)
    artifact = ArtifactStore().ingest_bytes(json.dumps(result['records'], ensure_ascii=False).encode(),
        filename=source['source_id'] + '.json', kind='rest-source-records', media_type='application/json',
        provenance={'source_id': source['source_id'], 'endpoint': source['endpoint'], 'target_model': source['target_model'], 'correlation_id': correlation_id})
    return {'status': 'completed', 'counts': {'records': result['record_count']},
            'partition_artifacts': {'source': artifact['artifact_id']}, 'source_id': source['source_id'],
            'semantic_validation': 'not_assessed', 'publication': 'not_attempted'}
