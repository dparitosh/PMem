from pathlib import Path
import pytest

from backend.ceim.contract import contract
from backend.ceim.plmxml_adapter import plmxml_to_ceim_batch
from backend.ceim_service.app import app
from fastapi.testclient import TestClient


FIXTURE = Path("D:/Githuv_repo/PLMXML/EBOM-Export/Motor_EBOM.xml")


def test_induction_motor_fragment_references_are_preserved():
    source = Path("D:/Githuv_repo/PLMXML/003257_InductionMotor.xml")
    if not source.is_file():
        pytest.skip("Customer fixture not installed")
    batch = plmxml_to_ceim_batch(source.read_bytes())
    assert len(batch["entities"]) == 1980
    # Includes parser relationships plus declared ProductView root/product
    # reference fields that the former generic parser did not emit.
    assert len(batch["relationships"]) == 1688
    assert batch["source_summary"]["unmapped_relationships"] == 0
    resources = {entity["id"] for entity in batch["entities"] if entity["provenance"]["source_type"] in {"Terminal", "ConnectionRevision", "GDE"}}
    assert len(resources) == 300
    assert all(edge["relationship"] == "TRACE_TO" for edge in batch["relationships"] if edge["target_id"] in resources)
    ids = {entity["id"] for entity in batch["entities"]}
    assert all(edge["source_id"] in ids and edge["target_id"] in ids for edge in batch["relationships"])
    assert {edge["provenance"]["source_key"] for edge in batch["relationships"]} >= {"part_ref", "parent_ref", "root_refs", "product_ref"}
    assert contract.validate_projection(entities=batch["entities"], relationships=batch["relationships"])["conforms"]


def test_teamcenter_plmxml_normalizes_to_a_valid_ceim_batch():
    if not FIXTURE.is_file():
        pytest.skip("PLMXML fixture not installed")
    batch = plmxml_to_ceim_batch(FIXTURE.read_bytes())
    assert batch["standard"] == "plmxml"
    assert batch["source_summary"]["parts"] > 0
    assert batch["entities"]
    assert batch["relationships"]
    report = contract.validate_projection(entities=batch["entities"], relationships=batch["relationships"])
    assert report["conforms"] is True


def test_teamcenter_plmxml_adapter_is_registered_in_the_openapi_service():
    if not FIXTURE.is_file():
        pytest.skip("PLMXML fixture not installed")
    response = TestClient(app).post(
        "/api/v1/ceim/adapters/plmxml/normalize",
        files={"file": (FIXTURE.name, FIXTURE.read_bytes(), "application/xml")},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["standard"] == "plmxml"
    assert payload["representation"] == "normalized-ceim-v1"
    assert payload["source_artifact_id"].startswith("sha256:")
