from pathlib import Path
import sys

SERVICE_ROOT = Path(__file__).resolve().parents[1]
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

from ontology_agentic.tools.requirement_normalization_tools import (
    export_requirements_alignment_ttl,
    normalize_requirement_records,
    requirement_alignment_profile,
)


def test_requirement_normalization_aligns_cross_domain_links(tmp_path) -> None:
    records = [
        {
            "Requirement ID": "REQ-006",
            "Title": "Bearing life expectancy",
            "Text": "Bearing shall meet 20000 hour life under rated load.",
            "Part ID": "SKF_6306-2Z",
            "Function": "Support rotor shaft",
            "Process": "Bearing installation",
            "Verifies": "TEST-006",
        },
        {
            "Title": "REQ-007 vibration limit",
            "Description": "Motor vibration must remain below threshold.",
            "Derived From": "REQ-006",
        },
    ]

    normalized = normalize_requirement_records(records, source_name="customer.xlsx", source_type="excel")

    assert normalized["status"] == "normalized"
    assert normalized["quality"]["requirement_count"] == 2
    assert normalized["requirements"][0]["id"] == "REQ-006"
    relation_types = {rel["type"] for rel in normalized["relationships"]}
    assert {"relatedPart", "relatedFunction", "relatedProcess", "verifies", "derivedFrom"}.issubset(relation_types)
    assert normalized["alignment_profile"]["canonical_requirement"]["same_as_or_subclass_of"]

    output = tmp_path / "requirements-alignment.ttl"
    exported = export_requirements_alignment_ttl(normalized, output)
    ttl = output.read_text(encoding="utf-8")
    assert exported["status"] == "exported"
    assert "oslc_rm" in ttl
    assert "ap242" in ttl
    assert "relatedPart" in ttl
    assert "REQ-006" in ttl


def test_requirement_normalization_reports_duplicate_ids() -> None:
    normalized = normalize_requirement_records(
        [
            {"id": "REQ-001", "text": "Requirement one"},
            {"id": "REQ-001", "text": "Requirement duplicate"},
        ]
    )
    assert normalized["quality"]["duplicate_ids"] == ["REQ-001"]


def test_requirement_alignment_profile_names_target_domains() -> None:
    profile = requirement_alignment_profile()
    domains = {item["target_domain"] for item in profile["cross_domain_links"]}
    assert "MBSE" in domains
    assert "AP242/PLM" in domains
    assert "PLM/BOP/MBOM" in domains
