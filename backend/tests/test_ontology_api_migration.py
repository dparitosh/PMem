from fastapi import HTTPException
import pytest

from backend.ontology_service import router as ontology_router


def test_legacy_migration_checks_every_source_before_writing(monkeypatch):
    adopted = []
    monkeypatch.setattr(ontology_router.OntologyUploadManager, "get_ontology", lambda ontology_id: (
        {"status": "success", "metadata": {"ontology_id": ontology_id}} if ontology_id == "available"
        else {"status": "error"}))
    monkeypatch.setattr(ontology_router.OntologyUploadManager, "get_file_for_reuse", lambda ontology_id: (
        b"ontology" if ontology_id == "available" else None))
    monkeypatch.setattr(ontology_router.catalog, "adopt_legacy", lambda **kwargs: adopted.append(kwargs))
    with pytest.raises(HTTPException) as error:
        ontology_router.migrate_legacy_ontologies({"ontology_ids": ["available", "missing"]})
    assert error.value.status_code == 404
    assert adopted == []


def test_legacy_migration_rejects_non_array_ids():
    with pytest.raises(HTTPException) as error:
        ontology_router.migrate_legacy_ontologies({"ontology_ids": "ontology"})
    assert error.value.status_code == 422


@pytest.mark.parametrize("call,payload", [
    ("reason", {"facts": {"unexpected": "object"}}),
    ("quality_gate", {"entities": "not-an-array"}),
    ("evaluate_policies", {"exception_policy_ids": "policy-id"}),
])
def test_ontology_api_rejects_collection_shape_errors(call, payload):
    with pytest.raises(HTTPException) as error:
        getattr(ontology_router, call)(payload)
    assert error.value.status_code == 422
