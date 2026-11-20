"""Bounded source-name presentation shared by processing and change summaries."""
from functools import lru_cache
from pathlib import Path
from backend.artifact_store import ArtifactStore


@lru_cache(maxsize=512)
def _source_filename(root, artifact_id):
    metadata, _ = ArtifactStore(Path(root)).resolve(artifact_id)
    if not str(metadata.get('kind', '')).startswith('source-'):
        return ''
    return str(metadata.get('filename') or '').replace('\\', '/').rsplit('/', 1)[-1][:240]


def source_name(record):
    if record.get('source_name'):
        return str(record['source_name'])[:240]
    manifest = record.get('input_manifest') or {}
    artifacts = manifest.get('artifact_ids') or []
    if not artifacts:
        return ''
    root = str(ArtifactStore().root)
    names = []
    for identifier in artifacts[:8]:
        if identifier == manifest.get('raw_payload_artifact_id'):
            continue
        try:
            name = _source_filename(root, identifier)
        except (ValueError, OSError, TypeError):
            continue
        if name and name not in names:
            names.append(name)
    return ' + '.join(names)[:240]


def present(record):
    name = source_name(record)
    return {**record, 'source_name': name} if name else record
