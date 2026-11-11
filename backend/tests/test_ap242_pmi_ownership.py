"""PMI ownership needs a source-defined chain, never filename co-occurrence."""
from backend.ceim.ap242_adapter import ap242_to_ceim_batch
from backend.ceim.contract import contract
from rdflib import Namespace
import pytest


def source(extra='', feature_shape='#4'):
    return ("ISO-10303-21;HEADER;FILE_SCHEMA(('AP242_MANAGED_MODEL_BASED_3D_ENGINEERING'));ENDSEC;DATA;"
        "#1=PRODUCT('P1','Housing','',());"
        "#2=PRODUCT_DEFINITION_FORMATION('A','',#1);"
        "#3=PRODUCT_DEFINITION('design','',#2,#9);"
        "#4=PRODUCT_DEFINITION_SHAPE('','',#3);"
        f"#5=SHAPE_ASPECT('bore','',{feature_shape},.T.);"
        "#6=DIMENSIONAL_SIZE(#5,'diameter');"
        "#9=PRODUCT_DEFINITION_CONTEXT('design',#10,'design');"
        "#10=APPLICATION_CONTEXT('mechanical design');" + extra +
        "ENDSEC;END-ISO-10303-21;").encode()


def ownership(batch):
    return [r for r in batch['relationships'] if r['provenance']['source_type']=='verified_pmi_characteristic']


def test_source_defined_dimension_owner_is_preserved_in_rdf():
    batch=ap242_to_ceim_batch(source(),filename='part.stp')
    links=ownership(batch)
    assert len(links)==1
    assert links[0]['relationship']=='HAS_CHARACTERISTIC'
    assert links[0]['source_id'].endswith('ap242:3')
    assert links[0]['target_id'].endswith('ap242:6')
    assert links[0]['provenance']['source_key']=='STEP:#6->#5->#4->#3'
    graph=contract.to_rdf(entities=batch['entities'],relationships=batch['relationships'])
    ceim=Namespace(contract.namespace)
    assert len(list(graph.triples((None,ceim.hasCharacteristic,None))))==1
    assert len(list(graph.triples((None,ceim.sourceKey,None))))>0


def test_product_in_same_document_is_not_ownership():
    batch=ap242_to_ceim_batch(source(feature_shape='#10'),filename='part.stp')
    assert not ownership(batch)


def test_two_explicit_owners_are_held():
    extra="#11=PRODUCT_DEFINITION('other','',#2,#9);#12=PRODUCT_DEFINITION_SHAPE('','',#11);"
    batch=ap242_to_ceim_batch(source(extra,feature_shape='(#4,#12)'),filename='part.stp')
    assert not ownership(batch)


def test_changed_mapping_requires_review_of_old_batches():
    batch=ap242_to_ceim_batch(source(),filename='part.stp')
    assert ownership(batch)[0]['provenance']['mapping_version']=='0.4.0'
    assert contract.validate_projection(entities=batch['entities'],relationships=batch['relationships'])['conforms']
    batch['entities'][0]['provenance']['mapping_version']='0.3.0'
    with pytest.raises(ValueError,match='mapping_version'):
        contract.validate_mapping_evidence(standard='ap242',entities=batch['entities'],relationships=batch['relationships'])


def test_dimension_between_two_features_requires_both_owners():
    raw=source(extra="#11=SHAPE_ASPECT('unresolved','',#10,.T.);")
    raw=raw.replace(b"#6=DIMENSIONAL_SIZE(#5,'diameter');",b"#6=DIMENSIONAL_LOCATION('distance','',#5,#11);")
    assert not ownership(ap242_to_ceim_batch(raw,filename='part.stp'))


def test_dimension_between_same_product_features_is_one_association():
    raw=source(extra="#11=SHAPE_ASPECT('other bore','',#4,.T.);")
    raw=raw.replace(b"#6=DIMENSIONAL_SIZE(#5,'diameter');",b"#6=DIMENSIONAL_LOCATION('distance','',#5,#11);")
    links=ownership(ap242_to_ceim_batch(raw,filename='part.stp'))
    assert len(links)==1
    assert '#6->#5->#4->#3' in links[0]['provenance']['source_key']
    assert '#6->#11->#4->#3' in links[0]['provenance']['source_key']


def test_reference_in_wrong_attribute_does_not_assert_ownership():
    raw=source().replace(b"#6=DIMENSIONAL_SIZE(#5,'diameter');",b"#6=DIMENSIONAL_SIZE($,#5);")
    assert not ownership(ap242_to_ceim_batch(raw,filename='part.stp'))


def test_argument_parser_preserves_strings_and_aggregates():
    from backend.ceim.ap242_pmi import arguments
    assert arguments("'bore, O''Brien',(#4,#5),#6")==["'bore, O''Brien'",'(#4,#5)','#6']
    assert arguments("'unclosed")==[]
    assert arguments('(unclosed')==[]


def test_compound_shape_aspect_is_not_promoted():
    raw=source().replace(b"#5=SHAPE_ASPECT('bore','',#4,.T.);",b"#5=(SHAPE_ASPECT('bore','',#4,.T.) COMPOSITE_SHAPE_ASPECT());")
    assert not ownership(ap242_to_ceim_batch(raw,filename='part.stp'))
