"""Compare a CAD-derived AP242 PMI set with a QIF Bill of Characteristics.

Pairing is conservative. A QIF characteristic is paired with an AP242 dimension
only when the nominal values are equal and there is exactly one candidate.
Matched pairs are then checked for tolerance bounds and units. Anything that
cannot be decided from the extracted values is reported, never guessed.

Not compared: feature and face references (STEP ids have no crosswalk to QIF
ids), and unit conversion (a unit mismatch is reported, not converted).
"""
from __future__ import annotations

from typing import Any
from math import isfinite

NOMINAL_TOLERANCE = 1e-6
_TOLERANCE_SOURCES = {
    "GEOMETRIC_TOLERANCE", "ANGULARITY_TOLERANCE", "CIRCULAR_RUNOUT_TOLERANCE",
    "COAXIALITY_TOLERANCE", "CONCENTRICITY_TOLERANCE", "CYLINDRICITY_TOLERANCE",
    "FLATNESS_TOLERANCE", "LINE_PROFILE_TOLERANCE", "PARALLELISM_TOLERANCE",
    "PERPENDICULARITY_TOLERANCE", "POSITION_TOLERANCE", "ROUNDNESS_TOLERANCE",
    "STRAIGHTNESS_TOLERANCE", "SURFACE_PROFILE_TOLERANCE", "SYMMETRY_TOLERANCE",
    "TOTAL_RUNOUT_TOLERANCE",
}


def _number(value: Any) -> float | None:
    try:
        number = float(value)
        return number if isfinite(number) else None
    except (TypeError, ValueError):
        return None


def _unit(value: Any) -> str:
    return str(value or "").strip().lower()


def _brief(entity: dict[str, Any]) -> dict[str, Any]:
    props = entity.get("properties", {})
    return {"id": entity.get("id"), "name": props.get("name") or props.get("external_id"),
            "source_entity": props.get("source_entity") or props.get("source_kind")}


def _close(left: float | None, right: float | None) -> bool:
    return left is not None and right is not None and abs(left - right) <= NOMINAL_TOLERANCE


def _tolerance_check(dimension: dict[str, Any], characteristic: dict[str, Any], nominal: float) -> dict[str, Any]:
    """Compare AP242 tolerance bounds with QIF limits. Bounds are absolute values."""
    ap = dimension.get("properties", {})
    qif = characteristic.get("properties", {})
    ap_unit, qif_unit = _unit(ap.get("unit")), _unit(qif.get("unit"))
    if not ap_unit or not qif_unit:
        unit_status = "not_available"
    else:
        unit_status = "match" if ap_unit == qif_unit else "mismatch"

    lower_offset = _number(ap.get("lower_tolerance"))
    upper_offset = _number(ap.get("upper_tolerance"))
    qif_lower = _number(qif.get("lower_limit"))
    qif_upper = _number(qif.get("upper_limit"))
    if lower_offset is None and upper_offset is None:
        bounds_status = "not_available"
        ap_bounds = None
    else:
        ap_lower = nominal + lower_offset if lower_offset is not None else None
        ap_upper = nominal + upper_offset if upper_offset is not None else None
        ap_bounds = {"lower": ap_lower, "upper": ap_upper}
        if qif_lower is None and qif_upper is None:
            bounds_status = "not_available"
        else:
            checks = []
            if ap_lower is not None and qif_lower is not None:
                checks.append(_close(ap_lower, qif_lower))
            if ap_upper is not None and qif_upper is not None:
                checks.append(_close(ap_upper, qif_upper))
            complete = ((ap_lower is None) == (qif_lower is None)
                        and (ap_upper is None) == (qif_upper is None))
            bounds_status = ("mismatch" if checks and not all(checks)
                             else "match" if checks and complete else "not_available")
    return {
        "bounds_status": bounds_status,
        "unit_status": unit_status,
        "ap242_values": {"unit": ap.get("unit") or None, "bounds": ap_bounds},
        "qif_values": {"unit": qif.get("unit") or None, "lower_limit": qif_lower, "upper_limit": qif_upper},
    }


def compare_boc(ap242_batch: dict[str, Any], qif_batch: dict[str, Any]) -> dict[str, Any]:
    ap_entities = ap242_batch.get("entities", [])
    qif_entities = qif_batch.get("entities", [])

    ap_dimensions = [e for e in ap_entities if e.get("ceim_type") == "Characteristic"
                     and e.get("properties", {}).get("source_entity") == "DIMENSIONAL_SIZE"]
    ap_tolerances = [e for e in ap_entities if e.get("ceim_type") == "Characteristic"
                     and e.get("properties", {}).get("source_entity") in _TOLERANCE_SOURCES]
    qif_characteristics = [e for e in qif_entities if e.get("ceim_type") == "Characteristic"]

    qif_nominals = []
    qif_without_nominal = []
    for entity in qif_characteristics:
        value = _number(entity.get("properties", {}).get("nominal_value"))
        if value is None:
            qif_without_nominal.append(_brief(entity))
        else:
            qif_nominals.append((value, entity))

    used: set[str] = set()
    matched, ambiguous, unmatched_ap = [], [], []
    for dimension in ap_dimensions:
        value = _number(dimension.get("properties", {}).get("nominal_value"))
        if value is None:
            unmatched_ap.append({**_brief(dimension), "reason": "no nominal value in AP242"})
            continue
        candidates = [entity for qv, entity in qif_nominals
                      if abs(qv - value) <= NOMINAL_TOLERANCE and entity.get("id") not in used]
        competing_dimensions = [other for other in ap_dimensions
                                if _close(_number(other.get("properties", {}).get("nominal_value")), value)]
        if len(candidates) == 1 and len(competing_dimensions) == 1:
            qif_entity = candidates[0]
            used.add(qif_entity["id"])
            matched.append({"ap242": _brief(dimension), "qif": _brief(qif_entity), "nominal_value": value,
                            **_tolerance_check(dimension, qif_entity, value)})
        elif candidates:
            ambiguous.append({"ap242": _brief(dimension), "nominal_value": value,
                              "qif_candidates": [_brief(c) for c in candidates]})
        else:
            unmatched_ap.append({**_brief(dimension), "reason": "no QIF characteristic with this nominal value"})

    unmatched_qif = [_brief(entity) for _, entity in qif_nominals if entity.get("id") not in used]
    tolerance_values = [{**_brief(e), "tolerance_value": e.get("properties", {}).get("tolerance_value"),
                         "unit": e.get("properties", {}).get("unit") or None} for e in ap_tolerances]
    bounds_mismatch = sum(1 for m in matched if m["bounds_status"] == "mismatch")
    unit_mismatch = sum(1 for m in matched if m["unit_status"] == "mismatch")
    return {
        "pairing": "nominal value, one-to-one; ambiguous pairs are not matched",
        "matched": matched,
        "ambiguous": ambiguous,
        "ap242_dimensions_unmatched": unmatched_ap,
        "qif_characteristics_unmatched": unmatched_qif + qif_without_nominal,
        "ap242_tolerances_for_review": tolerance_values,
        "summary": {
            "ap242_dimensions": len(ap_dimensions),
            "ap242_tolerances": len(ap_tolerances),
            "qif_characteristics": len(qif_characteristics),
            "matched": len(matched),
            "ambiguous": len(ambiguous),
            "bounds_mismatch": bounds_mismatch,
            "unit_mismatch": unit_mismatch,
        },
        "scope_notes": [
            "Matched pairs are checked for tolerance bounds (nominal plus AP242 offsets against QIF limits) and units.",
            "AP242 geometric tolerance zones are listed with their values for manual review; they are not paired with QIF.",
            "Unit mismatches are reported; no unit conversion is applied.",
            "Feature and face references are not compared; no AP242-to-QIF feature crosswalk is available.",
        ],
    }
