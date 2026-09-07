from fastapi.testclient import TestClient
from pathlib import Path

from backend.ceim.reqif_adapter import reqif_to_ceim_batch
from backend.ceim.qif_adapter import qif_to_ceim_batch, validate_qif_instance
from backend.ceim.contract import contract
from backend.ceim_service.app import app
from backend.mesh_store import InMemoryRegistry


def test_ceim_graph_client_accepts_a_service_api_root(monkeypatch):
    """A recovery/service-discovery URL can already include /api/v1."""
    captured = {}

    class Response:
        is_error = False
        def json(self): return {"status": "success"}

    class Client:
        async def __aenter__(self): return self
        async def __aexit__(self, *args): return False
        async def post(self, url, **kwargs):
            captured["url"] = url
            captured["headers"] = kwargs.get("headers")
            return Response()

    monkeypatch.setenv("GRAPH_SERVICE_URL", "http://graph.internal:8013/api/v1")
    monkeypatch.setenv("GRAPH_PUBLICATION_TOKEN", "test-service-token")
    monkeypatch.setattr("backend.ceim_service.router.httpx.AsyncClient", lambda timeout: Client())

    import asyncio
    result = asyncio.run(__import__("backend.ceim_service.router", fromlist=["_publish_to_graph"])._publish_to_graph(turtle="@prefix ex: <urn:test:> .", ontology_id="test", prefix="ex"))

    assert result["status"] == "success"
    assert captured["url"] == "http://graph.internal:8013/api/v1/graph/ontologies/publish"
    assert captured["headers"] == {"Authorization": "Bearer test-service-token"}


def test_ceim_service_exposes_contract_and_normalizes_qif_entity():
    client = TestClient(app)
    assert client.get("/healthz").status_code == 200
    contract = client.get("/api/v1/ceim/contract")
    assert contract.status_code == 200
    assert contract.json()["version"] == "0.1.0"
    result = client.post("/api/v1/ceim/normalize/entity", json={
        "standard": "qif",
        "record": {"source_type": "Part", "source_id": "P-1", "attributes": {"name": "Rotor"}},
    })
    assert result.status_code == 200
    assert result.json()["ceim_type"] == "Part"


def test_ceim_service_validates_and_projects_reqif_batch():
    client = TestClient(app)
    payload = {"standard": "reqif", "entities": [{"source_type": "SPEC-OBJECT", "source_id": "REQ-2", "attributes": {"LONG-NAME": "Speed"}}], "relationships": []}
    assert client.post("/api/v1/ceim/validate/batch", json=payload).json()["conforms"] is True
    projection = client.post("/api/v1/ceim/projection/turtle", json=payload)
    assert projection.status_code == 200
    assert "externalId" in projection.text


def test_ceim_service_requires_approval_and_publishes_only_validated_projection(monkeypatch):
    async def fake_publish(*, turtle, ontology_id, prefix):
        assert "externalId" in turtle
        assert ontology_id == "ceim-qif-demo"
        assert prefix == "ceim"
        return {"status": "success", "resources": 1, "relationships": 0}

    monkeypatch.setattr("backend.ceim_service.router.approval_identity", lambda request, payload, token_env: "reviewer@example.test")
    monkeypatch.setattr("backend.ceim_service.router._publish_to_graph", fake_publish)
    async def fake_release(release):
        return release
    monkeypatch.setattr("backend.ceim_service.router.resolve_approved_release", fake_release)
    response = TestClient(app).post("/api/v1/ceim/publications/graph", json={
        "standard": "qif",
        "ontology_id": "ceim-qif-demo",
        "semantic_release": {"asset_id": "ceim-qif", "version": "0.1.0", "lifecycle_status": "approved"},
        "entities": [{"source_type": "Part", "source_id": "P-1", "attributes": {"name": "Rotor"}}],
        "relationships": [],
    })

    assert response.status_code == 200
    assert response.json()["status"] == "published"
    assert response.json()["semantic_release"]["asset_id"] == "ceim-qif"
    assert response.json()["validation"]["conforms"] is True


def test_ceim_service_surfaces_and_resolves_conflicting_entity_cases(monkeypatch):
    from backend.ceim_service import router
    from backend.ceim.resolution import EntityResolutionRegistry
    registry = EntityResolutionRegistry(); registry.store = InMemoryRegistry()
    monkeypatch.setattr(router, "resolution_registry", registry)
    monkeypatch.setattr("backend.ceim_service.router.approval_identity", lambda *args, **kwargs: "steward")
    client = TestClient(app)
    payload = {"standard": "qif", "entities": [
        {"source_type": "Part", "source_id": "P-1", "attributes": {"name": "Rotor"}},
        {"source_type": "Part", "source_id": "P-1", "attributes": {"name": "Stator"}},
    ], "relationships": []}
    result = client.post("/api/v1/ceim/normalize/batch", json=payload)
    assert result.status_code == 200
    assert result.json()["entity_resolution"]["blocking"] is True
    case_id = result.json()["entity_resolution"]["resolution_case_ids"][0]
    resolved = client.post(f"/api/v1/ceim/entity-resolution/cases/{case_id}/resolve", json={"strategy": "manual", "selected_candidate_index": 0, "rationale": "Use the approved CAD source"})
    assert resolved.status_code == 200
    assert resolved.json()["status"] == "resolved"
    replay = client.post("/api/v1/ceim/normalize/batch", json={**payload, "resolution_case_ids": [case_id]})
    assert replay.status_code == 200
    assert replay.json()["entity_resolution"]["blocking"] is False
    assert len(replay.json()["entities"]) == 1


def test_reqif_adapter_normalizes_a_real_teamcenter_export_when_available():
    source = Path("D:/Githuv_repo/PLMXML/98InductionMotor.reqif")
    if not source.is_file():
        return
    batch = reqif_to_ceim_batch(source.read_bytes())

    assert batch["source_summary"]["requirements"] >= 10
    assert batch["source_summary"]["specifications"] >= 1
    assert any(entity["ceim_type"] == "Document" for entity in batch["entities"])
    assert contract.validate_projection(entities=batch["entities"], relationships=batch["relationships"])["conforms"] is True


def test_reqif_adapter_api_keeps_source_read_only():
    document = b'''<REQ-IF xmlns="http://www.omg.org/spec/ReqIF/20110401/reqif.xsd"><CORE-CONTENT><REQ-IF-CONTENT><SPEC-OBJECTS><SPEC-OBJECT IDENTIFIER="REQ-1" LONG-NAME="Bearing life"/></SPEC-OBJECTS></REQ-IF-CONTENT></CORE-CONTENT></REQ-IF>'''
    response = TestClient(app).post("/api/v1/ceim/adapters/reqif/normalize", files={"file": ("bearing.reqif", document, "application/xml")})

    assert response.status_code == 200
    assert response.json()["entities"][0]["ceim_type"] == "Requirement"
    assert response.json()["source_artifact_id"].startswith("sha256:")
    assert response.json()["representation"] == "normalized-ceim-v1"


def test_qif_adapter_normalizes_representative_instance_and_validates_projection():
    source = Path("data/ceim/fixtures/qif-inspection-instance.xml")
    batch = qif_to_ceim_batch(source.read_bytes())

    assert batch["source_summary"] == {"parts": 1, "inspection_plans": 1, "measurement_results": 1, "features": 0, "characteristics": 0, "datums": 0, "datum_reference_frames": 0, "pmi_annotations": 0, "geometry_bodies": 0, "unresolved_references": 0}
    assert {entity["ceim_type"] for entity in batch["entities"]} == {"Part", "Test", "QualityMeasurement"}
    assert contract.validate_projection(entities=batch["entities"], relationships=batch["relationships"])["conforms"] is True


def test_qif_adapter_api_keeps_source_read_only():
    source = Path("data/ceim/fixtures/qif-inspection-instance.xml")
    response = TestClient(app).post("/api/v1/ceim/adapters/qif/normalize", files={"file": (source.name, source.read_bytes(), "application/xml")})

    assert response.status_code == 200
    assert response.json()["source_summary"]["measurement_results"] == 1
    assert response.json()["mapping_diagnostics"]["status"] == "complete_for_declared_profile"
    assert response.json()["source_artifact_id"].startswith("sha256:")
    assert response.json()["representation"] == "normalized-ceim-v1"


def test_qif_adapter_reports_unmapped_semantic_content_for_steward_review():
    document = b'''<QIFDocument xmlns="http://qifstandards.org/xsd/qif3"><QPId>fd43400a-29bf-4ec6-b96c-e2f846eb6ff6</QPId><Features><FeatureDefinitions /></Features></QIFDocument>'''
    batch = qif_to_ceim_batch(document)

    assert batch["mapping_diagnostics"]["status"] == "review_required"
    assert batch["mapping_diagnostics"]["unmapped_semantic_elements"] == [{"source_type": "FeatureDefinitions", "count": 1}]


def test_qif_adapter_maps_declared_product_semantics_and_geometry_links():
    document = b'''<QIFDocument xmlns="http://qifstandards.org/xsd/qif3"><Product><RootPart><Id>P-1</Id></RootPart><Part id="P-1"><FeatureNominalIds><Id>FN-1</Id></FeatureNominalIds><CharacteristicNominalIds><Id>CN-1</Id></CharacteristicNominalIds><DatumDefinitionIds><Id>D-1</Id></DatumDefinitionIds><DatumReferenceFrameIds><Id>DRF-1</Id></DatumReferenceFrameIds></Part><FolderPart><BodyIds><Id>B-1</Id></BodyIds></FolderPart></Product><Features><FeatureDefinitions><FeatureDefinition id="FD-1" /></FeatureDefinitions><FeatureNominals><PointFeatureNominal id="FN-1"><FeatureDefinitionId>FD-1</FeatureDefinitionId></PointFeatureNominal></FeatureNominals></Features><Characteristics><CharacteristicDefinitions><CharacteristicDefinition id="CD-1" /></CharacteristicDefinitions><CharacteristicNominals><LengthCharacteristicNominal id="CN-1"><CharacteristicDefinitionId>CD-1</CharacteristicDefinitionId></LengthCharacteristicNominal></CharacteristicNominals></Characteristics><DatumDefinitions><DatumDefinition id="D-1" /></DatumDefinitions><DatumReferenceFrames><DatumReferenceFrame id="DRF-1" /></DatumReferenceFrames><PMIDisplaySet><PMIDisplay /></PMIDisplaySet><BodySet><Body id="B-1" /></BodySet></QIFDocument>'''
    batch = qif_to_ceim_batch(document)

    assert batch["mapping_diagnostics"]["status"] == "complete_for_declared_profile"
    assert batch["source_summary"] == {"parts": 1, "inspection_plans": 0, "measurement_results": 0, "features": 2, "characteristics": 2, "datums": 1, "datum_reference_frames": 1, "pmi_annotations": 1, "geometry_bodies": 1, "unresolved_references": 0}
    assert {relationship["relationship"] for relationship in batch["relationships"]} == {"HAS_FEATURE", "HAS_CHARACTERISTIC", "USES_DATUM", "USES_REFERENCE_FRAME", "HAS_GEOMETRY", "REALIZES"}
    assert contract.validate_projection(entities=batch["entities"], relationships=batch["relationships"])["conforms"] is True


def test_qif_xsd_validation_distinguishes_structural_and_mapping_fixtures():
    valid_fixture = Path("data/ceim/fixtures/qif-minimal-valid.xml")
    mapping_fixture = Path("data/ceim/fixtures/qif-inspection-instance.xml")

    assert validate_qif_instance(valid_fixture.read_bytes())["conforms"] is True
    assert validate_qif_instance(mapping_fixture.read_bytes())["conforms"] is False
    response = TestClient(app).post("/api/v1/ceim/adapters/qif/validate", files={"file": (valid_fixture.name, valid_fixture.read_bytes(), "application/xml")})
    assert response.status_code == 200
    assert response.json()["conforms"] is True
