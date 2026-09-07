from pathlib import Path

from rdflib import Graph, Namespace, RDF, RDFS, URIRef
from backend.ceim.ap242_adapter import ap242_to_ceim_batch
from backend.ceim.contract import contract
from backend.ceim.qif_adapter import qif_to_ceim_batch
from backend.tests.test_ap242_mbd import AP242_PART21


ROOT = Path(__file__).resolve().parents[2] / "ontology"
BOC = Namespace("https://depo.example.org/ontology/bill-of-characteristics/1.0/")
QIF = Namespace("https://depo.example.org/ontology/qif/3.0/")
AP242 = Namespace("https://depo.example.org/ontology/ap242/")


def test_bill_of_characteristics_ontology_and_qif_ap242_crosswalk_are_valid_rdf():
    graph = Graph()
    graph.parse(ROOT / "bill_of_characteristics.ttl", format="turtle")
    graph.parse(ROOT / "qif_ap242_boc_alignment.ttl", format="turtle")
    assert (BOC.BillOfCharacteristics, RDF.type, URIRef("http://www.w3.org/2002/07/owl#Class")) in graph
    assert (QIF.CharacteristicNominal, RDFS.subClassOf, BOC.NominalCharacteristic) in graph
    assert (AP242.GeometricDimension, RDFS.subClassOf, BOC.DimensionalCharacteristic) in graph
    assert (AP242.GeometricTolerance, RDFS.subClassOf, BOC.TolerancedCharacteristic) in graph


def test_qif_and_ap242_instances_receive_bill_of_characteristics_types():
    qif = qif_to_ceim_batch(b'''<QIFDocument xmlns="http://qifstandards.org/xsd/qif3"><Product><Part id="P-1"><CharacteristicNominalIds><Id>C-1</Id></CharacteristicNominalIds></Part></Product><Characteristics><CharacteristicNominals><LengthCharacteristicNominal id="C-1" /></CharacteristicNominals></Characteristics></QIFDocument>''')
    qif_graph = contract.to_rdf(entities=qif["entities"], relationships=qif["relationships"])
    assert any(qif_graph.triples((None, RDF.type, BOC.NominalCharacteristic)))

    ap242 = ap242_to_ceim_batch(AP242_PART21, filename="pump.stp")
    ap242_graph = contract.to_rdf(entities=ap242["entities"], relationships=ap242["relationships"])
    assert any(ap242_graph.triples((None, RDF.type, BOC.DimensionalCharacteristic)))
    assert any(ap242_graph.triples((None, RDF.type, BOC.TolerancedCharacteristic)))
    assert any(entity["properties"].get("nominal_value") is not None for entity in ap242["entities"] if entity["provenance"]["source_type"] == "dimension")


def test_qif_characteristic_values_are_preserved_for_boc_mapping():
    qif = qif_to_ceim_batch(b'''<QIFDocument xmlns="http://qifstandards.org/xsd/qif3"><Characteristics><CharacteristicNominals><LengthCharacteristicNominal id="C-1"><NominalValue>12.5</NominalValue><LowerLimit>12.4</LowerLimit><UpperLimit>12.6</UpperLimit><Unit>mm</Unit></LengthCharacteristicNominal></CharacteristicNominals></Characteristics></QIFDocument>''')
    characteristic = next(entity for entity in qif["entities"] if entity["id"] == "qif:C-1")
    assert characteristic["properties"] == {"external_id": "C-1", "name": "LengthCharacteristicNominal", "source_kind": "LengthCharacteristicNominal", "nominal_value": "12.5", "lower_limit": "12.4", "upper_limit": "12.6", "unit": "mm"}
