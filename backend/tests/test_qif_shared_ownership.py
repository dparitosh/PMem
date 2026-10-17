"""Replica coordination tests using shared files and a PostgreSQL session-lock double."""
from contextlib import contextmanager
from concurrent.futures import Future
import threading
import pytest
from backend.qif import ownership
from backend.qif.task_service import QifTaskService


class ManualExecutor:
    def __init__(self): self.jobs=[]
    def submit(self, work):
        future=Future(); self.jobs.append((work,future)); return future
    def shutdown(self, **kwargs):
        for _, future in self.jobs: future.cancel()
    def run(self):
        work,future=self.jobs.pop(0)
        if future.set_running_or_notify_cancel():
            work(); future.set_result(None)


class Registry:
    def __init__(self): self.locks={}; self.mutex=threading.Lock()
    def lock(self, key):
        with self.mutex: return self.locks.setdefault(key,threading.Lock())
    @contextmanager
    def advisory_lock(self,key,**kwargs):
        lock=self.lock(key); acquired=lock.acquire(blocking=False)
        try: yield acquired
        finally:
            if acquired: lock.release()
    @contextmanager
    def _session_connect(self,**kwargs):
        registry=self
        class Connection:
            alive=True
            held=None
            acquired=False
            @contextmanager
            def cursor(self): yield self
            def execute(self, sql, args=None):
                if not self.alive: raise RuntimeError('Lock session disconnected')
                if 'pg_try_advisory_lock' in sql:
                    self.held=registry.lock(args[0]); self.acquired=self.held.acquire(blocking=False)
            def fetchone(self): return (self.acquired,)
        connection=Connection()
        try: yield connection
        finally:
            if connection.acquired: connection.held.release()


@pytest.fixture
def replicas(tmp_path,monkeypatch):
    monkeypatch.setenv('QIF_TASK_STORAGE','shared')
    registry=Registry()
    monkeypatch.setattr(ownership,'_registry',lambda:registry)
    services=[QifTaskService(tmp_path),QifTaskService(tmp_path)]
    for service in services:
        service._executor.shutdown(wait=False); service._executor=ManualExecutor()
    yield services
    for service in services: service.shutdown()


def create(service):
    return service.create(source_paths=[],ontology_name='test',prefix='test',description='',source='test')['task_id']


@pytest.mark.parametrize('overlap',[False,True])
def test_two_replicas_cannot_execute_same_queued_phase(replicas,overlap):
    first,second=replicas; identity=create(first); calls=[]
    entered=threading.Event(); release=threading.Event()
    def work(task_id):
        calls.append(task_id)
        first._update(task_id,status='running',stage='inspect')
        entered.set(); assert release.wait(3)
        first._update(task_id,status='awaiting_approval',stage='review')
    first.prepare=work; second.prepare=lambda task_id:calls.append('duplicate')
    first.submit_prepare(identity); second.submit_prepare(identity)
    thread=threading.Thread(target=first._executor.run); thread.start()
    assert entered.wait(3)
    # Recovery on another replica must not reset active preparation state.
    assert second.recover_pending()['recovered']==0
    if overlap: second._executor.run()
    release.set(); thread.join(3); assert not thread.is_alive()
    if not overlap: second._executor.run()
    assert calls==[identity]
    assert first.get(identity)['status']=='awaiting_approval'


def test_disconnected_owner_cannot_write_terminal_state(replicas):
    first,second=replicas; identity=create(first)
    def work(task_id):
        first._update(task_id,status='running',stage='inspect')
        ownership._execution_connection.get().alive=False
        first._update(task_id,status='completed')
    first.prepare=work
    first.submit_prepare(identity); first._executor.run()
    assert second.get(identity)['status']=='running'
    assert second.get(identity)['stage']=='inspect'
    second.prepare=lambda task_id:second._update(task_id,status='awaiting_approval',stage='review')
    assert second.recover_pending()['recovered']==1
    second._executor.run()
    assert second.get(identity)['status']=='awaiting_approval'


def test_shared_mode_requires_absolute_storage_root(monkeypatch,tmp_path):
    monkeypatch.setenv('QIF_TASK_STORAGE','shared')
    monkeypatch.delenv('QIF_TASK_ROOT',raising=False)
    with pytest.raises(RuntimeError,match='QIF_TASK_ROOT'): ownership.task_root(tmp_path)
    monkeypatch.setenv('QIF_TASK_ROOT','relative/tasks')
    with pytest.raises(RuntimeError,match='absolute'): ownership.task_root(tmp_path)



def test_shared_storage_identity_rejects_separate_disks(tmp_path,monkeypatch):
    from backend.mesh_store import InMemoryRegistry
    class RegistryWithBoundedLock(InMemoryRegistry):
        def advisory_lock(self, key, *, bounded=False):
            return super().advisory_lock(key)
    registry=RegistryWithBoundedLock()
    monkeypatch.setattr(ownership,'_registry',lambda:registry)
    monkeypatch.setenv('ARTIFACT_STORAGE',str(tmp_path/'artifacts'))
    ownership.verify_shared_storage(tmp_path/'tasks')
    ownership.verify_shared_storage(tmp_path/'tasks')
    with pytest.raises(RuntimeError,match='do not share'):
        ownership.verify_shared_storage(tmp_path/'separate-disk')
    assert registry.get('storage-identity') is not None


def test_shared_storage_requires_shared_artifact_configuration(tmp_path,monkeypatch):
    monkeypatch.delenv('ARTIFACT_STORAGE',raising=False)
    with pytest.raises(RuntimeError,match='ARTIFACT_STORAGE'):
        ownership.verify_shared_storage(tmp_path)
