"""Shared native policy evidence and write-boundary regression tests; no live DB."""
import copy
import pytest
from backend.mesh_store import InMemoryRegistry
from backend.ontology_service.intelligence import SemanticIntelligence
from backend.depo_platform.decision_policy import decision, assess_decisions, assess_recommendation
from backend.tests.test_bridge_jobs import Source, Graph
from backend.agentic_service.bridge_jobs import BridgeJobs


def intelligence():
    service = SemanticIntelligence(None, registry=InMemoryRegistry())
    service.evidence = {}
    service._retain_assessment = lambda key, value: service.evidence.update({key: copy.deepcopy(value)})
    return service


def test_no_policy_is_not_approval_and_evidence_is_bound_to_decisions():
    service = intelligence()
    result = service.evaluate_decisions('instance_bridge', [decision(.95, candidate_id='one')])
    assert result['status'] == 'not_configured' and result['compliant'] is None and not result['blocking']
    assert result['assessment_id'] in service.evidence
    changed = service.evaluate_decisions('instance_bridge', [decision(.95, candidate_id='two')])
    assert changed['decision_digest'] != result['decision_digest']


def test_native_rules_scoped_and_changed_policy_changes_snapshot():
    service = intelligence()
    policy = dict(policy_id='minimum', operations=['instance_bridge'], rules={'min_confidence': .99})
    service.add_policy(policy)
    blocked = service.evaluate_decisions('instance_bridge', [decision(.95)])
    assert blocked['blocking'] and blocked['checks'][0]['violations']
    assert service.evaluate_decisions('ontology_merge', [decision()])['status'] == 'not_configured'
    policy['rules'] = {'min_confidence': .9}
    service.add_policy(policy)
    passed = service.evaluate_decisions('instance_bridge', [decision(.95)])
    assert passed['status'] == 'passed'
    assert passed['policy_digest'] != blocked['policy_digest']


def test_unknown_rules_and_invalid_confidence_are_not_silently_accepted():
    service = intelligence()
    with pytest.raises(ValueError):
        service.add_policy(dict(policy_id='bad', rules={'owl_dl_proof': True}))
    for score in (True, float('nan'), float('inf'), -1):
        assert decision(score)['confidence_basis'] == 'not_established'
    assert decision(decision_maker='recommendation-service')['decision_maker'] == 'recommendation-service'


def test_policy_or_audit_store_failure_is_unavailable_not_pass(monkeypatch):
    def fail(*args): raise RuntimeError('private DB details')
    monkeypatch.setattr('backend.depo_platform.decision_policy.service_bearer_headers', lambda *a,**kw:{})
    monkeypatch.setattr('backend.depo_platform.decision_policy.peer_response', fail)
    report = assess_decisions('ontology_merge', [decision()])
    assert report['blocking'] and report['status'] == 'unavailable'
    assert 'private DB' not in str(report)
    result = assess_recommendation({'impact_score': 100}, 'change-impact', {})
    assert result['decision_policy']['blocking'] and result['advisory_only']


def test_manual_bridge_rechecks_latest_policy_and_retains_hold():
    service = intelligence()
    source, graph, store = Source(), Graph(), InMemoryRegistry()
    jobs = BridgeJobs(store, source, graph, policy_evaluator=service.evaluate_decisions)
    preview = jobs.preview('ontology', 'import', 'reader')
    assert jobs.evaluate_policy(preview['job_id'])['decision_policy']['status'] == 'not_configured'
    service.add_policy(dict(policy_id='strict', operations=['instance_bridge'], rules={'min_confidence': .99}))
    ids = [preview['candidates'][0]['candidate_id']]
    with pytest.raises(ValueError, match='decision policy holds'):
        jobs.publish(preview['job_id'], ids, 'reviewer')
    assert graph.calls == []
    assert store.get(preview['publication_job_id'])['decision_policy']['status'] == 'blocked'


def test_manual_merge_rechecks_shared_policy_after_local_checks(monkeypatch):
    from backend.tests.test_merge_automation import MergeAutomationTests
    service, values, preview = MergeAutomationTests().service()
    report = {'status':'blocked','blocking':True,'checks':[]}
    service._decision_policy = lambda record: report
    result = service.evaluate_policy(preview['preview_id'])
    assert result['status'] == 'held' and result['governance']['decision_policy'] == report
    with pytest.raises(ValueError, match='decision policy holds'):
        service._apply(preview['preview_id'], 'reviewer')
    service.catalog.register.assert_not_called()


def test_recommendation_rank_uses_evidence_not_alphabetical_position(monkeypatch):
    from backend.tests.test_recommendation_customer_audit import Graph, record
    from backend.graph_service.recommendation_engine import RecommendationEngine
    monkeypatch.delenv('DEPO_DATABASE_URL', raising=False)
    monkeypatch.delenv('DATABASE_URL', raising=False)
    rows = [record('root','Wheel',material='Steel',diameter='1 in'),
            record('two','A very different wheel'), record('three','Replacement',material='Steel',diameter='25.4 mm')]
    first = RecommendationEngine(Graph(rows)).similar('root')
    rows.reverse()
    assert first == RecommendationEngine(Graph(rows)).similar('root')
    assert first['similar_parts'][0]['node_id'] == 'three'
    assert first['similar_parts'][0]['score_evidence']['engineering_matches'] == 2
    assert first['similar_parts'][0]['similarity_score'] > first['similar_parts'][1]['similarity_score']


def test_engineering_policy_holds_conflicts_and_missing_coverage():
    service = intelligence()
    service.add_policy({'policy_id':'engineering-review','operations':['recommendations'],
        'rules':{'min_confidence':0,'max_conflicts':0,'min_evidence_coverage':.6,
                 'allowed_evidence_statuses':['requires_engineering_review']}})
    subjects = [decision(candidate_id='bad', conflicts=['diameter'], evidence_coverage=.8,evidence_status='conflicting_evidence'),
                decision(candidate_id='missing',conflicts=[], evidence_coverage=None,evidence_status='requires_engineering_review'),
                decision(candidate_id='reviewable',conflicts=[],evidence_coverage=.7,evidence_status='requires_engineering_review')]
    report=service.evaluate_decisions('recommendations',subjects)
    assert report['blocked_decision_indices'] == [0,1]
    assert report['checks'][2]['compliant'] is True
    assert service.evidence[report['assessment_id']]['decisions'] == subjects
    assert report['engineering_rules_engine'] == 'depo.engineering-evidence-rules-v1'


def test_engineering_policy_never_accepts_unknown_effectivity_or_truncated_coverage():
    service=intelligence()
    service.add_policy({'policy_id':'effectivity','operations':['recommendations'],
        'rules':{'min_confidence':0,'require_effectivity_verified':True,'require_complete_coverage':True}})
    result=service.evaluate_decisions('recommendations',[decision(effectivity_verified=False,coverage={'whole_graph_complete':False})])
    assert result['blocking']
    assert len(result['checks'][0]['violations']) >= 2


@pytest.mark.parametrize('rules',[{'max_conflicts':True},{'min_evidence_coverage':float('nan')},{'require_complete_coverage':'yes'},{'allowed_evidence_statuses':[]}])
def test_invalid_engineering_policy_settings_are_rejected(rules):
    with pytest.raises(ValueError): intelligence().add_policy({'policy_id':'invalid','rules':rules})

def test_automatic_bridge_cannot_bypass_native_policy():
    service = intelligence()
    service.add_policy(dict(policy_id='stricter', operations=['instance_bridge'], rules={'min_confidence': .99}))
    source, graph = Source(), Graph()
    original = source.preview()[1][0]
    source.preview = lambda *args: (source.snapshot(), [{**original, 'confidence':.95, 'rank':1, 'validation_status':'auto_approved'}])
    jobs = BridgeJobs(InMemoryRegistry(), source, graph, policy_evaluator=service.evaluate_decisions)
    preview = jobs.preview('ontology','import','reader')
    report = jobs.publish_automatic(preview['job_id'],'reviewer')
    assert report['status'] == 'held' and report['applied_links'] == 0
    assert 'decision_policy_blocked' in report['decisions'][0]['reasons']
    assert graph.calls == []


def test_evidence_write_failure_is_not_policy_pass(monkeypatch):
    service = intelligence()
    def fail(*args): raise RuntimeError('audit unavailable')
    service._retain_assessment = fail
    evaluate = service.evaluate_decisions
    monkeypatch.setattr('backend.depo_platform.decision_policy.service_bearer_headers', lambda *a,**kw:{})
    monkeypatch.setattr('backend.depo_platform.decision_policy.peer_response', lambda *a,**kw: evaluate(kw['json']['operation'],kw['json']['decisions']))
    report = assess_decisions('instance_bridge',[decision(.95)])
    assert report['status'] == 'unavailable' and report['blocking']


def test_policy_lookup_does_not_load_ontology_version_history():
    service = intelligence()
    service.registry.put('version:large', {'content':'unrelated'})
    service.registry.all = lambda: pytest.fail('Must not enumerate all version records')
    assert service.evaluate_decisions('ontology_merge', [decision()])['status'] == 'not_configured'


def test_automatic_retry_reconciles_receipt_after_policy_change():
    service = intelligence()
    source, graph = Source(), Graph()
    original = source.preview()[1][0]
    source.preview = lambda *args: (source.snapshot(), [{**original,'confidence':.95,'rank':1,'validation_status':'auto_approved'}])
    jobs = BridgeJobs(InMemoryRegistry(),source,graph,policy_evaluator=service.evaluate_decisions)
    preview = jobs.preview('ontology','import','reader')
    graph.lose_response = True
    with pytest.raises(TimeoutError): jobs.publish_automatic(preview['job_id'],'reviewer')
    service.add_policy(dict(policy_id='stricter',operations=['instance_bridge'],rules={'min_confidence':.99}))
    result = jobs.publish_automatic(preview['job_id'],'reviewer')
    assert result['status'] == 'published' and len(graph.calls) == 1


def test_large_batch_retains_all_evidence_without_unbounded_ui_payload():
    service = intelligence()
    service.add_policy(dict(policy_id='minimum',operations=['instance_bridge'],rules={'min_confidence':.99}))
    report = service.evaluate_decisions('instance_bridge',[decision(.95,candidate_id=str(i)) for i in range(205)])
    assert len(report['checks']) == 200 and report['checks_truncated']
    assert report['checks_total'] == 205 and 204 in report['blocked_decision_indices']
    assert len(service.evidence[report['assessment_id']]['checks']) == 205
