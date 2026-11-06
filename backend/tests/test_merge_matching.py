from rdflib import Graph, URIRef, Literal, RDF, RDFS, OWL
from backend.ontology_service.merge_matching import match_entities


def term(graph, iri, label, kind=OWL.Class):
    subject = URIRef(iri)
    graph.add((subject, RDF.type, kind))
    graph.add((subject, RDFS.label, Literal(label)))
    return subject


def test_camel_case_tokens_and_trigrams_propose_different_labels():
    source, target = Graph(), Graph()
    term(source, 'urn:source:dimension', 'NominalDiameter')
    term(target, 'urn:target:dimension', 'Nominal Diameter')
    rows, report = match_entities(source, target)
    assert len(rows) == 1
    assert rows[0]['confidence_score'] == .8
    assert rows[0]['score_components']['character_trigrams'] == 1
    assert rows[0]['requires_review'] is True
    assert report['policy'] == 'lexical-context-v2'


def test_property_kinds_and_context_are_compared_without_cross_kind_matches():
    source, target = Graph(), Graph()
    a = term(source, 'urn:a', 'hasDiameter', OWL.DatatypeProperty)
    b = term(target, 'urn:b', 'has Diameter', OWL.DatatypeProperty)
    term(target, 'urn:c', 'has Diameter', OWL.ObjectProperty)
    for graph, subject in [(source, a), (target, b)]:
        graph.add((subject, RDFS.range, URIRef('http://www.w3.org/2001/XMLSchema#decimal')))
        graph.add((subject, RDFS.comment, Literal('Nominal diameter of the part')))
    rows, _ = match_entities(source, target)
    assert len(rows) == 1
    assert rows[0]['target_iri'] == 'urn:b'
    assert rows[0]['confidence_score'] == 1
    assert rows[0]['score_components']['property_context'] == 1
    assert rows[0]['source_evidence']['ranges']


def test_ambiguous_alternatives_remain_explicit_and_deterministic():
    source, target = Graph(), Graph()
    term(source, 'urn:a', 'Part')
    term(target, 'urn:b', 'Part')
    term(target, 'urn:c', 'Part')
    rows, _ = match_entities(source, target)
    assert len(rows) == 2 and all(row['ambiguous'] for row in rows)
    assert rows == match_entities(source, target)[0]


def test_shared_iri_and_unrelated_labels_are_not_proposals():
    source, target = Graph(), Graph()
    term(source, 'urn:shared', 'Part')
    term(target, 'urn:shared', 'Part')
    term(target, 'urn:unrelated', 'Temperature')
    assert match_entities(source, target)[0] == []


def test_spelling_variation_is_ranked_by_label_and_ngram_evidence():
    source, target = Graph(), Graph()
    term(source, 'urn:a', 'Nominal Diametre')
    term(target, 'urn:b', 'Nominal Diameter')
    rows, _ = match_entities(source, target)
    assert len(rows) == 1
    assert .55 <= rows[0]['confidence_score'] < .8


def test_reversed_property_roles_do_not_receive_context_credit():
    source, target = Graph(), Graph()
    a = term(source, 'urn:a', 'uses', OWL.ObjectProperty)
    b = term(target, 'urn:b', 'uses', OWL.ObjectProperty)
    source.add((a, RDFS.domain, URIRef('urn:Part')))
    source.add((a, RDFS.range, URIRef('urn:Tool')))
    target.add((b, RDFS.domain, URIRef('urn:Tool')))
    target.add((b, RDFS.range, URIRef('urn:Part')))
    rows, _ = match_entities(source, target)
    assert rows[0]['score_components']['property_context'] == 0


def test_broad_candidate_buckets_report_incomplete_search():
    source, target = Graph(), Graph()
    term(source, 'urn:a', 'Part')
    for i in range(205): term(target, f'urn:{i}', 'Part')
    rows, report = match_entities(source, target)
    assert not rows
    assert report['truncated'] is True


def test_skos_synonyms_and_definitions_are_grounded_matching_evidence():
 from rdflib.namespace import SKOS
 source,target=Graph(),Graph()
 a=term(source,'urn:a','Deliverable Product')
 b=term(target,'urn:b','Finished Item')
 source.add((a,SKOS.altLabel,Literal('Finished Good')))
 target.add((b,SKOS.prefLabel,Literal('Finished Good')))
 for graph,subject in ((source,a),(target,b)):graph.add((subject,SKOS.definition,Literal('A product ready for delivery')))
 rows,_=match_entities(source,target)
 assert len(rows)==1 and rows[0]['score_components']['definitions']==1
 assert rows[0]['proposed_relation']=='unverified'
 assert rows[0]['source_evidence']['definitions']==['A product ready for delivery']
