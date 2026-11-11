from rdflib import Graph, Namespace, RDF

from backend.ceim.boc_conformance import compare_boc
from backend.ceim.boc_document import BOC, REPORT, build_boc_graph, serialize_boc


def _ap_dim(identifier, nominal, *, lower=None, upper=None, unit="mm"):
    props = {"name": f"dim {identifier}", "source_entity": "DIMENSIONAL_SIZE", "nominal_value": nominal, "unit": unit}
    if lower is not None:
        props["lower_tolerance"] = lower
    if upper is not None:
        props["upper_tolerance"] = upper
    return {"id": f"ap:{identifier}", "ceim_type": "Characteristic", "properties": props}


def _qif_char(identifier, nominal, *, lower=None, upper=None, unit="mm"):
    return {"id": f"qif:{identifier}", "ceim_type": "Characteristic",
            "properties": {"name": identifier, "nominal_value": nominal, "unit": unit,
                           "lower_limit": lower, "upper_limit": upper}}


def _graph(report) -> Graph:
    return build_boc_graph({"qif_filename": "p.xml", "ap242_filename": "p.stp", **report})


def test_bounds_match_and_unit_match_is_status_match():
    ap = {"entities": [_ap_dim("1", 25.0, lower=-0.1, upper=0.1)]}
    qif = {"entities": [_qif_char("C1", 25.0, lower=24.9, upper=25.1)]}
    graph = _graph(compare_boc(ap, qif))
    statuses = {str(o) for _, _, o in graph.triples((None, REPORT.comparisonStatus, None))}
    assert statuses == {"match"}


def test_bounds_mismatch_is_reported_as_mismatch():
    ap = {"entities": [_ap_dim("1", 25.0, lower=-0.2, upper=0.1)]}
    qif = {"entities": [_qif_char("C1", 25.0, lower=24.9, upper=25.1)]}
    graph = _graph(compare_boc(ap, qif))
    assert {str(o) for _, _, o in graph.triples((None, REPORT.comparisonStatus, None))} == {"mismatch"}


def test_unit_mismatch_is_reported_without_conversion():
    ap = {"entities": [_ap_dim("1", 25.0, unit="inch")]}
    qif = {"entities": [_qif_char("C1", 25.0, unit="mm")]}
    report = compare_boc(ap, qif)
    assert report["matched"][0]["unit_status"] == "mismatch"
    assert {str(o) for _, _, o in _graph(report).triples((None, REPORT.comparisonStatus, None))} == {"mismatch"}


def test_unmatched_and_ambiguous_items_keep_their_status_and_source_ids():
    ap = {"entities": [_ap_dim("1", 10.0), _ap_dim("2", 25.0)]}
    qif = {"entities": [_qif_char("C1", 25.0), _qif_char("C2", 25.0), _qif_char("C3", 40.0)]}
    graph = _graph(compare_boc(ap, qif))
    statuses = sorted(str(o) for _, _, o in graph.triples((None, REPORT.comparisonStatus, None)))
    assert statuses == ["ambiguous", "ap242_only", "qif_only", "qif_only", "qif_only"]
    assert {str(o) for _, _, o in graph.triples((None, REPORT.ap242SourceId, None))} == {"ap:1", "ap:2"}


def test_document_is_a_bill_of_characteristics_and_round_trips_as_turtle():
    ap = {"entities": [_ap_dim("1", 25.0, lower=-0.1, upper=0.1)]}
    qif = {"entities": [_qif_char("C1", 25.0, lower=24.9, upper=25.1)]}
    text = serialize_boc({"qif_filename": "p.xml", "ap242_filename": "p.stp", **compare_boc(ap, qif)})
    parsed = Graph().parse(data=text, format="turtle")
    documents = list(parsed.subjects(RDF.type, BOC.BillOfCharacteristics))
    assert len(documents) == 1
    characteristics = list(parsed.objects(documents[0], BOC.hasCharacteristic))
    assert len(characteristics) == 1
    assert (characteristics[0], RDF.type, BOC.DimensionalCharacteristic) in parsed
    assert (characteristics[0], RDF.type, BOC.TolerancedCharacteristic) in parsed


def test_aas_submodel_has_identification_semantics_and_typed_properties():
    from backend.ceim.boc_aas import build_boc_submodel
    ap = {"entities": [_ap_dim("1", 25.0, lower=-0.1, upper=0.1)]}
    qif = {"entities": [_qif_char("C1", 25.0, lower=24.9, upper=25.1)]}
    submodel = build_boc_submodel({"qif_filename": "p.xml", "ap242_filename": "p.stp", **compare_boc(ap, qif)})
    assert submodel["modelType"] == "Submodel"
    assert submodel["idShort"] == "BillOfCharacteristics"
    assert submodel["id"].startswith("urn:depo:boc:")
    assert submodel["semanticId"]["keys"][0]["value"] == str(BOC) + "BillOfCharacteristics"
    collections = [e for e in submodel["submodelElements"] if e["modelType"] == "SubmodelElementCollection"]
    assert len(collections) == 1
    props = {p["idShort"]: p for p in collections[0]["value"] if p["modelType"] == "Property"}
    assert props["ComparisonStatus"]["value"] == "match"
    assert props["NominalValue"]["valueType"] == "xs:decimal" and props["NominalValue"]["value"] == "25.0"
    assert props["Unit"]["value"] == "mm"


def test_export_route_returns_each_format():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from backend.qif import router as qif_router
    from backend.tests.test_ap242_mbd import AP242_PART21
    from backend.tests.test_boc_conformance import _length, _qif

    app = FastAPI()
    app.include_router(qif_router.router, prefix="/api/v1")
    app.dependency_overrides[qif_router._qif_identity] = lambda: "test"
    client = TestClient(app)
    files = {"qif_file": ("part.xml", _qif(_length("C-1", "25.0")), "text/xml"),
             "ap242_file": ("part.stp", AP242_PART21, "application/octet-stream")}
    aas = client.post("/api/v1/qif/boc/export", files=files)
    assert aas.status_code == 200 and aas.json()["modelType"] == "Submodel"
    ttl = client.post("/api/v1/qif/boc/export?format=turtle", files=files)
    assert ttl.status_code == 200 and "BillOfCharacteristics" in ttl.text and "text/turtle" in ttl.headers["content-type"]
    js = client.post("/api/v1/qif/boc/export?format=json", files=files)
    assert js.status_code == 200 and js.json()["summary"]["matched"] == 1
    bad = client.post("/api/v1/qif/boc/export?format=xml", files=files)
    assert bad.status_code == 422
