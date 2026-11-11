from backend.ceim.ap242_adapter import ap242_to_ceim_batch
from backend.ceim.boc_conformance import compare_boc
from backend.ceim.qif_adapter import qif_to_ceim_batch
from backend.tests.test_ap242_mbd import AP242_PART21


def _qif(*characteristics: str) -> bytes:
    body = "".join(characteristics)
    return (f'<QIFDocument xmlns="http://qifstandards.org/xsd/qif3"><Product><Part id="P-1"/></Product>'
            f'<Characteristics><CharacteristicNominals>{body}</CharacteristicNominals></Characteristics></QIFDocument>').encode()


def _length(identifier: str, value: str, unit: str = "mm") -> str:
    return (f'<LengthCharacteristicNominal id="{identifier}"><NominalValue>{value}</NominalValue>'
            f'<LowerLimit>{float(value) - 0.1}</LowerLimit><UpperLimit>{float(value) + 0.1}</UpperLimit>'
            f'<Unit>{unit}</Unit></LengthCharacteristicNominal>')


def test_ap242_dimension_matches_qif_nominal_and_reports_tolerances_for_review():
    ap = ap242_to_ceim_batch(AP242_PART21, filename="part.stp")
    qif = qif_to_ceim_batch(_qif(_length("C-1", "25.0")))
    report = compare_boc(ap, qif)
    assert report["summary"]["matched"] == 1
    assert report["matched"][0]["qif"]["id"] == "qif:C-1"
    assert report["matched"][0]["qif_values"]["unit"] == "mm"
    assert report["matched"][0]["bounds_status"] == "not_available"
    assert report["ap242_tolerances_for_review"]
    assert report["ap242_dimensions_unmatched"] == []


def test_nominal_mismatch_is_reported_on_both_sides():
    ap = ap242_to_ceim_batch(AP242_PART21, filename="part.stp")
    qif = qif_to_ceim_batch(_qif(_length("C-1", "30.0")))
    report = compare_boc(ap, qif)
    assert report["matched"] == []
    assert report["ap242_dimensions_unmatched"][0]["reason"].startswith("no QIF characteristic")
    assert [item["id"] for item in report["qif_characteristics_unmatched"]] == ["qif:C-1"]


def test_ambiguous_nominal_values_are_not_paired():
    ap = ap242_to_ceim_batch(AP242_PART21, filename="part.stp")
    qif = qif_to_ceim_batch(_qif(_length("C-1", "25.0"), _length("C-2", "25.0")))
    report = compare_boc(ap, qif)
    assert report["matched"] == []
    assert len(report["ambiguous"]) == 1
    assert len(report["ambiguous"][0]["qif_candidates"]) == 2


def test_qif_characteristic_without_nominal_is_listed_not_matched():
    ap = ap242_to_ceim_batch(AP242_PART21, filename="part.stp")
    qif = qif_to_ceim_batch(_qif('<LengthCharacteristicNominal id="C-9"><Unit>mm</Unit></LengthCharacteristicNominal>'))
    report = compare_boc(ap, qif)
    assert report["matched"] == []
    assert any(item["id"] == "qif:C-9" for item in report["qif_characteristics_unmatched"])


def test_boc_check_route_compares_uploaded_pair():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from backend.qif import router as qif_router

    app = FastAPI()
    app.include_router(qif_router.router, prefix="/api/v1")
    app.dependency_overrides[qif_router._qif_identity] = lambda: "test"
    client = TestClient(app)
    response = client.post("/api/v1/qif/instances/boc-check", files={
        "qif_file": ("part.xml", _qif(_length("C-1", "25.0")), "text/xml"),
        "ap242_file": ("part.stp", AP242_PART21, "application/octet-stream"),
    })
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["summary"]["matched"] == 1
    assert body["qif_filename"] == "part.xml"
    assert "bill_of_characteristics_turtle" in body and "BillOfCharacteristics" in body["bill_of_characteristics_turtle"]

    bad = client.post("/api/v1/qif/instances/boc-check", files={
        "qif_file": ("part.xml", _qif(), "text/xml"),
        "ap242_file": ("part.txt", b"x", "text/plain"),
    })
    assert bad.status_code == 422


def _entity(identifier, **properties):
    return {"id": identifier, "ceim_type": "Characteristic", "properties": properties}


def test_incomplete_bounds_do_not_establish_match():
    ap = _entity("a", source_entity="DIMENSIONAL_SIZE", nominal_value=25,
                 lower_tolerance=-.1, upper_tolerance=.1)
    for limits in ({"lower_limit":24.9}, {"upper_limit":25.1}):
        qif = _entity("q", nominal_value=25, **limits)
        result = compare_boc({"entities":[ap]}, {"entities":[qif]})
        assert result["matched"][0]["bounds_status"] == "not_available"


def test_repeated_ap_nominals_are_ambiguous_in_both_orders():
    dimensions = [_entity(i, source_entity="DIMENSIONAL_SIZE", nominal_value=25) for i in ("a", "b")]
    qif = _entity("q", nominal_value=25)
    for ordered in (dimensions, list(reversed(dimensions))):
        result = compare_boc({"entities":ordered}, {"entities":[qif]})
        assert result["matched"] == []
        assert result["summary"]["ambiguous"] == 2


def test_nonfinite_nominals_are_missing_evidence():
    ap = _entity("a", source_entity="DIMENSIONAL_SIZE", nominal_value=float("nan"))
    result = compare_boc({"entities":[ap]}, {"entities":[]})
    assert result["ap242_dimensions_unmatched"][0]["reason"] == "no nominal value in AP242"


def test_exports_do_not_call_unknown_units_a_full_match():
    from backend.ceim.boc_aas import build_boc_submodel
    from backend.ceim.boc_document import build_boc_graph, REPORT
    from rdflib import Literal
    ap = _entity("a", source_entity="DIMENSIONAL_SIZE", nominal_value=25,
                 lower_tolerance=-.1, upper_tolerance=.1)
    qif = _entity("q", nominal_value=25, lower_limit=24.9, upper_limit=25.1)
    report = compare_boc({"entities":[ap]}, {"entities":[qif]})
    graph = build_boc_graph(report)
    assert list(graph.objects(None, REPORT.comparisonStatus)) == [Literal("nominal_match")]
    def statuses(node):
        if isinstance(node, dict):
            if node.get("idShort") == "ComparisonStatus":
                yield node["value"]
            for value in node.values():
                yield from statuses(value)
        elif isinstance(node, list):
            for value in node:
                yield from statuses(value)
    assert list(statuses(build_boc_submodel(report))) == ["nominal_match"]
