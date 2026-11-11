"""Export a QIF/AP242 Bill of Characteristics as an AAS-style Submodel.

The structure follows the Asset Administration Shell submodel conventions
(idShort, semanticId, SubmodelElementCollection, Property with valueType).
It is a seed document for AAS or twin services. It is not an AASX package and
is not validated against the IDTA metamodel schema.
"""
from __future__ import annotations

import hashlib
from typing import Any

SEMANTIC_BASE = "https://depo.example.org/ontology/bill-of-characteristics/1.0/"
REPORT_BASE = "https://depo.example.org/boc-report/1.0/"


def _semantic(term: str, base: str = SEMANTIC_BASE) -> dict[str, Any]:
    return {"type": "ExternalReference", "keys": [{"type": "GlobalReference", "value": base + term}]}


def _property(id_short: str, value: Any, value_type: str, term: str | None = None, base: str = SEMANTIC_BASE) -> dict[str, Any]:
    element: dict[str, Any] = {"modelType": "Property", "idShort": id_short, "valueType": value_type,
                               "value": "" if value is None else str(value)}
    if term:
        element["semanticId"] = _semantic(term, base)
    return element


def _collection(id_short: str, term: str, children: list[dict[str, Any]]) -> dict[str, Any]:
    return {"modelType": "SubmodelElementCollection", "idShort": id_short,
            "semanticId": _semantic(term), "value": children}


def _characteristic_fields(report_fields: dict[str, Any]) -> list[dict[str, Any]]:
    fields = [
        ("ComparisonStatus", report_fields.get("status"), "xs:string", "comparisonStatus", REPORT_BASE),
        ("QifSourceId", report_fields.get("qif_id"), "xs:string", "qifSourceId", REPORT_BASE),
        ("Ap242SourceId", report_fields.get("ap242_id"), "xs:string", "ap242SourceId", REPORT_BASE),
        ("NominalValue", report_fields.get("nominal"), "xs:decimal", "nominalValue", SEMANTIC_BASE),
        ("LowerLimit", report_fields.get("qif_lower"), "xs:decimal", "lowerLimit", SEMANTIC_BASE),
        ("UpperLimit", report_fields.get("qif_upper"), "xs:decimal", "upperLimit", SEMANTIC_BASE),
        ("Ap242LowerBound", report_fields.get("ap_lower"), "xs:decimal", "ap242LowerBound", REPORT_BASE),
        ("Ap242UpperBound", report_fields.get("ap_upper"), "xs:decimal", "ap242UpperBound", REPORT_BASE),
        ("Unit", report_fields.get("unit"), "xs:string", "unit", SEMANTIC_BASE),
        ("Note", report_fields.get("note"), "xs:string", None, REPORT_BASE),
    ]
    return [_property(id_short, value, value_type, term, base)
            for id_short, value, value_type, term, base in fields if value not in (None, "")]


def _characteristics(report: dict[str, Any]) -> list[tuple[str, str, dict[str, Any]]]:
    """Flatten the comparison report into (kind, label, fields) rows."""
    rows: list[tuple[str, str, dict[str, Any]]] = []
    for item in report.get("matched", []):
        ap, qif = item.get("ap242", {}), item.get("qif", {})
        qv, av = item.get("qif_values", {}), item.get("ap242_values", {})
        bounds = av.get("bounds") or {}
        bounds_status, unit_status = item.get("bounds_status"), item.get("unit_status")
        if bounds_status == "mismatch" or unit_status == "mismatch":
            status = "mismatch"
        elif bounds_status == "match" and unit_status in ("match", "not_available"):
            status = "match"
        else:
            status = "nominal_match"
        rows.append(("matched", ap.get("name") or qif.get("name") or "characteristic", {
            "status": status, "qif_id": qif.get("id"), "ap242_id": ap.get("id"), "nominal": item.get("nominal_value"),
            "qif_lower": qv.get("lower_limit"), "qif_upper": qv.get("upper_limit"),
            "ap_lower": bounds.get("lower"), "ap_upper": bounds.get("upper"),
            "unit": qv.get("unit") or av.get("unit"), "note": f"bounds: {bounds_status}; unit: {unit_status}"}))
    for item in report.get("ambiguous", []):
        candidates = ", ".join(str(c.get("id")) for c in item.get("qif_candidates", []))
        rows.append(("ambiguous", item.get("ap242", {}).get("name") or "ambiguous", {
            "status": "ambiguous", "ap242_id": item.get("ap242", {}).get("id"), "nominal": item.get("nominal_value"),
            "note": f"QIF candidates: {candidates}"}))
    for item in report.get("ap242_dimensions_unmatched", []):
        rows.append(("ap242_only", item.get("name") or "ap242 dimension", {
            "status": "ap242_only", "ap242_id": item.get("id"), "note": item.get("reason")}))
    for item in report.get("qif_characteristics_unmatched", []):
        rows.append(("qif_only", item.get("name") or "qif characteristic", {
            "status": "qif_only", "qif_id": item.get("id"), "note": "no AP242 dimension with the same nominal value"}))
    for item in report.get("ap242_tolerances_for_review", []):
        rows.append(("review_required", item.get("name") or "tolerance", {
            "status": "review_required", "ap242_id": item.get("id"), "unit": item.get("unit"),
            "note": f"tolerance value {item.get('tolerance_value')}; not paired with QIF"}))
    return rows


def build_boc_submodel(report: dict[str, Any]) -> dict[str, Any]:
    qif_name = report.get("qif_filename", "")
    ap_name = report.get("ap242_filename", "")
    digest = hashlib.sha256(f"{qif_name}|{ap_name}".encode("utf-8")).hexdigest()[:24]
    elements = []
    for index, (kind, label, fields) in enumerate(_characteristics(report), start=1):
        children = [_property("Kind", kind, "xs:string"), _property("Label", label, "xs:string")]
        children.extend(_characteristic_fields(fields))
        elements.append(_collection(f"Characteristic_{index:04d}", "Characteristic", children))
    return {
        "modelType": "Submodel",
        "id": f"urn:depo:boc:{digest}",
        "idShort": "BillOfCharacteristics",
        "semanticId": _semantic("BillOfCharacteristics"),
        "kind": "Instance",
        "submodelElements": [
            _property("SourceQifFile", qif_name, "xs:string", "qifSource", REPORT_BASE),
            _property("SourceAp242File", ap_name, "xs:string", "ap242Source", REPORT_BASE),
            _property("CharacteristicCount", len(elements), "xs:integer"),
            *elements,
        ],
        "provenance": {"standard": "QIF 3.0 + STEP AP242 MBD", "scope": "pairwise comparison; no feature-reference or unit conversion",
                       "published": False},
    }
