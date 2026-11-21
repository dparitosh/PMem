import hashlib
from types import SimpleNamespace
from unittest.mock import patch
import pytest
from rdflib import Graph, Namespace, URIRef, BNode, Literal
from rdflib.collection import Collection
from rdflib.namespace import RDF, RDFS, OWL, XSD
from backend.ontology_service.rule_assessment import assess, retained_rule, rdf_list
from backend.depo_platform.shacl_core import check_shacl_core

E=Namespace('urn:inspection:'); S=Namespace('http://www.w3.org/2003/11/swrl#'); SH=Namespace('http://www.w3.org/ns/shacl#')

def fixture():
    g=Graph()
    g.add((E.Inspection,RDFS.subClassOf,E.Measurement))
    for index in range(1000):
        subject=E[f'record-{index}']
        g.add((subject,RDF.type,E.Inspection))
        g.add((subject,E.value,Literal('30.025' if index==999 else '30.020',datatype=XSD.decimal)))
    g.add((E.Shape,RDF.type,SH.NodeShape));g.add((E.Shape,SH.targetClass,E.Measurement))
    p=BNode();g.add((E.Shape,SH.property,p));g.add((p,SH.path,E.value));g.add((p,SH.minCount,Literal(1)));g.add((p,SH.datatype,XSD.decimal))
    for v in (E.i,E.v):g.add((v,RDF.type,S.Variable))
    def atom(kind,**props):
        a=BNode();g.add((a,RDF.type,S[kind]))
        for k,v in props.items():g.add((a,S[k],v))
        return a
    args=BNode();Collection(g,args,[E.v,Literal('30.024',datatype=XSD.decimal)])
    body=[atom('ClassAtom',classPredicate=E.Measurement,argument1=E.i),
          atom('DatavaluedPropertyAtom',propertyPredicate=E.value,argument1=E.i,argument2=E.v),
          atom('BuiltinAtom',builtin=URIRef('http://www.w3.org/2003/11/swrlb#greaterThan'),arguments=args)]
    head=[atom('ClassAtom',classPredicate=E.AboveLimit,argument1=E.i)]
    g.add((E.rule,RDF.type,S.Imp));g.add((E.rule,OWL.versionInfo,Literal('1.0.0')))
    for pred,items in ((S.body,body),(S.head,head)):
        h=BNode();Collection(g,h,items);g.add((E.rule,pred,h))
    return g

def catalog(g,status='approved',bad_hash=False):
    content=g.serialize(format='turtle').encode()
    return SimpleNamespace(read_artifact=lambda oid:({'lifecycle_status':status,'artifact_id':'sha256:'+('bad' if bad_hash else hashlib.sha256(content).hexdigest())},content),
        _parse_ontology=lambda *args,**kwargs:{'graph':g})

def test_owned_rules_derive_types_and_preserve_measurement_evidence():
    g=fixture()
    result=assess(catalog(g),'release')
    assert result['status']=='completed'
    assert result['shacl']['targeted_subjects']==1000
    assert result['summary']=={'rules':1,'executed':1,'conclusions':1}
    row=result['rules'][0]['rows'][0]
    assert row['subject']==str(E['record-999'])
    assert any(i['value']=='30.025' for i in row['inputs'])
    assert any(i['asserted'] is False and i['support_facts'] for i in row['inputs'])
    assert (E['record-999'],RDF.type,E.Measurement) not in g
    assert result['publication_authorized'] is False

@pytest.mark.parametrize('status,bad_hash',[('draft',False),('approved',True)])
def test_unapproved_or_changed_source_is_rejected(status,bad_hash):
    with pytest.raises(ValueError):assess(catalog(fixture(),status,bad_hash),'release')

def test_shacl_violation_blocks_execution():
    g=fixture();g.remove((E['record-0'],E.value,None))
    result=assess(catalog(g),'release')
    assert result['status']=='blocked' and result['summary']['executed']==0

def test_zero_targets_are_not_conformance():
    g=fixture();g.remove((E.Shape,SH.targetClass,None));g.add((E.Shape,SH.targetClass,E.Unrelated))
    result=check_shacl_core(g,g)
    assert result['status']=='no_targets' and result['conforms'] is None

def test_executable_shapes_and_cyclic_rule_lists_are_rejected():
    g=fixture();g.add((E.Shape,SH.sparql,E.code))
    with pytest.raises(ValueError):check_shacl_core(g,g)
    h=BNode();g.add((h,RDF.first,E.i));g.add((h,RDF.rest,h))
    with pytest.raises(ValueError):rdf_list(g,h)

def test_no_rules_does_not_claim_execution_or_validation():
    r=assess(catalog(Graph()),'release')
    assert r['status']=='no_rules' and r['summary']['executed']==0 and 'shacl' not in r

def test_unsupported_builtin_rejects_whole_release():
    g=fixture();a=next(g.subjects(S.builtin,None));g.set((a,S.builtin,URIRef('http://www.w3.org/2003/11/swrlb#multiply')))
    with pytest.raises(ValueError):retained_rule(g,E.rule)


def test_ambiguous_atom_kind_cannot_be_silently_interpreted():
    g=fixture();a=next(g.subjects(S.classPredicate,None));g.add((a,RDF.type,S.BuiltinAtom))
    with pytest.raises(ValueError):retained_rule(g,E.rule)

def test_blank_rule_version_is_rejected():
    g=fixture();g.set((E.rule,OWL.versionInfo,Literal(' ')))
    with pytest.raises(ValueError):retained_rule(g,E.rule)
