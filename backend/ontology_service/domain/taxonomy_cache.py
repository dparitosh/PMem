"""Disposable local browse cache; never a source of approval or reasoning evidence."""
import gzip
import hashlib
import json
import logging
import os
import tempfile
from pathlib import Path

MAX_BYTES = 256 * 1024 * 1024
log = logging.getLogger(__name__)


def cache_identity(paths, metadata):
    digests = []
    for path in paths:
        digest = hashlib.sha256()
        with Path(path).open('rb') as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                digest.update(chunk)
        digests.append(digest.hexdigest())
    return hashlib.sha256(json.dumps([digests, metadata], sort_keys=True).encode()).hexdigest()


def read_cache(path, identity):
    try:
        if path.is_symlink() or path.stat().st_size > MAX_BYTES:
            return None
        with gzip.open(path, 'rb') as stream:
            raw = stream.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            return None
        record = json.loads(raw)
        if not isinstance(record, dict):
            return None
        payload = record.get('payload')
        if record.get('identity') != identity or not isinstance(payload, dict):
            return None
        if payload.get('extraction_source') != 'rdf' or not isinstance(payload.get('nodes'), list) or not isinstance(payload.get('edges'), list):
            return None
        return payload
    except (OSError, ValueError, EOFError):
        return None


def write_cache(path, identity, payload):
    if payload.get('extraction_source') != 'rdf':
        return
    temporary = None
    try:
        raw = json.dumps({'identity': identity, 'payload': payload}, separators=(',', ':')).encode()
        if len(raw) > MAX_BYTES or path.is_symlink():
            return
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix='.taxonomy-', suffix='.tmp', delete=False) as stream:
            temporary = Path(stream.name)
            with gzip.GzipFile(fileobj=stream, mode='wb', compresslevel=1) as compressed:
                compressed.write(raw)
        os.replace(temporary, path)
    except OSError:
        log.warning('Taxonomy browse cache could not be saved; retained ontology remains authoritative')
    finally:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                log.warning('Temporary taxonomy cache cleanup failed')
