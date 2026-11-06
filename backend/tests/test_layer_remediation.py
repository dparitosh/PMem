import copy
import pytest
from backend.depo_platform.semantic_support import assessment, target_conflict
from backend.agentic_service.bridge_jobs import BridgeJobs, BridgeConflict
from backend.mesh_store import InMemoryRegistry
from backend.tests.test_bridge_automation_policy import Source
from backend.tests.test_bridge_jobs import Graph


def evidence(**changes):
    return assessment(dict(status='consistent', consistency_verified=True, deductive_reasoner_executed=True,
        artifact_sha256='a'*64, foundation={'bundle_sha256':'b'*64}, modeling_coherent=False,
        unsatisfiable_class_count=205, unsatisfiable_classes=['urn:Bad'+str(i) for i in range(200)], **changes))


def test_incomplete_class_sample_never_establishes_satisfiability():
    candidate={'target_ontology_type':'Class','target_ontology_iri':'urn:Omitted'}
    assert target_conflict(evidence(),candidate)
    assert not target_conflict(evidence(target_checks={'urn:Omitted':'satisfiable'}),candidate)
    assert target_conflict(evidence(target_checks={'urn:Omitted':'unknown'}),candidate)


def test_known_semantic_hold_survives_outage_new_preview_and_controller_restart():
    source,graph,store,holds=Source(),Graph(),InMemoryRegistry(),InMemoryRegistry()
    source.rows[0]['target_ontology_iri']='urn:Omitted'
    current=evidence()
    source.semantic_support=lambda identifier:current
    policy=lambda *args:{'status':'not_configured','blocking':False,'checks':[]}
    first=BridgeJobs(store,source,graph,policy,holds)
    preview=first.preview('model','import','reader')
    assert not first.evaluate_policy(preview['job_id'])['accepted_ids']
    current={'status':'unknown','disposition':'unverified','consistency_verified':False}
    restarted=BridgeJobs(store,source,graph,policy,holds)
    preview=restarted.preview('model','import','reader')
    assert not restarted.evaluate_policy(preview['job_id'])['accepted_ids']
    with pytest.raises(ValueError,match='logical contradiction'):
        restarted.publish(preview['job_id'],[preview['candidates'][0]['candidate_id']],'reviewer')
    assert not graph.calls
    current=evidence(target_checks={'urn:Omitted':'satisfiable'})
    assert restarted.evaluate_policy(preview['job_id'])['accepted_ids']


def test_selected_run_product_and_artifact_are_preserved_and_cannot_switch():
    from backend.agentic_service.goal_runner import selected_scope,validate_action
    for field in ('run_id','product_id','product_version','artifact_id'):
        assert selected_scope({field:'chosen'})=={field:'chosen'}
    tool={'id':'pipeline.run.evidence','input_schema':{'type':'object','required':['run_id'],
        'properties':{'run_id':{'type':'string'}},'additionalProperties':False}}
    record={'scope':{'run_id':'chosen'},'plans':['plan'],'observations':[],'context':{}}
    with pytest.raises(ValueError,match='scope'):
        validate_action(record,{'tool_id':tool['id'],'inputs':{'run_id':'different'}},[tool])
    from backend.agentic_service.goal_runner import verify_read_identity
    with pytest.raises(ValueError,match='identity'):
        verify_read_identity(tool['id'],{'run_id':'chosen'},{'run_id':'different'})


def test_followup_memory_does_not_cross_operational_records():
    from backend.agentic_service.context_scope import same_companion_scope
    assert not same_companion_scope({'run_id':'A'},{'run_id':'B'})
    assert not same_companion_scope({'product_id':'P','product_version':'1'},{'product_id':'P','product_version':'2'})
    assert same_companion_scope({'page':'graph'},{'page':'graph','run_id':''})


@pytest.mark.parametrize('count',[199,200,201,205])
def test_class_list_completeness_boundaries(count):
    report=evidence()
    report.update(unsatisfiable_class_count=count,
                  unsatisfiable_classes=['urn:Bad'+str(i) for i in range(min(count,200))],
                  unsatisfiable_classes_complete=True)
    normalized=assessment(report)
    assert normalized['unsatisfiable_classes_complete'] is (count<=200)


def test_goal_uses_only_the_selected_catalog_version():
    from backend.agentic_service.goal_runner import verify_read_identity
    selected={'product_id':'P','version':'1','description':'Retained contract'}
    body={'product_id':'P','versions':[selected,{'product_id':'P','version':'2'}]}
    assert verify_read_identity('data.catalog.product',{'product_id':'P'},body,{'product_version':'1'})==selected
    with pytest.raises(ValueError,match='selected product version'):
        verify_read_identity('data.catalog.product',{'product_id':'P'},body,{'product_version':'3'})


@pytest.mark.asyncio
async def test_selected_record_read_rejects_wrong_identity_and_binds_revision(monkeypatch):
    from backend.agentic_service import selected_record,source_revisions
    body={'run_id':'A','status':'completed','description':'Validated source'}
    async def read(*args):return copy.deepcopy(body),'http://owner/run/A'
    monkeypatch.setattr(selected_record,'_read_json',read)
    answer=await selected_record.answer({'run_id':'A'}, {})
    assert 'Validated source' in answer['response'] and '<' not in answer['response']
    receipts=await source_revisions.capture({'run_id':'A'}, {})
    assert receipts[0]['resource_id']=='A'
    body['status']='failed'
    with pytest.raises(ValueError,match='revision'):
        await source_revisions.verify({'scope':{'run_id':'A'},'source_revisions':receipts},{})
    body['run_id']='B'
    with pytest.raises(ValueError,match='selected run'):
        await selected_record.answer({'run_id':'A'}, {})


@pytest.mark.asyncio
async def test_companion_pinned_record_never_falls_back_to_other_graph_matches(monkeypatch):
    from backend.agentic_service.companion import KnowledgeCompanion
    from backend.agentic_service import selected_record
    async def unavailable(*args):raise ValueError('wrong identity')
    monkeypatch.setattr(selected_record,'answer',unavailable)
    result=await KnowledgeCompanion().ask('Explain its quality',run_id='A',headers={})
    assert result['answerable'] is False and not result['evidence']
    assert 'no other record was substituted' in result['response']


@pytest.mark.parametrize('module',['backend/depo_platform/semantic_support.py',
    'backend/ontology_service/semantic_merge.py','backend/agentic_service/selected_record.py'])
def test_release_rejects_missing_semantic_and_context_helpers(tmp_path,module):
    from backend.depo_platform.release_code_check import REQUIRED_MODULES,check
    for name in REQUIRED_MODULES:
        path=tmp_path/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text('')
    (tmp_path/module).unlink()
    with pytest.raises(ValueError,match='missing required modules'):
        check(tmp_path)


def test_real_reasoner_omitted_target_checked_directly(monkeypatch):
    from backend.ontology_service.owl_dl import inspect_graph
    from rdflib import Graph as RDFGraph, RDF, RDFS, OWL, URIRef
    monkeypatch.setenv('DEPO_REASONER_JAVA',r'C:\Program Files\Microsoft\jdk-25.0.4.101-hotspot\bin\java.exe')
    graph=RDFGraph()
    for i in range(205):
        term=URIRef(f'urn:Bad{i:03d}')
        graph.add((term,RDF.type,OWL.Class));graph.add((term,RDFS.subClassOf,OWL.Nothing))
    graph.add((URIRef('urn:Good'),RDF.type,OWL.Class))
    result=inspect_graph(graph,artifact_sha256='a'*64,include_foundation=False,
                         target_iris=['urn:Bad204','urn:Good','urn:Missing'])
    assert result['consistency_verified'] is True
    assert result['unsatisfiable_class_count']==205 and len(result['unsatisfiable_classes'])==200
    assert result['unsatisfiable_classes_complete'] is False
    assert result['target_checks']=={'urn:Bad204':'unsatisfiable','urn:Good':'satisfiable','urn:Missing':'unknown'}
    assert target_conflict(assessment(result),{'target_ontology_type':'Class','target_ontology_iri':'urn:Bad204'})


def test_graph_write_requires_matching_published_revision_when_using_reasoning():
    from backend.graph_service.bridge_publication import verify_semantic_projection
    from unittest.mock import Mock
    tx=Mock(); tx.run.return_value.single.return_value={'matched':0}
    command={'ontology_id':'chosen','semantic_binding':{'artifact_sha256':'a'*64}}
    with pytest.raises(ValueError,match='differs'):
        verify_semantic_projection(tx,command)
    assert tx.run.call_args.kwargs['artifact_sha256']=='a'*64
    tx.run.return_value.single.return_value={'matched':1}
    verify_semantic_projection(tx,command)
    tx.reset_mock()
    verify_semantic_projection(tx,{'ontology_id':'chosen'})
    tx.run.assert_not_called()  # Legacy unverified policy does not claim DL/projection verification.


def test_final_semantic_check_and_publication_share_revision_lock():
    import threading
    from contextlib import contextmanager
    from concurrent.futures import ThreadPoolExecutor
    class LockedStore(InMemoryRegistry):
        def __init__(self):
            super().__init__(); self.lock=threading.Lock()
        @contextmanager
        def advisory_lock(self,key):
            acquired=self.lock.acquire(blocking=False)
            try:yield acquired
            finally:
                if acquired:self.lock.release()
    entered,release=threading.Event(),threading.Event()
    class DelayedGraph(Graph):
        def publish(self,command):
            entered.set()
            assert release.wait(5)
            return super().publish(command)
    source,graph,holds=Source(),DelayedGraph(),LockedStore()
    current=assessment({'status':'consistent','consistency_verified':True,'deductive_reasoner_executed':True,
        'artifact_sha256':'a'*64,'foundation':{'bundle_sha256':'b'*64},'modeling_coherent':True,
        'unsatisfiable_class_count':0,'unsatisfiable_classes':[]})
    source.semantic_support=lambda identifier:current
    jobs=BridgeJobs(InMemoryRegistry(),source,graph,lambda *args:{'status':'not_configured','blocking':False,'checks':[]},holds)
    preview=jobs.preview('model','import','reader')
    with ThreadPoolExecutor(max_workers=1) as executor:
        future=executor.submit(jobs.publish,preview['job_id'],[preview['candidates'][0]['candidate_id']],'reviewer')
        try:
            assert entered.wait(5)
            current=evidence();current.update(status='inconsistent')
            with pytest.raises(BridgeConflict,match='being updated'):
                jobs.evaluate_policy(preview['job_id'])
        finally:release.set()
        assert future.result()['status']=='published'
    assert not jobs.evaluate_policy(preview['job_id'])['accepted_ids']
    assert len(graph.calls)==1
