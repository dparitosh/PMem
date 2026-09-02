"""Run with: python -m uvicorn backend.ingestion_service.app:app --port 8014."""
from backend.platform.service_runtime import create_service_app
from backend.platform.odata import ServiceCapability, create_odata_catalog_router
from .router import router
from .ontology_browser_router import router as ontology_browser_router
from backend.Services.unified_import_router import ontology_router as compatibility_ontology_router
from backend.Services.unified_import_router import router as compatibility_import_router

app = create_service_app(title="DEPO Ingestion Service", version="1.0.0")
app.include_router(create_odata_catalog_router(
    service_name="DEPOIngestion",
    capabilities=[
        ServiceCapability("Health", "/ingestion/health", description="Ingestion service health"),
        ServiceCapability("Source profiles", "/source-profiles", description="List reusable ingestion profiles"),
        ServiceCapability("Inspect source", "/source-profiles/inspect", "POST", "Inspect a source schema or sample"),
        ServiceCapability("Engineering schema conversion", "/schema-conversions/inspect", "POST", "Convert EXPRESS, STEP, XMI, or XSD to Turtle"),
        ServiceCapability("AP242 inspection", "/ap242/inspect", "POST", "Classify AP242 XSD ontology schemas, EXPRESS schemas, or STEP instances"),
        ServiceCapability("AP242 MBD extraction", "/ap242/mbd/extract", "POST", "Extract traceable product, geometry, PMI, and presentation mappings"),
        ServiceCapability("AP242 Part-28 export", "/ap242/mbd/export-part28", "POST", "Losslessly re-export an already supplied AP242 Part-28 XML source"),
        ServiceCapability("Engineering workflow", "/engineering-workflows", "POST", "Convert, govern, register and optionally publish an engineering ontology"),
        ServiceCapability("Execute profile", "/source-profiles/{profile_id}/workflow", "POST", "Run governed profile ingestion"),
        ServiceCapability("Import workflow", "/import/upload", "POST", "Upload and run the existing tracked import workflow"),
        ServiceCapability("Import task", "/import/status/{task_id}", description="Read tracked import workflow status"),
        ServiceCapability("Ontology upload compatibility", "/ontology/upload", "POST", "Upload an ontology artifact through the ingestion boundary"),
    ],
))
app.include_router(router, prefix="/api/v1")
app.include_router(ontology_browser_router, prefix="/api/v1")
# The tracked import and ontology-upload contracts are retained during the SPA
# migration.  They execute in the ingestion process rather than through the
# retired aggregate server, while new engineering workflows use router.py.
app.include_router(compatibility_import_router, prefix="/api/v1")
app.include_router(compatibility_ontology_router, prefix="/api/v1")
