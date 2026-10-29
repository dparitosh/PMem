import json
import subprocess
from pathlib import Path
from unittest.mock import patch
import pytest
from rdflib import Graph, OWL, RDF, RDFS, URIRef
from backend.ontology_service import owl_dl
from backend.ontology_service.foundation import foundation, foundation_summary, alignment_coverage


def rdf(text):
    return Graph().parse(data='@prefix owl:<http://www.w3.org/2002/07/owl#> . @prefix rdfs:<http://www.w3.org/2000/01/rdf-schema#> . '+text,format='turtle')


def require_engine():
    assert owl_dl.capabilities()['available'], 'Build the bundled reasoner and provide Java; actual reasoning tests must not silently skip'


def test_embedded_foundation_is_original_versioned_offline_reference():
    meta, graph = foundation()
    assert meta['version']=='4.2' and len(meta['bundle_sha256'])==64
    assert not list(graph.objects(None,OWL.imports))
    assert (URIRef('urn:depo:business:PhysicalPart'),RDFS.subClassOf,URIRef('http://rds.posccaesar.org/ontology/lis14/rdl/PhysicalArtefact')) in graph
    assert foundation_summary()['alignment_approved'] is False


def test_real_ido_plus_depo_foundation_is_consistent_and_coherent():
    require_engine()
    meta, graph = foundation()
    result = owl_dl.inspect_graph(graph,artifact_sha256=meta['bundle_sha256'])
    assert result['status']=='consistent' and result['consistency_verified']
    assert result['deductive_reasoner_executed'] and result['modeling_coherent']
    assert result['unsatisfiable_class_count']==0
    assert result['iso_conformance_established'] is False


def test_real_reasoner_detects_disjoint_instance_contradiction():
    require_engine()
    graph=rdf('<urn:A> a owl:Class ; owl:disjointWith <urn:B> . <urn:B> a owl:Class . <urn:item> a <urn:A>,<urn:B> .')
    result=owl_dl.inspect_graph(graph,artifact_sha256='disjoint-fixture')
    assert result['status']=='inconsistent' and result['consistency_verified']
    assert result['modeling_coherent'] is False


def test_unsatisfiable_class_is_distinguished_from_global_inconsistency():
    require_engine()
    graph=rdf('<urn:A> a owl:Class ; rdfs:subClassOf <urn:B>,<urn:C> . <urn:B> a owl:Class ; owl:disjointWith <urn:C> . <urn:C> a owl:Class .')
    result=owl_dl.inspect_graph(graph,artifact_sha256='unsat-fixture')
    assert result['status']=='consistent' and result['consistency_verified']
    assert 'urn:A' in result['unsatisfiable_classes']
    assert result['modeling_coherent'] is False


def test_real_profile_violation_is_unsupported_not_consistent():
    require_engine()
    result=owl_dl.inspect_graph(rdf('<urn:p> a owl:ObjectProperty,owl:DatatypeProperty .'),artifact_sha256='profile-fixture')
    assert result['status']=='unsupported'
    assert not result['consistency_verified'] and not result['deductive_reasoner_executed']


def test_remote_import_never_fetches_or_starts_java():
    with patch.object(owl_dl.subprocess,'run') as run:
        result=owl_dl.inspect_graph(rdf('<urn:o> a owl:Ontology ; owl:imports <https://untrusted.invalid/ontology> .'),artifact_sha256='remote')
    run.assert_not_called()
    assert result['reason']=='unresolved_imports' and not result['consistency_verified']


def test_timeout_is_unknown_and_releases_execution_slot():
    with patch.object(owl_dl,'capabilities',return_value={'available':True}), patch.object(owl_dl.subprocess,'run',side_effect=subprocess.TimeoutExpired('java',1)):
        result=owl_dl.inspect_graph(rdf('<urn:A> a owl:Class .'),artifact_sha256='timeout')
    assert result['status']=='unknown' and result['reason']=='reasoner_timeout'
    assert owl_dl._slot.acquire(blocking=False)
    owl_dl._slot.release()


def test_busy_reasoner_does_not_queue_or_claim_success():
    owl_dl._slot.acquire()
    try: result=owl_dl.inspect_graph(rdf('<urn:A> a owl:Class .'),artifact_sha256='busy')
    finally: owl_dl._slot.release()
    assert result['status']=='unknown' and result['reason']=='reasoner_busy'


def test_importing_reference_does_not_establish_alignment():
    _,base=foundation()
    graph=rdf('<urn:A> a owl:Class .')
    assert alignment_coverage(graph,base)['classes_with_foundation_path']==0
    graph.add((URIRef('urn:A'),RDFS.subClassOf,URIRef('urn:depo:business:PhysicalPart')))
    coverage=alignment_coverage(graph,base)
    assert coverage['classes_with_foundation_path']==1
    assert coverage['alignment_approved'] is False


def test_foundation_tamper_is_detected(tmp_path,monkeypatch):
    from backend.ontology_service import foundation as module
    for item in module.ROOT.iterdir():
        if item.is_file(): (tmp_path/item.name).write_bytes(item.read_bytes())
    (tmp_path/'ido-core-4.2.ttl').write_text('tampered')
    monkeypatch.setattr(module,'ROOT',tmp_path)
    with pytest.raises(ValueError,match='digest mismatch'):module.foundation()


def test_bundled_worker_tamper_is_unavailable(tmp_path,monkeypatch):
    (tmp_path/'depo-owl-dl.jar').write_bytes(b'not-the-worker')
    (tmp_path/'manifest.json').write_text(json.dumps({'sha256':'0'*64}))
    monkeypatch.setattr(owl_dl,'RESOURCE',tmp_path)
    assert owl_dl.capabilities()['available'] is False


def test_existing_agents_have_read_only_foundation_and_reasoning_tools():
    from backend.agentic_service.catalog_loader import load_catalog
    catalog=load_catalog()
    tools={item['id']:item for item in catalog['tools']}
    for name in ('ontology.foundation.inspect','ontology.consistency.check'):
        assert tools[name]['mutates'] is False and tools[name]['method']=='GET'
    for agent in catalog['agents']:
        if agent['id'] in ('ontology-governor','ontology-steward','ontology-inference','graph-analyst'):
            assert 'ontology.consistency.check' in agent['tools']


def test_retained_results_are_bound_to_changed_artifact_bytes():
    from types import SimpleNamespace
    from backend.mesh_store import InMemoryRegistry
    from backend.ontology_service.catalog import OntologyCatalog
    content=[b'@prefix owl:<http://www.w3.org/2002/07/owl#> . <urn:A> a owl:Class .']
    catalog=SimpleNamespace(read_artifact=lambda identifier:({'original_filename':'a.ttl'},content[0]),_parse_ontology=OntologyCatalog._parse_ontology)
    store=InMemoryRegistry()
    first=owl_dl.inspect_retained('selected',catalog,store)
    second=owl_dl.inspect_retained('selected',catalog,store)
    assert first['status']=='consistent' and second['cached']
    content[0]+=b' <urn:B> a owl:Class .'
    third=owl_dl.inspect_retained('selected',catalog,store)
    assert not third['cached'] and third['evidence_id'] != first['evidence_id']
    assert third['artifact_sha256'] != first['artifact_sha256']


def test_reasoner_agent_budget_exceeds_bounded_process_deadline(monkeypatch):
    from backend.agentic_service.tool_timeouts import tool_timeout_seconds
    monkeypatch.setenv('DEPO_REASONER_TIMEOUT_SECONDS','60')
    assert tool_timeout_seconds({'id':'ontology.consistency.check'}, {}) >= 90


def test_oversized_retained_input_is_rejected_before_parsing(monkeypatch):
    from types import SimpleNamespace
    monkeypatch.setattr(owl_dl,'MAX_SOURCE_BYTES',2)
    parser=SimpleNamespace(read_artifact=lambda identifier:({},b'large'),_parse_ontology=lambda *args:pytest.fail('Must not parse oversized data'))
    result=owl_dl.inspect_retained('selected',parser,None)
    assert result['reason']=='source_size_budget_exceeded' and not result['consistency_verified']


def test_simultaneous_retained_checks_do_not_parse_or_open_more_sources():
    owl_dl._request_slot.acquire()
    try: result=owl_dl.inspect_retained('selected',None,None)
    finally: owl_dl._request_slot.release()
    assert result['status']=='unknown' and result['reason']=='reasoner_busy'


def test_worker_has_independent_wall_clock_exit_even_without_api_timeout(tmp_path):
    import shutil
    from backend.ontology_service.foundation import ROOT
    process=subprocess.run([shutil.which('java'),'-Ddepo.reasoner.maxMillis=50','-Xmx512m','-jar',str(owl_dl.RESOURCE/'depo-owl-dl.jar'),str(ROOT/'ido-core-4.2.ttl'),str(tmp_path/'never-success.json')],
        timeout=10,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
        creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    assert process.returncode==124
    assert not (tmp_path/'never-success.json').exists()
