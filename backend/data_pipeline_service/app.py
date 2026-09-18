"""Run with: python -m uvicorn backend.data_pipeline_service.app:app --port 8019."""
from contextlib import asynccontextmanager

from backend.depo_platform.odata import ServiceCapability, create_odata_catalog_router
from backend.depo_platform.service_runtime import create_service_app

from .router import router, runner, execute_configured_job
from .speed_router import router as speed_router
from .scheduler import ScheduledJobSupervisor


supervisor = ScheduledJobSupervisor(execute_configured_job)


@asynccontextmanager
async def lifespan():
    supervisor.start()
    yield
    supervisor.stop()
    runner.shutdown()


app = create_service_app(title="DEPO Data Pipeline Service", version="0.1.0", lifespan_hook=lambda: lifespan())
app.include_router(create_odata_catalog_router(
    service_name="DEPODataPipeline",
    capabilities=[
        ServiceCapability("Pipeline health", "/api/v1/pipeline/health", description="Read Spark job readiness"),
        ServiceCapability("Pipeline telemetry", "/api/v1/pipeline/telemetry", description="Read ECharts-ready job telemetry"),
        ServiceCapability("Spark transform", "/api/v1/pipeline/jobs/transform", "POST", "Run a bounded Spark quality transformation and return JSON"),
        ServiceCapability("Data quality assessment", "/api/v1/pipeline/jobs/definitions/{job_id}/{version}/run", "POST", "Run the source-neutral completeness, validity, uniqueness and provenance quality gate"),
        ServiceCapability("Schema analytics data product", "/api/v1/pipeline/jobs/definitions/{job_id}/{version}/run", "POST", "Build a governed schema analytics data-product draft from a retained schema artifact"),
        ServiceCapability("Data-job definitions", "/api/v1/pipeline/jobs/definitions", description="Create and govern versioned Spark data-job definitions"),
        ServiceCapability("Document evidence workflow", "/api/v1/pipeline/workflows/document-evidence/run", "POST", "Run approved document validation, enrichment and CEIM normalization stages"),
        ServiceCapability("Unstructured evidence validation", "/api/v1/pipeline/jobs/definitions/{job_id}/{version}/run", "POST", "Validate content-addressed document evidence before CEIM normalization"),
        ServiceCapability("Distributed RDF statistics", "/api/v1/pipeline/jobs/definitions/{job_id}/{version}/run", "POST", "Run read-only Spark RDF quality statistics over an immutable N-Triples artifact"),
        ServiceCapability("Canonical RDF serialization", "/api/v1/pipeline/jobs/definitions/{job_id}/{version}/run", "POST", "Deduplicate and deterministically serialize an immutable N-Triples artifact with quality evidence"),
        ServiceCapability("Data-job run manifests", "/api/v1/pipeline/jobs/runs", description="Read durable input/output manifests and checkpoints for configured job runs"),
        ServiceCapability("Canonical run publication", "/api/v1/pipeline/jobs/runs/{run_id}/publish", "POST", "Publish an accepted semantic partition through CEIM and advance its checkpoint only after success"),
        ServiceCapability("Speed-path sources", "/api/v1/pipeline/speed/sources", description="Register and approve bounded low-latency event sources"),
        ServiceCapability("Speed-path events", "/api/v1/pipeline/speed/events", "POST", "Capture immutable idempotent semantic event envelopes"),
        ServiceCapability("Speed reconciliation", "/api/v1/pipeline/speed/reconciliations", "POST", "Normalize and validate event records with CEIM without graph writes"),
        ServiceCapability("Speed-path publication", "/api/v1/pipeline/speed/reconciliations/{reconciliation_id}/publish", "POST", "Publish only a validated speed partition through the canonical CEIM API"),
    ],
))
app.include_router(router, prefix="/api/v1")
app.include_router(speed_router, prefix="/api/v1")
