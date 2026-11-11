"""Customer engineering scenarios use controlled graph records, never a live DB."""
from copy import deepcopy
from unittest.mock import patch
import pytest
from fastapi import HTTPException
from backend.graph_service.recommendation_engine import RecommendationEngine
from backend.graph_service.engineering_comparison import compare, values
from backend.graph_service import context_router as api


def record(identifier, name, category='Part', **props):
    return {'id': identifier, 'labels': ['OntologyResource'], 'properties': {'label': name, 'rdf_types': ['https://customer.example/engineering#'+category], **props}}


class Graph:
    def __init__(self, records, edges=()):
        self.records = {row['id']: row for row in records}
        self.links = edges
        self.calls = []

    def _session_rows(self, query, **params):
        self.calls.append((query, params))
        def allowed(row):
            p = row['properties']
            return (not params.get('scope') or p.get('ontology_id') == params['scope']) and (not params.get('prefix') or p.get('prefix') == params['prefix'])
        if 'recommendation-record' in query:
            row = self.records.get(params['id'])
            return [deepcopy(row)] if row and allowed(row) else []
        if 'recommendation-candidates' in query:
            return [deepcopy(row) for row in self.records.values() if row['id'] != params['id'] and allowed(row)][:201]
        if 'recommendation-dependencies' in query:
            rows = []
            for source in params['frontier']:
                for start, end, relation, identifier in self.links:
                    if source not in (start, end): continue
                    target = end if source == start else start
                    row = self.records[target]
                    if not allowed(row): continue
                    rows.append({'from_id':source, 'to_id':target, **deepcopy(row), 'relationship_id':identifier,
                                 'relationship_type':relation, 'start_id':start, 'end_id':end})
            return rows[:601]
        raise AssertionError(query)


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    monkeypatch.delenv('DEPO_DATABASE_URL', raising=False)
    monkeypatch.delenv('DATABASE_URL', raising=False)


def test_similarity_excludes_requirements_and_does_not_invent_trace_evidence():
    graph = Graph([record('root','Motor'), record('req','Motor','Requirement'), record('part','Motor')])
    result = RecommendationEngine(graph).similar('root')
    assert [row['node_id'] for row in result['similar_parts']] == ['part']
    row = result['similar_parts'][0]
    assert row['similarity_score'] == 35
    assert row['evidence_coverage'] == 0
    assert row['shared_assembly'] is None and row['traceability_link'] is None
    assert result['coverage']['category_mismatches_excluded'] == 1


def test_candidate_scope_uses_indexed_published_ontology_anchor():
    graph = Graph([record('root','Shaft',ontology_id='one'), record('same','Alternative',ontology_id='one'), record('other','Other',ontology_id='two')])
    result = RecommendationEngine(graph).similar('root')
    query, params = next(call for call in graph.calls if 'recommendation-candidates' in call[0])
    assert 'MATCH (n:OntologyResource {ontology_id:$scope})' in query
    assert 'UNION MATCH (n:OntologyResource {source_ontology:$scope})' in query
    assert params['scope'] == 'one'
    assert [row['node_id'] for row in result['similar_parts']] == ['same']
    assert result['coverage']['default_ontology_scope'] == 'one'


def test_legacy_candidate_query_has_an_explicit_label_anchor():
    root = {'id':'legacy','labels':['Part'],'properties':{'name':'Legacy'}}
    graph = Graph([root])
    RecommendationEngine(graph).similar('legacy')
    query, _ = next(call for call in graph.calls if 'recommendation-candidates' in call[0])
    assert 'MATCH (n) ' not in query
    assert '|Part|' in query


def test_differently_named_part_with_engineering_evidence_outranks_name_only_match():
    props = dict(material='Steel', diameter='25.4 mm', length='10 mm', revision='A', specification='ISO-1')
    graph = Graph([record('root','Drive shaft',**props), record('good','Replacement 739',**{**props,'diameter':'1 in'}), record('lexical','Drive shaft')])
    result = RecommendationEngine(graph).similar('root')['similar_parts']
    assert result[0]['node_id'] == 'good'
    assert result[0]['score_evidence']['engineering_matches'] == 5
    assert result[0]['conflicts'] == []
    assert 'material' in {entry['property'] for entry in result[0]['engineering_comparisons']}


@pytest.mark.parametrize('field,left,right', [('diameter','10 mm','11 mm'),('material','Steel','Aluminium'),('revision','A','B'),('configuration','EU','US'),('tolerance','0.1 mm','0.2 mm')])
def test_engineering_conflict_holds_reuse_even_with_identical_names(field,left,right):
    result = RecommendationEngine(Graph([record('root','Motor',**{field:left}),record('other','Motor',**{field:right})])).similar('root')['similar_parts'][0]
    assert field in result['conflicts']
    assert result['compatibility'] == 'conflicting_evidence'
    assert result['similarity_score'] <= 35


def test_missing_units_multiple_values_and_embedded_markup_are_unassessed():
    result = compare({'diameter':'10', 'material':['Steel','Iron'], 'specification':'<xml>secret</xml>'}, {'diameter':'10 mm','material':'Steel'})
    assert all(row['status'] == 'unassessed' for row in result)
    assert 'specification' not in values({'specification':'<xml>secret</xml>'})


def test_candidate_cap_and_scope_are_visible():
    graph = Graph([record('root','Motor',ontology_id='one')] + [record(str(i),'Part',ontology_id='one') for i in range(202)] + [record('foreign','Motor',ontology_id='two')])
    result = RecommendationEngine(graph).similar('root',{'ontology_id':'one'},top_n=5)
    assert len(result['similar_parts']) == 5
    assert result['coverage']['limit_reached']
    assert result['coverage']['candidates_examined'] == 200
    assert all(row['node_id'] != 'foreign' for row in result['similar_parts'])
    query, params = graph.calls[1]
    assert params['scope'] == 'one' and 'LIMIT 201' in query


def test_impact_follows_carrier_upward_bom_trace_and_process_paths_with_identity():
    records = [record('change','ECR 1','Change'),record('carrier','Impacted item','GeneralRelation',sub_type='CMHasImpactedItem'),record('part','Bearing'),record('assembly','Drive assembly','Assembly'),record('req','Vibration limit','Requirement'),record('process','Press fit','Process')]
    links = [('change','carrier','RELATEDREFS','a'),('carrier','part','RELATEDREFS','b'),('assembly','part','HAS_CHILD_INSTANCE','c'),('assembly','req','SATISFIES','d'),('part','process','MANUFACTURED_BY','e')]
    result = RecommendationEngine(Graph(records,links)).impact('change')
    assert [row['node_id'] for row in result['impacted_parts']] == ['part']
    assert result['assembly_impact'][0]['depth'] == 3
    assert result['impacted_requirements'][0]['path_names'] == ['ECR 1','Impacted item','Bearing','Drive assembly','Vibration limit']
    assert [edge['relationship_id'] for edge in result['impacted_requirements'][0]['path']] == ['a','b','c','d']
    assert result['process_impacts'][0]['node_id'] == 'process'
    assert result['impact_score'] is None
    assert result['coverage']['whole_graph_complete'] is False


def test_plain_master_references_and_reverse_impact_are_not_change_effects():
    rows = [record('root','Motor'),record('other','Unrelated'),record('incoming','Another change','Change')]
    result = RecommendationEngine(Graph(rows,[('root','other','MASTERREF','a'),('incoming','root','IMPACTS','b')])).impact('root')
    assert result['realization_chain'] == []
    assert result['evidence_status'] == 'insufficient'


def test_configuration_conflict_and_scope_are_preserved_in_impact():
    rows = [record('root','Change','Change',configuration='A',ontology_id='one'),record('part','Part',configuration='B',ontology_id='one'),record('outside','Outside',ontology_id='two')]
    result = RecommendationEngine(Graph(rows,[('root','part','IMPACTS','a'),('root','outside','IMPACTS','b')])).impact('root',{'ontology_id':'one'})
    assert len(result['impacted_parts']) == 1
    assert result['impacted_parts'][0]['review_status'] == 'configuration_conflict'
    assert result['impacted_parts'][0]['effectivity_verified'] is False


def test_cycles_and_large_frontiers_are_bounded():
    rows = [record('root','Root')] + [record(str(i),'Part') for i in range(300)]
    graph = Graph(rows,[('root',str(i),'SATISFIES',str(i)) for i in range(300)])
    result = RecommendationEngine(graph).impact('root')
    assert len(result['realization_chain']) <= 199
    assert result['coverage']['limit_reached']
    assert len(graph.calls) == 2


def test_unclassified_source_requires_declared_type_and_selected_identity_cannot_escape_scope():
    graph = Graph([record('root','Part name','Unknown',ontology_id='one')])
    with pytest.raises(HTTPException) as error: RecommendationEngine(graph).similar('root')
    assert error.value.status_code == 422
    with pytest.raises(HTTPException) as error: RecommendationEngine(graph).impact('root',{'ontology_id':'two'})
    assert error.value.status_code == 404


def test_recommendation_name_lookup_requests_business_records():
    with patch.object(api.publisher, 'search', return_value={'nodes':[]}) as search:
        assert api._find_node('Motor') is None
    assert search.call_args.kwargs['business_only'] is True


def test_process_context_uses_declared_types_not_business_names_and_deduplicates():
    neighbors = [
        {'id':'fake','name':'Manufacturing process specification','labels':['Document']},
        {'id':'real','name':'Press fit','labels':['OntologyResource'],'rdf_types':['https://example.org/Process']},
        {'id':'real','name':'Press fit','labels':['OntologyResource'],'rdf_types':['https://example.org/Process']},
        {'id':'mapped','name':'Inspect bearing','mapped_types':['https://example.org/Operation']},
    ]
    with patch.object(api,'_find_node',return_value={'id':'root','name':'Bearing'}), patch.object(api,'_neighbors',return_value=neighbors) as query:
        result = api._manufacturing_context_result({'node_id':'root','scope':{'ontology_id':'selected'}})
    query.assert_called_once_with('root',scope={'ontology_id':'selected'},limit=101)
    assert [row['node_id'] for row in result['direct_processes']] == ['real','mapped']
    assert result['process_summary']['total_direct'] == 2
    assert result['part']['node_id'] == 'root'
    assert result['coverage']['whole_graph_complete'] is False


def test_process_neighbor_query_applies_scope_before_limit_and_has_timeout():
    with patch.object(api.publisher,'_session_rows',return_value=[]) as query:
        api._neighbors('root',scope={'ontology_id':'selected','ontology_prefix':'plant'},limit=101)
    cypher = query.call_args.args[0]
    params = query.call_args.kwargs
    assert params['scope'] == 'selected' and params['prefix'] == 'plant'
    assert 0 < params['_timeout_seconds'] <= 20
    assert cypher.index('neighbor.ontology_id = $scope') < cypher.index('LIMIT $limit')
    assert 'OntologyClass' in params['excluded']


def test_process_context_reports_neighbor_truncation_without_claiming_absence():
    with patch.object(api,'_find_node',return_value={'id':'root','name':'Bearing'}), patch.object(api,'_neighbors',return_value=[{'id':str(i),'name':'Document'} for i in range(101)]):
        result = api._manufacturing_context_result({'node_id':'root'})
    assert result['coverage']['limit_reached'] is True
    assert result['coverage']['neighbors_examined'] == 100


def test_process_neighbor_database_failure_is_actionable_503():
    with patch.object(api.publisher,'_session_rows',side_effect=OSError('DB unavailable')):
        with pytest.raises(HTTPException) as failure:
            api._neighbors('root')
    assert failure.value.status_code == 503


def test_compatibility_callers_use_same_engine_and_preserve_scope():
    from backend.Services.similar_parts_recommender import SimilarPartsRecommender
    from backend.Services.change_impact_recommender import ChangeImpactRecommender
    from types import SimpleNamespace
    graph = Graph([record('root','Motor',ontology_id='one'),record('other','Motor',ontology_id='one')])
    adapter = SimpleNamespace(query=lambda query, params, timeout: graph._session_rows(query, **params))
    old = SimilarPartsRecommender(adapter).recommend('Motor', scope={'ontology_id':'one'}, node_id='root')
    assert old == RecommendationEngine(graph).similar('root', {'ontology_id':'one'})
    assert ChangeImpactRecommender(adapter).analyse(part_name='Motor',scope={'node_id':'root','ontology_id':'one'}) == RecommendationEngine(graph).impact('root',{'ontology_id':'one'})


def test_each_candidate_has_separate_policy_subject_without_score_as_confidence():
    from backend.depo_platform.decision_policy import assess_recommendation
    result = {'similar_parts':[{'node_id':'a','name':'Bearing','conflicts':['diameter'],'evidence_coverage':.5},
                              {'node_id':'b','name':'Shaft','conflicts':[],'evidence_coverage':.1}]}
    with patch('backend.depo_platform.decision_policy.assess_decisions', return_value={'status':'not_configured'}) as assess:
        assessed = assess_recommendation(result,'similar-parts',{'ontology_id':'selected'})
    decisions = assess.call_args.args[1]
    assert [item['candidate_id'] for item in decisions] == ['a','b']
    assert decisions[0]['conflicts'] == ['diameter']
    assert all(item['confidence_basis'] == 'not_established' for item in decisions)
    assert assessed['advisory_only']


def test_engine_holds_publication_barrier_across_queries(monkeypatch):
    from contextlib import contextmanager
    active=[]
    @contextmanager
    def access():
        active.append(True)
        try: yield
        finally: active.pop()
    graph=Graph([record('root','Part')])
    original=graph._session_rows
    def query(*args,**kwargs):
        assert active
        return original(*args,**kwargs)
    monkeypatch.setattr('backend.depo_platform.graph_access.projection_access',access)
    graph._session_rows=query
    RecommendationEngine(graph).similar('root')
    assert not active


def test_retained_vocabulary_literals_compare_with_units_and_provenance():
    import json
    props={'rdf_properties':json.dumps({'https://customer.example/vocabulary#diameter':[{'value':'25.4','unit':'mm'}]}),'artifact_digest':'source-v1','password':'never exposed'}
    rows=[record('root','Part',**props),record('other','Replacement',diameter='1 in')]
    result=RecommendationEngine(Graph(rows)).similar('root')
    comparison=next(item for item in result['similar_parts'][0]['engineering_comparisons'] if item['property']=='diameter')
    assert comparison['status']=='match'
    assert result['source_evidence']['artifact_digest']=='source-v1'
    assert 'password' not in str(result)


def test_dependency_query_filters_before_limit_and_uses_a_deadline():
    graph=Graph([record('root','Part')])
    RecommendationEngine(graph).impact('root')
    query,params=graph.calls[-1]
    assert query.index('WHERE relation IN $relations') < query.index('LIMIT 601')
    assert 0 < params['_timeout_seconds'] <= 20


def test_read_failure_is_an_actionable_service_error():
    from types import SimpleNamespace
    def fail(*args,**kwargs):raise RuntimeError('database unavailable')
    with pytest.raises(HTTPException) as error:
        RecommendationEngine(SimpleNamespace(_session_rows=fail)).similar('root')
    assert error.value.status_code==503
    assert 'database unavailable' not in error.value.detail


def test_unsupported_legacy_scope_cannot_broaden_to_all_customer_data():
    with pytest.raises(HTTPException) as error:
        RecommendationEngine(Graph([record('root','Part')])).similar('root',{'namespaces':['one']})
    assert error.value.status_code==422
