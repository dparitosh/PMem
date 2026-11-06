"""Business-facing semantic evidence contracts; isolated from customer databases/LLMs."""
import copy
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
from backend.depo_platform.semantic_support import assessment, read_support


def verdict(status='consistent', coherent=True):
    return {'ontology_id': 'model', 'status': status, 'artifact_sha256': 'a'*64,
            'consistency_verified': status in {'consistent', 'inconsistent'},
            'deductive_reasoner_executed': True, 'modeling_coherent': coherent,
            'evidence_id': 'receipt', 'foundation': {'bundle_sha256': 'b'*64}}


@pytest.mark.parametrize('status,coherent,expected', [('consistent',True,'ready_for_review'),
    ('consistent',False,'conflict'), ('inconsistent',False,'conflict'), ('unknown',False,'unverified'),
    ('unsupported',False,'unverified')])
def test_business_disposition_does_not_equate_execution_with_suitability(status,coherent,expected):
    result=assessment(verdict(status,coherent))
    assert result['disposition']==expected
    assert result['instance_conformance_established'] is False
    assert result['publication_authorized'] is False


def test_unverified_consistent_string_is_never_ready():
    assert assessment({'status':'consistent'})['disposition']=='unverified'


def test_missing_read_access_never_uses_a_write_credential(monkeypatch):
    monkeypatch.setenv('INGESTION_WRITE_TOKEN','do-not-use')
    assert read_support('model')['reason']=='semantic_read_access_required'


def test_foundation_tool_returns_actual_business_definitions():
    from backend.ontology_service.foundation import foundation_summary
    result=foundation_summary('Physical part',3)
    assert result['terms'] and len(result['terms'])<=3
    assert any(term['iri']=='urn:depo:business:PhysicalPart' and any('physical artefact' in definition for definition in term['definitions']) for term in result['terms'])
    assert result['alignment_approved'] is False


@pytest.mark.asyncio
async def test_companion_unknown_is_a_business_explanation_not_schema_search(monkeypatch):
    from backend.agentic_service import companion_context
    from backend.agentic_service.companion import KnowledgeCompanion
    read=AsyncMock(return_value=({'ontology_id':'model','status':'unknown','reason':'unresolved_imports'},'owning-api'))
    monkeypatch.setattr(companion_context,'_read_json',read)
    result=await KnowledgeCompanion().ask('Is the ontology logically consistent?',ontology_id='model',headers={'Authorization':'Bearer test'})
    assert 'unknown' in result['response'] and 'Next action' in result['response']
    assert result['generation']['enabled'] is False
    assert read.await_count==1 and '/model/semantic-evidence' in read.call_args.args[2]


@pytest.mark.asyncio
async def test_companion_rejects_evidence_for_a_different_model(monkeypatch):
    from backend.agentic_service import companion_context
    monkeypatch.setattr(companion_context,'_read_json',AsyncMock(return_value=(verdict(), 'api')))
    with pytest.raises(ValueError,match='selected ontology'):
        await companion_context.semantic_context('Check OWL-DL consistency',headers={},ontology_id='other')


def test_goal_completion_cannot_replace_unknown_with_model_prose():
    from backend.agentic_service.goal_runner import semantic_completion
    record={'observations':[{'id':'o1','tool_id':'ontology.consistency.check','result':verdict('unknown',False)}]}
    result=semantic_completion(record,{'evidence_steps':['o1'],'semantic_conclusion':'unknown','summary':'This is definitely safe to publish'})
    assert 'definitely safe' not in result['summary']
    assert result['semantic_assessments'][0]['disposition']=='unverified'


def test_retained_evidence_is_not_reused_after_artifact_change(monkeypatch):
    from backend.ontology_service import owl_dl
    from backend.mesh_store import InMemoryRegistry
    store=InMemoryRegistry()
    monkeypatch.setattr(owl_dl,'evidence_key',lambda digest: digest)
    store.put('a'*64,verdict())
    catalog=SimpleNamespace(artifact_digest=lambda _: 'b'*64)
    assert owl_dl.current_evidence('model',catalog,store)['status']=='not_checked'


@pytest.mark.asyncio
async def test_agent_resume_detects_foundation_version_change(monkeypatch):
    from backend.agentic_service import source_revisions
    old={'ontology_id':'model','artifact_sha256':'a'*64,'status':'active','lifecycle_status':'approved','semantic_dependencies':{'foundation_sha256':'b'*64}}
    new=copy.deepcopy(old);new['semantic_dependencies']['foundation_sha256']='c'*64
    monkeypatch.setattr(source_revisions,'_read_json',AsyncMock(return_value=(new,'api')))
    with pytest.raises(ValueError,match='changed'):
        await source_revisions.verify({'scope':{'ontology_id':'model'},'source_revisions':[old]}, {})


def test_exact_union_exposes_conflict_for_industry_object_types():
    from backend.ontology_service.semantic_merge import check
    result=check('''@prefix owl:<http://www.w3.org/2002/07/owl#> .
      <urn:Design> a owl:Class; owl:disjointWith <urn:PhysicalPart> .
      <urn:PhysicalPart> a owl:Class . <urn:assembly> a <urn:Design>, <urn:PhysicalPart> .''')
    assert result['evidence']['status']=='inconsistent'
    assert result['assessment']['disposition']=='conflict'
    assert not result['assessment']['publication_authorized']


def test_governed_union_retains_actual_reasoning_and_blocks_conflicting_apply(tmp_path):
    from backend.ontology_service.catalog import OntologyCatalog
    from backend.ontology_service.merge_service import GovernedMergeService
    catalog=OntologyCatalog(root=tmp_path/'catalog')
    prolog=b'@prefix owl:<http://www.w3.org/2002/07/owl#> . @prefix rdfs:<http://www.w3.org/2000/01/rdf-schema#> . '
    first=catalog.register(content=prolog+b'<urn:Design> a owl:Class; rdfs:label "Design"; owl:disjointWith <urn:PhysicalPart> . <urn:PhysicalPart> a owl:Class; rdfs:label "Physical part" . <urn:item> a <urn:Design> .',filename='design.ttl',ontology_name='Design model',prefix='design')
    second=catalog.register(content=prolog+b'<urn:PhysicalPart> a owl:Class; rdfs:label "Physical part" . <urn:item> a <urn:PhysicalPart> .',filename='part.ttl',ontology_name='Physical model',prefix='physical')
    service=GovernedMergeService(catalog,SimpleNamespace(),catalog.root)
    preview=service.preview({'source_ontology_ids':[first['ontology_id'],second['ontology_id']], 'owl_dl_check':True})
    assert preview['owl_dl_evidence']['status']=='inconsistent'
    assert preview['semantic_support']['disposition']=='conflict'
    assert preview['publish_recommended'] is False
    with pytest.raises(ValueError,match='conflict'):
        service.apply(preview['preview_id'],'steward')


def test_recommendation_preserves_graph_evidence_and_adds_model_scope(monkeypatch):
    from backend.graph_service import context_router
    import backend.depo_platform.semantic_support as support
    calls=[]
    monkeypatch.setattr(support,'read_support',lambda identifier,headers: calls.append(identifier) or assessment(verdict('inconsistent',False)))
    result=context_router._semantic_recommendation({'similar_parts':[{'name':'Candidate bearing'}]}, {'scope':{'ontology_id':'model'}}, None)
    assert calls==['model'] and result['similar_parts'][0]['name']=='Candidate bearing'
    assert result['semantic_support']['disposition']=='conflict'
    assert result['engineering_action_authorized'] is False


def test_product_detail_reports_model_evidence_without_changing_package(monkeypatch):
    from backend.data_product_service import router
    import backend.depo_platform.semantic_support as support
    record={'product_id':'bearing','version':'1.0.0','ontologies':[{'ontology_id':'model'}], 'manifest':{'hash':'immutable'}}
    monkeypatch.setattr(router.store,'get',lambda _: copy.deepcopy(record))
    monkeypatch.setattr(support,'read_support',lambda identifier,headers: assessment(verdict()))
    result=router.get_product('bearing:1.0.0')
    assert result['semantic_support'][0]['disposition']=='ready_for_review'
    assert result['manifest']==record['manifest']


def test_data_flow_uses_publication_model_and_keeps_validation_separate(monkeypatch):
    from backend.data_pipeline_service import router
    import backend.depo_platform.semantic_support as support
    record={'run_id':'r1','output_manifest':{'publication':{'ontology_id':'model'},'validation_status':'conforms'}}
    monkeypatch.setattr(router.run_records,'get',lambda _:copy.deepcopy(record))
    calls=[]
    monkeypatch.setattr(support,'read_support',lambda identifier,headers: calls.append(identifier) or assessment(verdict('unknown',False)))
    result=router.get_job_run('r1')
    assert calls==['model'] and result['semantic_support']['disposition']=='unverified'
    assert result['output_manifest']['validation_status']=='conforms'


def test_bridge_holds_only_relevant_unsatisfiable_targets_and_rechecks_before_write():
    from backend.agentic_service.bridge_jobs import BridgeJobs
    from backend.mesh_store import InMemoryRegistry
    from backend.tests.test_bridge_automation_policy import Source
    from backend.tests.test_bridge_jobs import Graph
    source=Source(); graph=Graph()
    source.rows[0]['target_ontology_iri']='urn:PhysicalPart'
    report=assessment({**verdict('consistent',False),'unsatisfiable_classes':['urn:Design'], 'unsatisfiable_class_count':1})
    source.semantic_support=lambda identifier:report
    jobs=BridgeJobs(InMemoryRegistry(),source,graph,lambda *args:{'status':'not_configured','blocking':False,'checks':[]})
    preview=jobs.preview('model','import','reader')
    decision=jobs.evaluate_policy(preview['job_id'])
    assert decision['accepted_ids'] # An unrelated unsatisfiable design does not hold this physical-part target.
    report.update(status='inconsistent',consistency_verified=True)
    assert not jobs.evaluate_policy(preview['job_id'])['accepted_ids']
    with pytest.raises(ValueError,match='logical contradiction'):
        jobs.publish(preview['job_id'],decision['accepted_ids'],'reviewer')
    assert not graph.calls
