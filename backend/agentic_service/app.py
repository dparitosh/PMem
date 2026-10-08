from backend.depo_platform.service_runtime import create_service_app
from backend.depo_platform.odata import ServiceCapability, create_odata_catalog_router
from .router import router
from .configuration import configuration_status
import asyncio
import logging
from contextlib import asynccontextmanager, suppress
from fastapi.concurrency import run_in_threadpool
from backend.Services.agent_memory_service import AgentMemoryService
from . import sessions


@asynccontextmanager
async def lifecycle():
    async def maintenance():
        while True:
            try:
                await run_in_threadpool(sessions.prune)
                await run_in_threadpool(AgentMemoryService.prune_expired_sessions)
            except Exception:
                logging.getLogger(__name__).exception('Agent session/memory maintenance failed')
            await asyncio.sleep(300)
    task = asyncio.create_task(maintenance())
    try:
        yield
    finally:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task


app = create_service_app(title="DEPO Agentic Control Plane", version="1.0.0", readiness_check=configuration_status, lifespan_hook=lifecycle)
app.include_router(create_odata_catalog_router(service_name="DEPOAgentic", capabilities=[ServiceCapability("Agents", "/api/v1/agents"), ServiceCapability("Tools", "/api/v1/tools"), ServiceCapability("Workflows", "/api/v1/workflows"), ServiceCapability("Knowledge companion", "/api/v1/chat", "POST", "Submit a guided knowledge-companion prompt"), ServiceCapability("Knowledge companion stream", "/api/v1/chat-stream", "POST", "Stream a guided companion response"), ServiceCapability("Code audit", "/api/v1/code-audit", description="Generate a read-only repository dependency graph"), ServiceCapability("Plans", "/api/v1/plans", "POST", "Validate agent tool invocation"), ServiceCapability("Workflow runs", "/api/v1/workflow-runs", "POST", "Execute an ordered workflow and persist traces"), ServiceCapability("Recent workflow executions", "/api/v1/workflow-runs", description="Read authorized workflow history"), ServiceCapability("Verified write receipt", "/api/v1/workflow-runs/{run_id}/reconcile-receipt", "POST", "Verify a downstream receipt without repeating a write"), ServiceCapability("Compensation plan", "/api/v1/workflow-runs/{run_id}/compensation-plan", description="Review reversible operations"), ServiceCapability("Approved compensation", "/api/v1/workflow-runs/{run_id}/compensate", "POST", "Execute approved idempotent compensation"), ServiceCapability("Agent observability", "/api/v1/observability/summary", description="Read bounded durable agent and tool telemetry"), ServiceCapability("Prometheus metrics", "/api/v1/metrics", description="Scrape bounded agent operational metrics"), ServiceCapability("OpenAPI validation", "/api/v1/catalog/validate", description="Detect catalog drift from live OpenAPI contracts")]))
app.include_router(router)
from .bridge_router import router as bridge_router
app.include_router(bridge_router)
