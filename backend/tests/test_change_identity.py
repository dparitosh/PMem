from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor
from threading import RLock
from backend.mesh_store import InMemoryRegistry
from backend.depo_platform.resource_identity import allocate, ensure

class CounterStore(InMemoryRegistry):
    def __init__(self): super().__init__(); self.lock=RLock()
    @contextmanager
    def advisory_lock(self, key):
        with self.lock: yield True

def test_change_numbers_are_unique_and_idempotent_under_concurrency():
    store=CounterStore()
    with ThreadPoolExecutor(max_workers=8) as pool:
        numbers=list(pool.map(lambda i:allocate('CR','pipeline',str(i%20),store=store),range(80)))
    assert len(set(numbers))==20
    assert all(number.startswith('CR-') for number in numbers)
    assert allocate('CR','pipeline','0',store=store)==numbers[0]
    assert allocate('CR','merges','0',store=store) not in numbers

def test_order_number_is_created_only_for_an_existing_authorization():
    store=CounterStore(); change={'state':'submitted','plan_digest':'unchanged','order':None}
    ensure(change,'pipeline','r',store=store)
    assert change['request_number'].startswith('CR-')
    assert change['order'] is None and change['state']=='submitted'
    change['order']={'authorized_by':'verified-actor','plan_digest':'unchanged'}
    ensure(change,'pipeline','r',store=store)
    first=change['order']['order_number']
    ensure(change,'pipeline','r',store=store)
    assert first==change['order']['order_number'] and first.startswith('CO-')
    assert change['plan_digest']=='unchanged'

def test_source_label_uses_original_artifact_not_the_generated_job_payload(tmp_path,monkeypatch):
    from backend.artifact_store import ArtifactStore
    from backend.depo_platform.run_labels import present
    monkeypatch.setenv('ARTIFACT_STORAGE',str(tmp_path))
    artifacts=ArtifactStore()
    raw=artifacts.ingest_bytes(b'{}',filename='internal-input.json',kind='data-job-input',media_type='application/json')
    source=artifacts.ingest_bytes(b'source',filename='000687_A_1-INDUCTION MOTOR ASSY 5HP.stpx',kind='source-ap242',media_type='application/xml')
    record={'run_id':'canonical-identity','input_manifest':{'artifact_ids':[raw['artifact_id'],source['artifact_id']],'raw_payload_artifact_id':raw['artifact_id']}}
    shown=present(record)
    assert shown['source_name']=='000687_A_1-INDUCTION MOTOR ASSY 5HP.stpx'
    assert shown['run_id']=='canonical-identity' and 'source_name' not in record


def test_configured_numbering_preserves_existing_uuid_and_numbers(monkeypatch):
    from backend.depo_platform import resource_identity as identities
    store,config=CounterStore(),CounterStore()
    monkeypatch.setattr(identities,'registry',store);monkeypatch.setattr(identities,'configuration',config)
    old=identities.identify('WF','pipeline','existing',name='Validate CAD')
    identities.update_scheme('WF',{'prefix':'FLOW','digits':4,'include_year':False,'expected_revision':0},'verified-admin')
    assert identities.identify('WF','pipeline','existing')==old
    fresh=identities.identify('WF','pipeline','new')
    assert fresh['number']=='FLOW-0001' and fresh['object_id']!=old['object_id']
    import pytest
    with pytest.raises(ValueError,match='changed'):
        identities.update_scheme('WF',{'prefix':'FLOW','digits':4,'include_year':False,'expected_revision':0},'verified-admin')
    with pytest.raises(ValueError,match='belongs'):
        identities.update_scheme('DS',{'prefix':'WF','digits':6,'include_year':True,'expected_revision':0},'verified-admin')


def test_file_events_have_distinct_identity_with_shared_content_provenance(monkeypatch):
    from uuid import uuid4
    from backend.depo_platform import resource_identity as identities
    monkeypatch.setattr(identities, 'registry', CounterStore())
    first_id, second_id = str(uuid4()), str(uuid4())
    links = {'content_sha256': 'a' * 64, 'artifact_id': 'sha256:retained', 'secret': 'must-not-retain'}
    first = identities.identify('FILE', 'ingestion', first_id, name='shaft.stpx', links=links)
    second = identities.identify('FILE', 'ingestion', second_id, name='shaft.stpx', links=links)
    assert first['object_id'] == first_id and second['object_id'] == second_id
    assert first['number'] != second['number']
    assert first['links'] == second['links'] == {'content_sha256': 'a' * 64, 'artifact_id': 'sha256:retained'}
    assert identities.resolve_object(first_id) == first
    assert identities.identify('FILE', 'ingestion', first_id, name='renamed') == first


def test_run_reuses_canonical_uuid_and_links_its_workflow(monkeypatch):
    from uuid import uuid4
    from backend.depo_platform import resource_identity as identities
    monkeypatch.setattr(identities, 'registry', CounterStore())
    run_id = str(uuid4())
    record = identities.identify('RUN', 'pipeline', run_id, name='Validate shaft', links={'workflow_id': 'validate-source'})
    assert record['object_id'] == run_id
    assert identities.resolve_object(run_id)['links']['workflow_id'] == 'validate-source'


def test_ingested_file_uuid_is_accepted_by_the_native_job_input_contract():
    from pydantic import TypeAdapter, ValidationError
    from uuid import uuid4
    import pytest
    from backend.depo_platform.request_bodies import JobInputBody
    value=str(uuid4())
    assert TypeAdapter(JobInputBody).validate_python({'source_file_id':value})['source_file_id']==value
    with pytest.raises(ValidationError):TypeAdapter(JobInputBody).validate_python({'source_file_id':'not-a-file-uuid'})
