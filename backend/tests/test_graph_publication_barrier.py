"""Publication visibility and crash recovery without a live customer database."""
import copy
import threading
from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from backend.depo_platform import graph_access as access
from backend.tests import test_staged_publication as staged


class Store:
    def __init__(self):
        self.marker = None
        self.readers = 0
        self.writer = False
        self.writer_lock = threading.Lock()

    def get(self, key):
        return copy.deepcopy(self.marker)

    def put(self, key, value):
        self.marker = copy.deepcopy(value)

    def create(self, key, value):
        if self.marker is not None:
            raise FileExistsError('marker already exists')
        self.put(key, value)
        return value

    @contextmanager
    def advisory_lock(self, key, **kwargs):
        acquired = self.writer_lock.acquire(blocking=False)
        try:
            yield acquired
        finally:
            if acquired:
                self.writer_lock.release()

    @contextmanager
    def _connect(self, **kwargs):
        connection = Connection(self)
        try:
            yield connection
        finally:
            if connection.owns_writer:
                self.writer = False

    _session_connect = _connect

    def compare_and_put(self, key, expected, value):
        if self.marker != expected:
            return False
        self.put(key, value)
        return True


class Connection:
    def __init__(self, store):
        self.store = store
        self.shared = False
        self.owns_writer = False

    @contextmanager
    def transaction(self):
        try:
            yield
        finally:
            if self.shared:
                self.store.readers -= 1
                self.shared = False

    def cursor(self):
        return Cursor(self)


class Cursor:
    def __init__(self, connection):
        self.connection = connection
        self.row = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def execute(self, query, params):
        store = self.connection.store
        if 'pg_try_advisory_xact_lock_shared' in query:
            acquired = not store.writer
            if acquired:
                store.readers += 1
                self.connection.shared = True
            self.row = (acquired,)
        elif 'pg_try_advisory_lock' in query:
            acquired = not store.writer and not store.readers
            if acquired:
                store.writer = True
                self.connection.owns_writer = True
            self.row = (acquired,)
        elif 'pg_advisory_unlock' in query:
            store.writer = False
        elif 'SELECT value' in query:
            self.row = (store.marker,) if store.marker is not None else None
        else:
            raise AssertionError(query)

    def fetchone(self):
        return self.row


@pytest.fixture
def store(monkeypatch):
    value = Store()
    monkeypatch.setattr(access, '_store', lambda: value)
    monkeypatch.setattr(access, '_configured', lambda: True)
    return value


def test_crash_keeps_projection_unavailable_until_exact_publication_resumes(store):
    with pytest.raises(RuntimeError, match='worker crashed'):
        with access.replacement_access('ontology', 'revision') as activation:
            activation.begin_mutation()
            raise RuntimeError('worker crashed')
    assert store.marker['ontology_id'] == 'ontology'
    assert store.marker['publication_id'] == 'revision'
    assert store.marker['phase'] == 'activating'
    assert store.marker['owner_id']
    assert not store.writer
    with pytest.raises(RuntimeError, match='requires completion'):
        with access.projection_access():
            pytest.fail('Partial graph was exposed')
    with pytest.raises(RuntimeError, match='interrupted'):
        with access.replacement_access('other-ontology', 'revision'):
            pytest.fail('Another ontology cleared the crash marker')
    with access.replacement_access('ontology', 'revision'):
        pass
    with access.projection_access():
        assert store.readers == 1
    assert store.readers == 0


def test_existing_reader_drains_and_new_reader_cannot_starve_activation(store):
    reader_entered = threading.Event()
    release_reader = threading.Event()
    def reader():
        with access.projection_access():
            reader_entered.set()
            assert release_reader.wait(5)
    thread = threading.Thread(target=reader)
    thread.start()
    assert reader_entered.wait(5)
    original_put = store.put
    def put(key, value):
        original_put(key, value)
        if value:
            # The marker is committed before waiting for the old reader.
            with pytest.raises(RuntimeError, match='requires completion'):
                with access.projection_access():
                    pytest.fail('A new reader overtook the writer')
            release_reader.set()
    store.put = put
    try:
        with access.replacement_access('ontology', 'revision', timeout=5):
            assert store.readers == 0
            assert store.writer
    finally:
        release_reader.set()
        thread.join(5)
    assert not thread.is_alive()


def test_interruption_after_first_activation_batch_resumes_without_recopy(store):
    session = staged.Session()
    original = session.execute_write
    copy_calls = 0
    def write(operation):
        nonlocal copy_calls
        if operation.__name__ == 'copy':
            copy_calls += 1
            if copy_calls == 2:
                raise TimeoutError('second batch timed out')
        return original(operation)
    session.execute_write = write
    publish = staged.StagedPublicationTests().publish
    with pytest.raises(TimeoutError):
        publish(session)
    assert len(session.canonical) == 1000
    assert session.receipt['activation_resource_offset'] == 1000
    assert session.receipt['status'] == 'staging'
    with pytest.raises(RuntimeError, match='requires completion'):
        with access.projection_access():
            pytest.fail('Partial graph was exposed')
    session.execute_write = original
    publish(session)
    assert len(session.canonical) == 1201
    assert session.writes.count('copy') == 2
    assert session.receipt['status'] == 'published'
    with access.projection_access():
        assert not store.marker


def test_lost_receipt_response_clears_barrier_without_replaying_activation(store):
    session = staged.Session()
    original = session.execute_write
    def write(operation):
        result = original(operation)
        if operation.__name__ == 'finish':
            raise OSError('response lost after graph commit')
        return result
    session.execute_write = write
    publish = staged.StagedPublicationTests().publish
    with pytest.raises(OSError):
        publish(session)
    assert session.receipt['status'] == 'published'
    assert store.marker
    writes = list(session.writes)
    session.execute_write = original
    publish(session)
    assert session.writes == writes
    assert not store.marker


def test_driver_session_holds_barrier_until_results_are_consumed(store):
    @contextmanager
    def raw_session(**kwargs):
        yield SimpleNamespace(run=lambda *args: iter([1, 2]))
    driver = access.guard_driver(SimpleNamespace(session=raw_session))
    with driver.session() as session:
        assert store.readers == 1
        assert list(session.run('query')) == [1, 2]
    assert store.readers == 0


def test_timeout_before_activation_does_not_leave_graph_blocked(store):
    with pytest.raises(TimeoutError):
        with access.replacement_access('ontology', 'revision', timeout=0):
            pytest.fail('Expired activation started')
    assert not store.marker
    with access.projection_access():
        pass


def test_reader_drain_timeout_clears_only_its_unmodified_marker(store, monkeypatch):
    clock = [0.0]
    monkeypatch.setattr(access.time, 'monotonic', lambda: clock[0])
    monkeypatch.setattr(access.time, 'sleep', lambda seconds: clock.__setitem__(0, clock[0] + 1))
    store.readers = 1
    with pytest.raises(TimeoutError):
        with access.replacement_access('ontology', 'revision', timeout=.5):
            pytest.fail('Reader did not drain')
    assert not store.marker
    assert not store.writer
    store.readers = 0
    with access.projection_access():
        pass


def test_connection_work_does_not_restart_the_activation_budget(store, monkeypatch):
    clock = [0.0]
    monkeypatch.setattr(access.time, 'monotonic', lambda: clock[0])
    original_put = store.put
    def put(key, value):
        original_put(key, value)
        if value:
            clock[0] = 5
    store.put = put
    with pytest.raises(TimeoutError):
        with access.replacement_access('ontology', 'revision', timeout=1):
            pytest.fail('A new budget was granted after connection/marker work')
    assert not store.marker


def test_validation_error_before_mutation_restores_graph_access(store):
    session = staged.Session()
    session.wrong_count = True
    with pytest.raises(ValueError, match='counts'):
        staged.StagedPublicationTests().publish(session)
    assert not session.canonical
    assert not store.marker
    with access.projection_access():
        pass


def test_normal_receipt_poll_repairs_post_commit_marker_failure(store, monkeypatch):
    import ast
    import logging
    from pathlib import Path
    from fastapi import HTTPException
    from backend.depo_platform import graph_publication_lock
    session = staged.Session()
    original_compare = store.compare_and_put
    def compare(key, expected, value):
        if value == {}:
            raise TimeoutError('marker acknowledgement timed out after graph commit')
        return original_compare(key, expected, value)
    store.compare_and_put = compare
    with pytest.raises(TimeoutError):
        staged.StagedPublicationTests().publish(session)
    assert session.receipt['status'] == 'published'
    assert store.marker['phase'] == 'activating'
    store.compare_and_put = original_compare
    tree = ast.parse(Path('backend/graph_service/router.py').read_text(encoding='utf-8'))
    handler = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'publication_receipt')
    handler.decorator_list = []
    scope = {'publisher': SimpleNamespace(publication_receipt=lambda **kwargs: session.receipt),
             'HTTPException': HTTPException, 'logger': logging.getLogger('receipt-test')}
    exec(compile(ast.Module(body=[handler], type_ignores=[]), '<receipt-handler>', 'exec'), scope)
    @contextmanager
    def idle(*args):
        yield True
    monkeypatch.setattr(graph_publication_lock, 'publication_lock', idle)
    assert scope['publication_receipt']('demo', 'digest')['status'] == 'published'
    assert not store.marker


def test_unpublished_or_other_receipt_cannot_clear_uncertain_activation(store):
    store.marker = {'ontology_id': 'ontology', 'publication_id': 'revision', 'phase': 'activating'}
    access.reconcile_activation('ontology', 'revision', {'status': 'staging'})
    assert store.marker
    access.reconcile_activation('other', 'revision', {
        'ontology_id': 'other', 'publication_id': 'revision', 'status': 'published', 'current': True})
    assert store.marker


def test_previous_owner_cannot_mutate_or_clear_a_resumed_publications_marker(store):
    original = {'ontology_id': 'ontology', 'publication_id': 'revision',
                'phase': 'activating', 'owner_id': 'old-worker'}
    stale = access._Activation(store, original)
    replacement = {**original, 'owner_id': 'resumed-worker'}
    store.marker = replacement.copy()
    with pytest.raises(RuntimeError, match='ownership changed'):
        stale.begin_mutation()
    assert access._clear_marker(store, original, recovery=True) is False
    assert store.marker == replacement


def test_neo4j_owner_change_fences_a_stale_batch_before_public_writes(store):
    session = staged.Session()
    original = session.execute_write
    copies = [0]
    def write(operation):
        if operation.__name__ == 'copy':
            copies[0] += 1
            if copies[0] == 2:
                # Simulate a resumed worker claiming the Neo4j receipt after
                # PostgreSQL lock loss but before this worker's next transaction.
                session.receipt['activation_owner'] = 'new-neo4j-owner'
        return original(operation)
    session.execute_write = write
    publish = staged.StagedPublicationTests().publish
    with pytest.raises(RuntimeError, match='owner changed'):
        publish(session)
    assert len(session.canonical) == 1000
    assert session.receipt['activation_resource_offset'] == 1000
    assert session.receipt['status'] == 'staging'
    assert store.marker
    # A fresh owner resumes the retained 201 rows instead of replaying 1,000.
    session.execute_write = original
    publish(session)
    assert len(session.canonical) == 1201
    assert session.writes.count('copy') == 2
    assert session.receipt['status'] == 'published'
    assert not store.marker


def test_publication_completed_by_another_worker_rejects_late_mutation(store):
    session = staged.Session()
    original = session.execute_write
    def write(operation):
        if operation.__name__ == 'copy':
            session.receipt['status'] = 'published'
            session.receipt['current'] = True
        return original(operation)
    session.execute_write = write
    with pytest.raises(RuntimeError, match='already completed'):
        staged.StagedPublicationTests().publish(session)
    assert not session.canonical


def test_new_marker_claim_cannot_overwrite_a_competing_owner(store):
    competing = {'ontology_id': 'other', 'publication_id': 'other-revision',
                 'phase': 'activating', 'owner_id': 'competing-worker'}
    def create(key, value):
        store.marker = competing.copy()
        raise FileExistsError('another owner created the marker')
    store.create = create
    with pytest.raises(FileExistsError):
        with access.replacement_access('ontology', 'revision'):
            pytest.fail('Competing activation was overwritten')
    assert store.marker == competing
