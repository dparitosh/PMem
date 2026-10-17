"""Semantic inventories, graph rows, rule budgets and evidence alignment."""
import json
import pytest
from rdflib import Graph
from backend.depo_platform.ontology_semantics import inventory
from backend.depo_platform.projection_preparation import build_projection
from backend.Services.swrl_reasoning_service import SwrlRuleService as Rules, ApplicationRuleExecutor as Executor, SemanticFact

RDF = '''@prefix ex: <urn:ex:> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
ex:Part a rdfs:Class . ex:Label a owl:AnnotationProperty .
ex:mass a owl:DatatypeProperty; rdfs:range xsd:decimal .
ex:contains a owl:ObjectProperty; owl:inverseOf ex:inside .
ex:p a ex:Part; ex:mass "2.5"^^xsd:decimal .
ex:q a owl:NamedIndividual, ex:Part .
[] a owl:Axiom; owl:annotatedSource ex:Part .
'''

def test_inventory_and_projection_agree_without_modifying_assertions():
    graph = Graph().parse(data=RDF, format='turtle')
    original = set(graph)
    stats = inventory(graph)
    rows, edges, _ = build_projection(graph)
    by_id = {row['iri']: row for row in rows}
    assert stats['classes'] == 1 and stats['individuals'] == 2
    assert stats['named_individuals'] == 1 and stats['annotation_properties'] == 1
    assert stats['inverse_axioms'] == 1 and stats['axiom_annotations'] == 1
    assert by_id['urn:ex:Part']['kind'] == 'class'
    assert by_id['urn:ex:Label']['kind'] == 'property'
    assert by_id['urn:ex:p']['kind'] == 'individual'
    assert by_id['http://www.w3.org/2001/XMLSchema#decimal']['kind'] == 'datatype'
    assert json.loads(by_id['urn:ex:p']['rdf_properties'])['urn:ex:mass'][0]['datatype'].endswith('#decimal')
    assert any(row['predicate'].endswith('#inverseOf') for row in edges['SEMANTIC_RELATION'])
    assert set(graph) == original

def test_rules_preserve_quoted_conjunction_comma_and_all_support():
    rule = Rules.parse_rule({'expression': 'label(?x, "Pump, primary ^ AND") -> Selected(?x)'})
    assert Rules.validate(rule)['valid']
    assert rule.body[0].arguments[1] == 'Pump, primary ^ AND'
    rule = Rules.parse_rule({'expression': 'Part(?x) -> Selected(?x)'})
    result = Executor.execute(rule, [SemanticFact('p', 'http://www.w3.org/1999/02/22-rdf-syntax-ns#type', 'Part', 'a'),
        SemanticFact('p', 'rdf:type', 'Part', 'b')], 'test')
    assert result['inferred_facts'][0]['sourceFacts'] == ['a', 'b']

def test_rule_join_budget_rejects_cartesian_explosion():
    rule = Rules.parse_rule({'expression': 'p(?a, ?b) ^ p(?c, ?d) -> result(?a, ?d)'})
    facts = [SemanticFact(str(i), 'p', str(i)) for i in range(101)]
    with pytest.raises(ValueError, match='budget exceeded'):
        Executor.execute(rule, facts, 'test')


def test_taxonomy_exposes_instances_datatypes_and_disconnected_axioms(tmp_path):
    from backend.ontology_service.domain.taxonomy import OntologyTaxonomyService
    path = tmp_path / 'ontology.ttl'
    path.write_text(RDF, encoding='utf-8')
    result = OntologyTaxonomyService._parse_rdf({'prefix': 'ex'}, path)
    by_uri = {row['uri']: row for row in result['nodes']}
    assert by_uri['urn:ex:p']['source'] == 'rdf-individual'
    assert by_uri['http://www.w3.org/2001/XMLSchema#decimal']['source'] == 'rdf-datatype'
    assert any(edge['mapping_type'] == 'annotatedSource' for edge in result['edges'])
    assert any(edge['mapping_type'] == 'type' and edge['source_term'] == by_uri['urn:ex:p']['term_id'] for edge in result['edges'])

def test_catalog_semantic_statistics_use_canonical_rdf_types():
    from backend.ontology_service.catalog import OntologyCatalog
    assert OntologyCatalog._analytics_from_content(RDF.encode(), 'ontology.ttl') == inventory(Graph().parse(data=RDF, format='turtle'))


def test_registration_persists_inventory_in_authoritative_registry(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from backend.ontology_service import catalog as module
    from backend.mesh_store import InMemoryRegistry
    monkeypatch.setenv('DEPO_DATABASE_URL', 'postgresql://unused/test')
    monkeypatch.setattr(module, 'artifact_store', SimpleNamespace(ingest=lambda *a, **k: {'artifact_id': 'test-artifact'}))
    registry = InMemoryRegistry()
    catalog = module.OntologyCatalog(root=tmp_path, registry=registry)
    record = catalog._register(content=RDF.encode(), filename='ontology.ttl', ontology_name='Example', prefix='ex')
    stored = registry.get(record['ontology_id'])
    assert stored['statistics'] == inventory(Graph().parse(data=RDF, format='turtle'))
    assert stored['semantic_inventory_version'] == 1
    assert stored['lifecycle_status'] == 'draft'
    assert json.loads((tmp_path / record['ontology_id'] / 'metadata.json').read_text())['statistics'] == stored['statistics']

def test_cypher_reads_scoped_types_and_rdfs_class_mappings():
    from backend.graph_service import query_repository as queries
    assert 'rdf_types' in queries.ONTOLOGY_PROJECTION_NODES
    assert 'rdf_types' in queries.ONTOLOGY_SEARCH_NODES
    assert 'http://www.w3.org/2000/01/rdf-schema#Class' in queries.MAPPING_TERMS
    assert 't.ontology_id=n.ontology_id' in queries.MAPPING_TERMS


def test_inverse_preview_uses_assertions_and_openapi_contract(tmp_path, monkeypatch):
    from backend.ontology_service.domain.reasoning import OntologyReasoningService as Service
    from backend.depo_platform.request_bodies import InferenceBody
    from pydantic import TypeAdapter
    path = tmp_path / 'inverse.ttl'
    path.write_text(RDF + '\nex:p ex:contains ex:q .', encoding='utf-8')
    monkeypatch.setattr(Service, 'semantic_context', lambda _: {'file_path': path})
    monkeypatch.setattr(Service, 'inspect_context', lambda _: {})
    options = TypeAdapter(InferenceBody).validate_python({'rules': {'inverse_properties': True}, 'limit': 25})
    result = Service.preview_inferences('test', options)
    assert any(row['subject'] == 'urn:ex:q' and row['predicate'] == 'urn:ex:inside' and row['object'] == 'urn:ex:p' for row in result['inferences'])
    assert result['rules']['inverse_properties'] is True


def test_explicit_rule_namespaces_align_rdf_class_and_property_facts():
    rule = Rules.parse_rule({'expression': 'ex:Part(?x) ^ ex:has(?x, ?y) -> ex:Linked(?y)', 'namespaces': {'ex': 'urn:ex:'}})
    result = Executor.execute(rule, [SemanticFact('urn:p', 'http://www.w3.org/1999/02/22-rdf-syntax-ns#type', 'urn:ex:Part', 'a'),
        SemanticFact('urn:p', 'urn:ex:has', 'urn:q', 'b')], 'test')
    assert result['inferred_facts'][0]['object'] == 'urn:ex:Linked'
    assert result['inferred_facts'][0]['sourceFacts'] == ['a', 'b']


def test_namespaces_never_rewrite_quoted_literal_values():
    rule = Rules.parse_rule({'expression': 'ex:label(?x, "ex:literal") -> ex:Selected(?x)', 'namespaces': {'ex': 'urn:ex:'}})
    restored = Rules.parse_rule(Rules.to_dict(rule))
    for candidate in (rule, restored):
        result = Executor.execute(candidate, [SemanticFact('urn:p', 'urn:ex:label', 'ex:literal', 'a')], 'test')
        assert result['summary']['inferred_facts'] == 1


def test_reviewed_mapping_accepts_domain_typed_instances(tmp_path):
    from types import SimpleNamespace
    from backend.ontology_service.merge_service import GovernedMergeService
    content = lambda identity: ('''@prefix ex: <urn:ex:> .
        @prefix owl: <http://www.w3.org/2002/07/owl#> .
        @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
        @prefix dc: <http://purl.org/dc/elements/1.1/> .
        ex:Part a owl:Class; rdfs:label "Part"; rdfs:comment "A part"; dc:source ex:source .
        ex:''' + identity + ' a ex:Part .').encode()
    catalog = SimpleNamespace(get=lambda _: {'ontology_name': 'Example'},
        read_artifact=lambda key: ({'ontology_name': 'Example', 'original_filename': 'ontology.ttl'}, content(key)),
        _parse_ontology=lambda *a: {'rdf_format': 'turtle'})
    merge = GovernedMergeService(catalog, None, tmp_path)
    result = merge.preview({'source_ontology_ids': ['left', 'right'],
        'entity_mappings': [{'source_iri': 'urn:ex:left', 'target_iri': 'urn:ex:right'}]})
    assert result['changes']['modified_entity_count'] == 1
    assert result['semantic_checks']['shacl_conforms']


@pytest.mark.parametrize("arrow", ["->", "=>"])
def test_quoted_arrows_do_not_split_the_rule(arrow):
    rule = Rules.parse_rule({'expression': 'label(?x, "before ' + arrow + ' after") -> Selected(?x)'})
    result = Executor.execute(rule, [SemanticFact('part', 'label', 'before ' + arrow + ' after', 'evidence')], 'test')
    assert result['summary']['inferred_facts'] == 1


def test_repeated_rule_separators_are_rejected():
    with pytest.raises(ValueError, match='exactly one'):
        Rules.parse_rule({'expression': 'Part(?x) -> Selected(?x) -> Other(?x)'})


def test_backfill_preserves_approval_and_is_idempotent(tmp_path, monkeypatch):
    import copy
    from contextlib import nullcontext
    from backend.ontology_service import catalog as module
    from backend.mesh_store import InMemoryRegistry
    monkeypatch.setenv('DEPO_DATABASE_URL', 'postgresql://unused/test')
    registry = InMemoryRegistry()
    registry.advisory_lock = lambda _: nullcontext(True)
    catalog = module.OntologyCatalog(root=tmp_path, registry=registry)
    old = {'ontology_id': 'legacy', 'original_filename': 'ontology.ttl',
           'statistics': {'classes': 0}, 'lifecycle_status': 'approved',
           'provenance': {'approved_by': 'reviewer'}, 'lifecycle_events': []}
    registry.put('legacy', copy.deepcopy(old))
    monkeypatch.setattr(catalog, 'read_artifact', lambda _: (registry.get('legacy'), RDF.encode()))
    backfill = module.OntologyCatalog.backfill_analytics.__wrapped__
    result = backfill(catalog, ontology_ids=['legacy'], actor='operator')
    assert result['updated'] == 1
    updated = copy.deepcopy(registry.get('legacy'))
    assert updated['lifecycle_status'] == 'approved'
    assert updated['provenance'] == old['provenance']
    assert updated['statistics'] == inventory(Graph().parse(data=RDF, format='turtle'))
    assert updated['semantic_inventory_version'] == 1
    assert backfill(catalog, ontology_ids=['legacy'], actor='operator')['updated'] == 0
    assert registry.get('legacy') == updated


def test_rule_api_keeps_zero_valued_facts():
    import asyncio
    from backend.routes.ontology_routes import SwrlRuleRequest, execute_swrl_rule_preview
    request = SwrlRuleRequest(expression='value(?x, ?v) ^ swrlb:equal(?v, 0) -> Zero(?x)',
        facts=[{'subject': 'part', 'predicate': 'value', 'object': 0, 'id': 'zero'}])
    result = asyncio.run(execute_swrl_rule_preview(request))
    assert result['summary']['source_facts'] == 1
    assert result['inferred_facts'][0]['sourceFacts'] == ['zero']
