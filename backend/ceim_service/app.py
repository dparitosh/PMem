"""Run with: python -m uvicorn backend.ceim_service.app:app --port 8018."""
from backend.platform.odata import ServiceCapability, create_odata_catalog_router
from backend.platform.service_runtime import create_service_app

from .router import router


app = create_service_app(title="DEPO CEIM Service", version="0.1.0")
app.include_router(create_odata_catalog_router(
    service_name="DEPOCEIM",
    capabilities=[
        ServiceCapability("CEIM contract", "/api/v1/ceim/contract", description="Read canonical engineering contract metadata"),
        ServiceCapability("CEIM mapping pack", "/api/v1/ceim/mapping-packs/{standard}", description="Read a governed standard mapping"),
        ServiceCapability("Normalize entity", "/api/v1/ceim/normalize/entity", "POST", "Normalize a declared source entity"),
        ServiceCapability("Normalize relationship", "/api/v1/ceim/normalize/relationship", "POST", "Normalize a declared source relationship"),
        ServiceCapability("Normalize batch", "/api/v1/ceim/normalize/batch", "POST", "Normalize a bounded source batch"),
        ServiceCapability("Entity resolution cases", "/api/v1/ceim/entity-resolution/cases", description="Review durable duplicate/conflicting CEIM entity cases"),
        ServiceCapability("Resolve entity case", "/api/v1/ceim/entity-resolution/cases/{case_id}/resolve", "POST", "Record a steward-approved entity resolution strategy"),
        ServiceCapability("ReqIF adapter", "/api/v1/ceim/adapters/reqif/normalize", "POST", "Extract a ReqIF instance into a non-persisted CEIM batch"),
        ServiceCapability("PLMXML adapter", "/api/v1/ceim/adapters/plmxml/normalize", "POST", "Extract a Teamcenter PLMXML instance into a non-persisted CEIM batch"),
        ServiceCapability("QIF adapter", "/api/v1/ceim/adapters/qif/normalize", "POST", "Extract a declared QIF instance into a non-persisted CEIM batch"),
        ServiceCapability("QIF XSD validation", "/api/v1/ceim/adapters/qif/validate", "POST", "Validate a QIF 3.0 instance against the bundled document XSD"),
        ServiceCapability("Validate CEIM batch", "/api/v1/ceim/validate/batch", "POST", "Validate normalized entities and relationships using CEIM SHACL"),
        ServiceCapability("CEIM RDF projection", "/api/v1/ceim/projection/turtle", "POST", "Create RDF Turtle for governed graph publication"),
        ServiceCapability("CEIM graph publication", "/api/v1/ceim/publications/graph", "POST", "Approve, validate, and publish CEIM RDF through the graph service"),
    ],
))
app.include_router(router, prefix="/api/v1")
