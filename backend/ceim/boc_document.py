"""Render a QIF/AP242 Bill of Characteristics comparison as an RDF document.

Terms come from the Bill of Characteristics ontology (ontology/bill_of_characteristics.ttl).
Report-only fields (comparison status, source ids, AP242 bounds) use a separate
namespace so the ontology file is not changed by this document.

The document is an output artifact. It is not published to the graph and does
not register an ontology; those steps stay behind the governed approval flow.
"""
from __future__ import annotations

import hashlib
from .boc_identity import report_digest
from typing import Any

from rdflib import Graph, Literal, Namespace, RDF, RDFS, URIRef
from rdflib.namespace import XSD

BOC = Namespace("https://depo.example.org/ontology/bill-of-characteristics/1.0/")
REPORT = Namespace("https://depo.example.org/boc-report/1.0/")
DOCS = Namespace("https://depo.example.org/boc/")


def _node(prefix: str, *parts: Any) -> URIRef:
    digest = hashlib.sha256("|".join(str(part) for part in parts).encode("utf-8")).hexdigest()[:16]
    return DOCS[f"{prefix}/{digest}"]


def _decimal(graph: Graph, subject: URIRef, predicate: URIRef, value: Any) -> None:
    if value is None or value == "":
        return
    try:
        number = float(value)
    except (TypeError, ValueError):
        return
    graph.add((subject, predicate, Literal(number, datatype=XSD.decimal)))


def _text(graph: Graph, subject: URIRef, predicate: URIRef, value: Any) -> None:
    if value not in (None, ""):
        graph.add((subject, predicate, Literal(str(value))))


def build_boc_graph(report: dict[str, Any]) -> Graph:
    graph = Graph()
    graph.bind("boc", BOC)
    graph.bind("bocr", REPORT)
    qif_name = report.get("qif_filename", "")
    ap_name = report.get("ap242_filename", "")
    document = _node("document", report_digest(report))
    graph.add((document, RDF.type, BOC.BillOfCharacteristics))
    graph.add((document, RDFS.label, Literal(f"Bill of Characteristics: {qif_name} / {ap_name}")))
    _text(graph, document, REPORT.qifSource, qif_name)
    _text(graph, document, REPORT.ap242Source, ap_name)

    def add_characteristic(key: tuple, *, status: str, kinds: tuple[URIRef, ...], **fields: Any) -> URIRef:
        node = _node("characteristic", document, *key)
        graph.add((node, RDF.type, BOC.Characteristic))
        for kind in kinds:
            graph.add((node, RDF.type, kind))
        graph.add((document, BOC.hasCharacteristic, node))
        graph.add((node, REPORT.comparisonStatus, Literal(status)))
        _text(graph, node, REPORT.qifSourceId, fields.get("qif_id"))
        _text(graph, node, REPORT.ap242SourceId, fields.get("ap242_id"))
        _text(graph, node, RDFS.label, fields.get("name"))
        _text(graph, node, REPORT.note, fields.get("note"))
        _decimal(graph, node, BOC.nominalValue, fields.get("nominal"))
        _decimal(graph, node, BOC.lowerLimit, fields.get("qif_lower"))
        _decimal(graph, node, BOC.upperLimit, fields.get("qif_upper"))
        _decimal(graph, node, REPORT.ap242LowerBound, fields.get("ap_lower"))
        _decimal(graph, node, REPORT.ap242UpperBound, fields.get("ap_upper"))
        _text(graph, node, BOC.unit, fields.get("unit"))
        return node

    for item in report.get("matched", []):
        ap, qif = item.get("ap242", {}), item.get("qif", {})
        qif_values, ap_values = item.get("qif_values", {}), item.get("ap242_values", {})
        bounds = ap_values.get("bounds") or {}
        unit_status = item.get("unit_status")
        bounds_status = item.get("bounds_status")
        if bounds_status == "mismatch" or unit_status == "mismatch":
            status = "mismatch"
        elif bounds_status == "match" and unit_status == "match":
            status = "match"
        else:
            status = "nominal_match"
        add_characteristic(
            ("matched", ap.get("id"), qif.get("id")),
            status=status,
            kinds=(BOC.NominalCharacteristic, BOC.DimensionalCharacteristic) + ((BOC.TolerancedCharacteristic,) if bounds else ()),
            qif_id=qif.get("id"), ap242_id=ap.get("id"), name=ap.get("name") or qif.get("name"),
            nominal=item.get("nominal_value"), qif_lower=qif_values.get("lower_limit"),
            qif_upper=qif_values.get("upper_limit"), ap_lower=bounds.get("lower"), ap_upper=bounds.get("upper"),
            unit=qif_values.get("unit") or ap_values.get("unit"),
            note=f"bounds: {bounds_status}; unit: {unit_status}",
        )

    for item in report.get("ambiguous", []):
        ap = item.get("ap242", {})
        candidates = ", ".join(str(c.get("id")) for c in item.get("qif_candidates", []))
        add_characteristic(("ambiguous", ap.get("id")), status="ambiguous",
                           kinds=(BOC.DimensionalCharacteristic,), ap242_id=ap.get("id"), name=ap.get("name"),
                           nominal=item.get("nominal_value"), note=f"QIF candidates: {candidates}")

    for item in report.get("ap242_dimensions_unmatched", []):
        add_characteristic(("ap242-only", item.get("id")), status="ap242_only",
                           kinds=(BOC.DimensionalCharacteristic,), ap242_id=item.get("id"),
                           name=item.get("name"), note=item.get("reason"))

    for item in report.get("qif_characteristics_unmatched", []):
        add_characteristic(("qif-only", item.get("id")), status="qif_only",
                           kinds=(BOC.NominalCharacteristic,), qif_id=item.get("id"), name=item.get("name"),
                           note="no AP242 dimension with the same nominal value")

    for item in report.get("ap242_tolerances_for_review", []):
        add_characteristic(("review", item.get("id")), status="review_required",
                           kinds=(BOC.TolerancedCharacteristic,), ap242_id=item.get("id"), name=item.get("name"),
                           unit=item.get("unit"), note=f"tolerance value {item.get('tolerance_value')}; not paired with QIF")
        node = _node("characteristic", document, "review", item.get("id"))
        _decimal(graph, node, BOC.toleranceValue, item.get("tolerance_value"))

    return graph


def serialize_boc(report: dict[str, Any]) -> str:
    return build_boc_graph(report).serialize(format="turtle")
