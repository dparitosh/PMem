import json
import pytest
from rdflib import Graph, URIRef, RDF, RDFS, OWL, Literal
from rdflib.namespace import SKOS
from backend.ontology_service.governance import audit_ontology, change_impact, policy, bridge_findings

PREFIX='@prefix ex: <urn:ex:> . @prefix owl: <http://www.w3.org/2002/07/owl#> . @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> . '

def record(text, **extra):
 return {'turtle':PREFIX+text,'source_ontology_ids':['one','two'],'sources':[{'ontology_id':'one','artifact_sha256':'a'*64},{'ontology_id':'two','artifact_sha256':'b'*64}], 'semantic_checks':{'shacl_conforms':True,'shape_digests':['shape-v1'],'owl_rl_performed':True}, **extra}

@pytest.fixture(autouse=True)
def profile(monkeypatch):
 monkeypatch.delenv('ONTOLOGY_GOVERNANCE_POLICY_FILE', raising=False)
 monkeypatch.setenv('ONTOLOGY_GOVERNANCE_PROFILE','imported_standard')

def test_source_iris_and_missing_editorial_metadata_are_preserved():
 value=record('ex:Part a owl:Class .')
 report=audit_ontology(value)
 assert report['overall_verdict']=='APPROVED'
 assert report['metrics']['findings']==2
 assert report['automatic_changes_applied'] is False
 assert report['coverage']['foundation_alignment']=='not_configured'
 assert all(row['subject_uri']=='urn:ex:Part' for row in report['violations_and_remediations'])
 assert 'skos:definition' not in value['turtle']
 Graph().parse(data=report['provenance_turtle'],format='turtle')

def test_curated_profile_quarantines_missing_definitions(monkeypatch):
 monkeypatch.setenv('ONTOLOGY_GOVERNANCE_PROFILE','enterprise_curated')
 report=audit_ontology(record('ex:Part a owl:Class .'))
 assert report['overall_verdict']=='REJECTED'
 assert report['metrics']['quarantined_subjects']==1

def test_foundation_alignment_is_configured_and_transitive(tmp_path, monkeypatch):
 path=tmp_path/'policy.json';path.write_text(json.dumps({'upper_class_iris':['urn:ex:Entity']}))
 monkeypatch.setenv('ONTOLOGY_GOVERNANCE_POLICY_FILE',str(path))
 report=audit_ontology(record('ex:Part a owl:Class; rdfs:subClassOf ex:Product . ex:Product a owl:Class; rdfs:subClassOf ex:Entity . ex:Unknown a owl:Class .'))
 assert [row['subject_uri'] for row in report['violations_and_remediations'] if row['issue_category']=='FOUNDATIONAL_ALIGNMENT']==['urn:ex:Unknown']

def test_identity_is_quarantined_without_a_silent_skos_downgrade(tmp_path,monkeypatch):
 value=record('ex:Design owl:sameAs ex:Serialized .')
 assert audit_ontology(value)['overall_verdict']=='REJECTED'
 assert 'sameAs' in value['turtle'] and 'exactMatch' not in value['turtle']
 path=tmp_path/'policy.json';path.write_text(json.dumps({'approved_identity_pairs':[['urn:ex:Design','urn:ex:Serialized']]}))
 monkeypatch.setenv('ONTOLOGY_GOVERNANCE_POLICY_FILE',str(path))
 assert audit_ontology(value)['overall_verdict']=='APPROVED'
 value['turtle']+='ex:Design owl:differentFrom ex:Serialized .'
 assert audit_ontology(value)['overall_verdict']=='REJECTED'

def test_selected_individuals_and_configured_viewpoints_need_identity_review():
 evidence={'source_iri':'urn:ex:Design','target_iri':'urn:ex:Serialized','individual':True}
 report=audit_ontology(record('ex:Serialized a owl:NamedIndividual .',mapping_evidence=[evidence],changes={'entity_mappings':[evidence]}))
 assert report['overall_verdict']=='REJECTED'

def test_cycles_are_review_findings_not_automatic_contradictions():
 report=audit_ontology(record('ex:A a owl:Class; rdfs:subClassOf ex:B . ex:B a owl:Class; rdfs:subClassOf ex:A .'))
 assert report['overall_verdict']=='APPROVED'
 assert any(row['issue_category']=='TAXONOMY_REVIEW' for row in report['violations_and_remediations'])

def test_incomplete_semantic_checks_and_missing_provenance_never_pass():
 assert audit_ontology(record('ex:A a owl:Class .',semantic_checks={}))['overall_verdict']=='PENDING_VALIDATION'
 assert audit_ontology(record('ex:A a owl:Class .',sources=[]))['overall_verdict']=='REJECTED'
 assert audit_ontology(record('ex:A a owl:Class .',removed_active_iris=['urn:ex:Active']))['overall_verdict']=='REJECTED'

def test_finding_limit_does_not_hide_blocking_counts(monkeypatch):
 monkeypatch.setenv('ONTOLOGY_GOVERNANCE_PROFILE','enterprise_curated')
 report=audit_ontology(record(' '.join(f'ex:A{i} a owl:Class .' for i in range(110))))
 assert len(report['violations_and_remediations'])==200
 assert report['metrics']['findings']==220 and report['findings_truncated']
 assert report['metrics']['quarantined_subjects']==110

def test_policy_binding_and_version_impact_are_explicit(monkeypatch):
 first=audit_ontology(record('ex:A a owl:Class .'))
 monkeypatch.setenv('ONTOLOGY_GOVERNANCE_PROFILE','enterprise_curated')
 assert first['policy_sha256']!=audit_ontology(record('ex:A a owl:Class .'))['policy_sha256']
 a,b=URIRef('urn:a'),URIRef('urn:b')
 assert change_impact({(a,RDFS.label,Literal('A'))},set())=='PATCH'
 assert change_impact({(a,RDF.type,OWL.Class)},set())=='MINOR'
 assert change_impact({(a,OWL.equivalentClass,b)},set())=='MAJOR'
 assert change_impact(set(),set())=='NONE'

def test_bridge_classification_is_distinct_from_identity():
 assert bridge_findings({'mapping_type':'rdf:type'})==[]
 assert bridge_findings({'predicate':str(OWL.sameAs)})==['identity_requires_domain_review']


def test_changed_policy_and_missing_mapping_evidence_hold_the_old_plan():
 value=record('ex:A a owl:Class .',governance_policy_sha256='old')
 assert audit_ontology(value)['overall_verdict']=='REJECTED'
 value=record('ex:A a owl:Class .',changes={'entity_mappings':[{'source_iri':'urn:a','target_iri':'urn:b'}]})
 assert audit_ontology(value)['overall_verdict']=='REJECTED'


@pytest.mark.parametrize('content',[{'require_definitions':'true'},{'unknown':True},{'approved_identity_pairs':[['not-an-iri','urn:valid']]}])
def test_invalid_policy_fails_closed(tmp_path,monkeypatch,content):
 path=tmp_path/'policy.json';path.write_text(json.dumps(content))
 monkeypatch.setenv('ONTOLOGY_GOVERNANCE_POLICY_FILE',str(path))
 with pytest.raises(ValueError):policy()


def test_authored_identity_allowlist_cannot_override_viewpoint(tmp_path,monkeypatch):
 path=tmp_path/'policy.json';path.write_text(json.dumps({'approved_identity_pairs':[['urn:ex:Design','urn:ex:Serialized']], 'identity_context_predicates':['urn:ex:view']}))
 monkeypatch.setenv('ONTOLOGY_GOVERNANCE_POLICY_FILE',str(path))
 for tail in ['', 'ex:Design ex:view "design" . ex:Serialized ex:view "physical" .']:
  assert audit_ontology(record('ex:Design owl:sameAs ex:Serialized .'+tail))['overall_verdict']=='REJECTED'
 assert audit_ontology(record('ex:Design owl:sameAs ex:Serialized; ex:view "design" . ex:Serialized ex:view "design" .'))['overall_verdict']=='APPROVED'

def test_same_length_evidence_for_another_pair_is_rejected():
 report=audit_ontology(record('ex:A a owl:Class .',changes={'entity_mappings':[{'source_iri':'urn:a','target_iri':'urn:b'}]},mapping_evidence=[{'source_iri':'urn:c','target_iri':'urn:d'}]))
 assert report['overall_verdict']=='REJECTED'
 assert any(row['issue_category']=='VALIDATION_COVERAGE' for row in report['violations_and_remediations'])

def test_missing_owl_rl_validation_is_pending():
 assert audit_ontology(record('ex:A a owl:Class .',semantic_checks={'shacl_conforms':True}))['overall_verdict']=='PENDING_VALIDATION'

def test_worker_roundtrip_and_fail_closed(monkeypatch):
 from backend.ontology_service.governance import audit_ontology_bounded
 import subprocess
 from types import SimpleNamespace
 assert audit_ontology_bounded(record('ex:A a owl:Class .'))['overall_verdict']=='APPROVED'
 def timeout(*args,**kwargs):raise subprocess.TimeoutExpired(args[0],kwargs['timeout'])
 monkeypatch.setattr(subprocess,'run',timeout)
 with pytest.raises(ValueError,match='timed out'):audit_ontology_bounded(record(''))
 monkeypatch.setattr(subprocess,'run',lambda *a,**kw:SimpleNamespace(returncode=0,stdout=b'bad-json'))
 with pytest.raises(ValueError,match='invalid evidence'):audit_ontology_bounded(record(''))
 monkeypatch.setattr(subprocess,'run',lambda *a,**kw:SimpleNamespace(returncode=1,stdout=b''))
 with pytest.raises(ValueError,match='failed'):audit_ontology_bounded(record(''))
