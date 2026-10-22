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


def test_recommendation_rank_uses_evidence_not_alphabetical_position():
    import ast, re
    from pathlib import Path
    from types import SimpleNamespace
    tree = ast.parse(Path('backend/graph_service/context_router.py').read_text(encoding='utf-8'))
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == '_similar_parts_result')
    rows = [dict(name='Wheel spare unrelated',labels=['Class'],source_tag='other'),
            dict(name='Wheel',labels=['Class'],source_tag='same')]
    scope = dict(re=re, ContextBody=dict, _find_node=lambda *args,**kwargs: dict(id='one', name='Wheel',labels=['Class'],source_tag='same'),
        _ontology_node_clause=lambda: 'true', _display_name=lambda row: row['name'],
        publisher=SimpleNamespace(_session_rows=lambda *args,**kwargs: rows))
    exec(compile(ast.Module(body=[fn],type_ignores=[]),'<recommendation>','exec'),scope)
    first = scope['_similar_parts_result']({'part_name':'Wheel'})
    rows.reverse()
    assert first == scope['_similar_parts_result']({'part_name':'Wheel'})
    assert first['similar_parts'][0]['similarity_score'] == 100
    assert first['similar_parts'][1]['similarity_score'] == 50


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
