"""Declarative engineering-standard profiles for generic multi-XSD ingestion."""
from __future__ import annotations

from pathlib import Path


STANDARDS = {
    "qif-3": {"name": "QIF 3.0", "prefix": "qif", "tokens": ("qif",), "reference_root": "docs/xsd"},
    "ap242": {
        "name": "STEP AP242",
        "prefix": "ap242",
        "tokens": ("ap242", "step"),
        "reference_root": "",
        "ontology_sources": ("AP242 Business Object Model XSD", "AP242 Domain Model XSD"),
        "instance_sources": ("STEP Part 21 (.stp/.step)", "STEP Part 28 (.stpx)"),
        "schema_support": ("EXPRESS (.exp)",),
    },
    "ap239": {"name": "STEP AP239 / PLCS", "prefix": "ap239", "tokens": ("ap239", "plcs"), "reference_root": ""},
    "ap243": {"name": "STEP AP243", "prefix": "ap243", "tokens": ("ap243",), "reference_root": ""},
    "plmxml": {"name": "PLMXML", "prefix": "plmxml", "tokens": ("plmxml",), "reference_root": ""},
    "b2mml": {"name": "B2MML", "prefix": "b2mml", "tokens": ("b2mml", "isa95"), "reference_root": ""},
    "reqif": {"name": "ReqIF", "prefix": "reqif", "tokens": ("reqif",), "reference_root": ""},
    "xmi": {"name": "XMI / SysML", "prefix": "xmi", "tokens": ("xmi", "sysml", "uml"), "reference_root": ""},
    "generic-xsd": {"name": "Generic XSD Schema Set", "prefix": "schema", "tokens": (), "reference_root": ""},
}


def get_standard(standard_id: str) -> dict:
    try:
        return {"id": standard_id, **STANDARDS[standard_id]}
    except KeyError as exc:
        raise ValueError(f"Unknown standard profile: {standard_id}") from exc


def detect_standard(filenames: list[str]) -> str:
    joined = " ".join(Path(name).name.lower() for name in filenames)
    for identifier, profile in STANDARDS.items():
        if identifier != "generic-xsd" and any(token in joined for token in profile["tokens"]):
            return identifier
    return "generic-xsd"


def public_standards() -> list[dict]:
    return [
        {
            "id": identifier,
            "name": profile["name"],
            "default_prefix": profile["prefix"],
            "reference_available": bool(profile["reference_root"]),
            "ontology_sources": list(profile.get("ontology_sources", ("XSD schema set",))),
            "instance_sources": list(profile.get("instance_sources", ())),
            "schema_support": list(profile.get("schema_support", ())),
        }
        for identifier, profile in STANDARDS.items()
    ]
