from fastapi.testclient import TestClient

from backend.ceim.ap242_adapter import ap242_to_ceim_batch
from backend.ceim.contract import contract
from backend.ingestion_service.app import app
from backend.ingestion_service.governed_import import profile_for_filename
from backend.ingestion_service.governed_import import governed_import
from backend.tests.test_ap242_mbd import AP242_PART21


def test_governed_instance_profiles_are_extension_bound():
    assert profile_for_filename("design.stp") == "ap242-step-mbd"
    assert profile_for_filename("design.step") == "ap242-step-mbd"
    assert profile_for_filename("design.stpx") == "ap242-step-mbd"
    assert profile_for_filename("requirements.reqif") == "reqif"
    assert profile_for_filename("inspection.qif") == "qif"
    assert profile_for_filename("ebom.plmxml") == "plmxml"


def test_ap242_step_profile_normalizes_to_a_valid_ceim_batch():
    batch = ap242_to_ceim_batch(AP242_PART21, filename="pump.stp")
    assert batch["standard"] == "ap242"
    assert batch["source_summary"]["geometry"] >= 1
    assert batch["source_summary"]["geometric_tolerances"] == 1
    assert contract.validate_projection(entities=batch["entities"], relationships=batch["relationships"])["conforms"] is True


def test_legacy_instance_adapters_receive_the_ceim_version_at_job_submission(monkeypatch):
    class Response:
        status_code = 200
        is_error = False
        text = ""
        def json(self): return {"configured_job": {"job_id": "semantic-source-validation"}, "run_manifest": {"run_id": "run-reqif"}}

    class Client:
        def __init__(self, **_kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *_args): pass
        async def post(self, _url, *, json):
            assert json["standard"] == "reqif"
            assert json["ceim_version"] == contract.version
            assert json["approved_by"] == "governed-ingestion-service"
            return Response()

    monkeypatch.setattr("backend.ingestion_service.governed_import.httpx.AsyncClient", Client)
    import asyncio
    result = asyncio.run(governed_import.run_job(
        filename="requirements.reqif",
        content=b'<REQ-IF xmlns="http://www.omg.org/spec/ReqIF/20110401/reqif.xsd"><CORE-CONTENT><REQ-IF-CONTENT><SPEC-OBJECTS><SPEC-OBJECT IDENTIFIER="R-1" LONG-NAME="Requirement" /></SPEC-OBJECTS></REQ-IF-CONTENT></CORE-CONTENT></REQ-IF>',
        job_id="semantic-source-validation", job_version="1.0.0",
    ))
    assert result["run_manifest"]["run_id"] == "run-reqif"


def test_governed_import_endpoint_delegates_only_to_an_approved_job(monkeypatch):
    async def fake_run_job(**kwargs):
        assert kwargs["job_id"] == "semantic-source-validation"
        assert kwargs["job_version"] == "1.0.0"
        assert kwargs["source_system"] == "Teamcenter"
        return {"status": "completed", "standard": "plmxml", "profile": "plmxml", "run_manifest": {"run_id": "run-1"}}

    monkeypatch.setattr("backend.ingestion_service.router.governed_import.run_job", fake_run_job)
    response = TestClient(app).post(
        "/api/v1/governed-import",
        data={"source_system": "Teamcenter"},
        files={"file": ("ebom.plmxml", b"<PLMXML/>", "application/xml")},
    )
    assert response.status_code == 200
    assert response.json()["run_manifest"]["run_id"] == "run-1"
