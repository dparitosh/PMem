from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor
import copy
import threading
import pytest
from backend.mesh_store import InMemoryRegistry
from backend.ontology_service.releases import OntologyReleases


class Catalog:
    def __init__(self):
        self.hashes = {'first': 'a'*64, 'second': 'b'*64, 'third': 'c'*64}
        self.lifecycle = 'draft'
        self.lock = threading.RLock()
    def get(self, key):
        return {'ontology_id': key, 'lifecycle_status': self.lifecycle} if key in self.hashes else None
    def artifact_digest(self, key): return self.hashes[key]
    def with_publication_lock(self, key, fn):
        with self.lock: return fn()


def payload(**changes):
    return dict(family_id='AP242', version='1.0.0', change_kind='initial',
                change_notes='Initial reviewed source', **changes)


def setup():
    catalog = Catalog()
    return OntologyReleases(catalog, InMemoryRegistry()), catalog


def test_release_chain_and_retry_preserve_artifacts_and_lifecycle():
    service, catalog = setup()
    first = service.declare('first', payload(), 'reviewer')
    assert service.declare('first', payload(), 'other') == first
    second = service.declare('second', {**payload(), 'version':'1.1.0', 'change_kind':'additive', 'predecessor_id':'first'}, 'reviewer')
    assert second['compatibility_verified'] is False
    assert len(service.describe('second')['history']) == 2
    assert catalog.lifecycle == 'draft' and len(catalog.hashes) == 3
    assert service.describe('third')['release'] is None


@pytest.mark.parametrize('version', ['1', '01.0.0', '1.0.0-beta', '1.0.-1', True, '1.0.0\n'])
def test_malformed_versions_rejected(version):
    service, _ = setup()
    with pytest.raises(ValueError): service.declare('first', {**payload(), 'version':version}, 'reviewer')


@pytest.mark.parametrize('change', [
    {'version':'1.0.0','change_kind':'corrective','predecessor_id':'first'},
    {'version':'2.0.0','change_kind':'additive','predecessor_id':'first'},
    {'version':'1.1.0','change_kind':'additive','predecessor_id':'third'},
    {'family_id':'other','version':'1.1.0','change_kind':'additive','predecessor_id':'first'},
])
def test_conflicting_lineage_is_rejected_without_partial_writes(change):
    service, _ = setup(); service.declare('first', payload(), 'reviewer')
    before = copy.deepcopy(service.store.values)
    with pytest.raises(ValueError): service.declare('second', {**payload(), **change}, 'reviewer')
    assert service.store.values == before


def test_changed_artifact_invalidates_release_and_blocks_publication_check():
    service, catalog = setup(); service.declare('first', payload(), 'reviewer')
    catalog.hashes['first'] = 'd'*64
    assert service.describe('first')['artifact_matches_release'] is False
    with pytest.raises(ValueError): service.verify_artifact('first', 'd'*64)
    with pytest.raises(ValueError): service.declare('first', payload(), 'reviewer')


def test_simultaneous_successors_cannot_fork_history():
    service, _ = setup(); service.declare('first', payload(), 'reviewer')
    successor = {**payload(), 'version':'2.0.0','change_kind':'breaking','predecessor_id':'first'}
    def declare(key):
        try: service.declare(key, successor, 'reviewer'); return True
        except ValueError: return False
    with ThreadPoolExecutor(2) as pool:
        assert sorted(pool.map(declare, ['second','third'])) == [False, True]


def test_atomic_store_failure_leaves_no_release():
    service, _ = setup()
    def fail(values): raise RuntimeError('database unavailable')
    service.store.put_many = fail
    with pytest.raises(RuntimeError): service.declare('first', payload(), 'reviewer')
    assert not service.store.values
