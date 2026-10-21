from backend.Services import owlready_runtime as runtime
from backend.ingestion_service.api import ontology_browser


def test_retained_draft_terms_remain_browseable_without_optional_owlready(tmp_path, monkeypatch):
    source = tmp_path / 'draft.ttl'
    source.write_text('''@prefix ex: <urn:terms:> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
ex:A a owl:Class .
ex:B a owl:Class .
[] a owl:Class .
ex:p a owl:DatatypeProperty ; rdfs:label "status" ; rdfs:domain ex:A ; rdfs:range xsd:string .
ex:q a owl:DatatypeProperty ; rdfs:label "status" ; rdfs:domain ex:B ; rdfs:range xsd:int .
''')
    monkeypatch.setattr(runtime, 'OWLREADY2_AVAILABLE', False)
    result = runtime.OwlreadyOntologyRuntime.inspect_ontology(source, 'ex')
    assert result['status'] == 'success'
    assert result['engine'] == 'rdflib'
    assert result['owlready2_available'] is False
    assert len(result['classes']) == 2  # anonymous expressions are not named classes
    assert len(result['datatype_properties']) == 2
    # Simulate identical human labels to verify the dictionary preserves IRIs.
    for row in result['datatype_properties']:
        row['label'] = 'status'
    monkeypatch.setattr(ontology_browser.OntologyReasoningService, 'get_reasoning', lambda _: result)
    monkeypatch.setattr(ontology_browser.GraphDatabase, 'driver', lambda *a, **kw: (_ for _ in ()).throw(AssertionError('Draft browsing must not require Neo4j')))
    dictionary = ontology_browser.data_dictionary('draft_id')
    assert dictionary['total_terms'] == 4
    assert {row['iri'] for row in dictionary['data']['properties'].values()} == {'urn:terms:p', 'urn:terms:q'}


def test_invalid_artifact_does_not_claim_success_without_optional_runtime(tmp_path, monkeypatch):
    source = tmp_path / 'bad.ttl'
    source.write_text('not valid turtle !')
    monkeypatch.setattr(runtime, 'OWLREADY2_AVAILABLE', False)
    assert runtime.OwlreadyOntologyRuntime.inspect_ontology(source)['status'] != 'success'
