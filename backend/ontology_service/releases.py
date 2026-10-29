"""Immutable human-readable release lineage over retained catalog artifacts."""
from datetime import datetime, timezone
import re

from backend.mesh_store import PostgresRegistry
from .catalog import _safe_token


class OntologyReleases:
    def __init__(self, catalog, store=None):
        self.catalog = catalog
        self.store = store if store is not None else PostgresRegistry('ontology_releases_v1')

    @staticmethod
    def version(value):
        if not isinstance(value, str) or len(value) > 32 or not re.fullmatch(r'(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)', value):
            raise ValueError('Version must be major.minor.patch without leading zeros')
        return tuple(map(int, value.split('.')))

    def describe(self, ontology_id):
        _safe_token(ontology_id, field='ontology_id')
        record = self.store.get('ontology:' + ontology_id)
        if not record:
            return {'ontology_id': ontology_id, 'release': None, 'history': []}
        family = self.store.get('family:' + record['family_id']) or {}
        try:
            current = self.catalog.artifact_digest(ontology_id) == record['artifact_sha256']
        except (ValueError, LookupError, OSError):
            current = False
        return {'ontology_id': ontology_id, 'release': record,
                'artifact_matches_release': current, 'history': family.get('releases', []),
                'compatibility_verified': False}

    def verify_artifact(self, ontology_id, digest):
        record = self.store.get('ontology:' + ontology_id)
        if record and record['artifact_sha256'] != digest:
            raise ValueError('Artifact differs from its declared release; register and review a new ontology version')
        return record

    def declare(self, ontology_id, payload, actor):
        _safe_token(ontology_id, field='ontology_id')
        family = _safe_token(payload.get('family_id'), field='family_id')
        version = payload.get('version')
        number = self.version(version)
        kind = payload.get('change_kind')
        predecessor = payload.get('predecessor_id') or None
        if predecessor is not None:
            _safe_token(predecessor, field='predecessor_id')
        notes = payload.get('change_notes')
        if not isinstance(notes, str) or not notes.strip() or len(notes) > 8000:
            raise ValueError('Change notes are required, up to 8000 characters')
        if not isinstance(actor, str) or not actor.strip():
            raise ValueError('A review identity is required')

        def operation():
            # Catalog lifecycle lock protects content/lifecycle during declaration.
            # Ontology and family locks serialize separate processes and families.
            with self.store.advisory_lock('ontology:' + ontology_id) as acquired:
                if not acquired:
                    raise ValueError('Release declaration is busy; refresh before retrying')
                with self.store.advisory_lock('family:' + family) as acquired:
                    if not acquired:
                        raise ValueError('Release family is busy; refresh before retrying')
                    metadata = self.catalog.get(ontology_id)
                    if not metadata:
                        raise LookupError('Ontology artifact not found')
                    if metadata.get('lifecycle_status') in {'retired', 'deprecated'} or metadata.get('status') == 'superseded':
                        raise ValueError('Cannot declare a retired, deprecated or superseded artifact')
                    digest = self.catalog.artifact_digest(ontology_id)
                    fields = dict(ontology_id=ontology_id, family_id=family, version=version,
                                  predecessor_id=predecessor, change_kind=kind,
                                  change_notes=notes.strip(), artifact_sha256=digest)
                    existing = self.store.get('ontology:' + ontology_id)
                    if existing:
                        if all(existing.get(k) == v for k, v in fields.items()):
                            return existing
                        raise ValueError('Ontology release is immutable; register a replacement artifact')
                    index = self.store.get('family:' + family) or {'family_id': family, 'releases': []}
                    history = index['releases']
                    if len(history) >= 1000:
                        raise ValueError('Release family history limit reached')
                    if history:
                        latest = history[-1]
                        if predecessor != latest['ontology_id']:
                            raise ValueError('Predecessor must be the latest declared release in this family')
                        previous = self.version(latest['version'])
                        if number <= previous:
                            raise ValueError('Version must increase')
                        required = 'breaking' if number[0] != previous[0] else 'additive' if number[1] != previous[1] else 'corrective'
                        if kind != required:
                            raise ValueError('Change kind must match version increment: ' + required)
                    elif predecessor is not None or kind != 'initial':
                        raise ValueError('First release requires initial change kind and no predecessor')
                    record = {**fields, 'declared_by': actor, 'declared_at': datetime.now(timezone.utc).isoformat(),
                              'compatibility_verified': False}
                    # Family history and ontology assignment commit together.
                    self.store.put_many({'ontology:' + ontology_id: record,
                                         'family:' + family: {**index, 'releases': [*history, record]}})
                    return record
        return self.catalog.with_publication_lock(ontology_id, operation)
