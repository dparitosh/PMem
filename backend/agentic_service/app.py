from backend.depo_platform.service_runtime import create_service_app
from backend.depo_platform.odata import ServiceCapability, create_odata_catalog_router
from .router import router
from .configuration import configuration_status
import asyncio
import logging
import os
from contextlib import asynccontextmanager, suppress
from fastapi.concurrency import run_in_threadpool
from backend.Services.agent_memory_service import AgentMemoryService
from . import sessions
from backend.depo_platform.network import bounded_timeout_seconds


@asynccontextmanager
async def lifecycle():
    async def maintenance():
        while True:
            from .router import companion_job_store
            retention = int(bounded_timeout_seconds('AGENT_MEMORY_RETENTION_DAYS', default=30, maximum=3650))
            for cleanup, args in ((sessions.prune, ()),
                                  (companion_job_store.prune_completed, (retention,)),
                                  (AgentMemoryService.prune_expired_sessions, ())):
                try:
                    await run_in_threadpool(cleanup, *args)
                except Exception:
                    logging.getLogger(__name__).exception('Agent maintenance failed: %s', cleanup.__name__)
            await asyncio.sleep(bounded_timeout_seconds('DEPO_AGENT_MAINTENANCE_SECONDS', default=300, maximum=3600))
    task = asyncio.create_task(maintenance())
    try:
        yield
    finally:
        from .router import _active_workflow_tasks
        pending = set(_active_workflow_tasks)
        if pending:
            _, pending = await asyncio.wait(pending, timeout=bounded_timeout_seconds('DEPO_AGENT_SHUTDOWN_SECONDS', default=30, maximum=300))
            for workflow in pending:
                workflow.cancel()
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task


app = create_service_app(title="DEPO Agentic Control Plane", version="1.0.0", readiness_check=configuration_status, lifespan_hook=lifecycle)
app.include_router(create_odata_catalog_router(service_name="DEPOAgentic", capabilities=[ServiceCapability("Agents", "/api/v1/agents"), ServiceCapability("Tools", "/api/v1/tools"), ServiceCapability("Workflows", "/api/v1/workflows"), ServiceCapability("Knowledge companion", "/api/v1/chat", "POST", "Submit a guided knowledge-companion prompt"), ServiceCapability("Knowledge companion stream", "/api/v1/chat-stream", "POST", "Stream a guided companion response"), ServiceCapability("Code audit", "/api/v1/code-audit", description="Generate a read-only repository dependency graph"), ServiceCapability("Plans", "/api/v1/plans", "POST", "Validate agent tool invocation"), ServiceCapability("Workflow runs", "/api/v1/workflow-runs", "POST", "Execute an ordered workflow and persist traces"), ServiceCapability("Recent workflow executions", "/api/v1/workflow-runs", description="Read authorized workflow history"), ServiceCapability("Verified write receipt", "/api/v1/workflow-runs/{run_id}/reconcile-receipt", "POST", "Verify a downstream receipt without repeating a write"), ServiceCapability("Compensation plan", "/api/v1/workflow-runs/{run_id}/compensation-plan", description="Review reversible operations"), ServiceCapability("Approved compensation", "/api/v1/workflow-runs/{run_id}/compensate", "POST", "Execute approved idempotent compensation"), ServiceCapability("Agent observability", "/api/v1/observability/summary", description="Read bounded durable agent and tool telemetry"), ServiceCapability("Prometheus metrics", "/api/v1/metrics", description="Scrape bounded agent operational metrics"), ServiceCapability("OpenAPI validation", "/api/v1/catalog/validate", description="Detect catalog drift from live OpenAPI contracts")]))
app.include_router(router)
from .bridge_router import router as bridge_router
app.include_router(bridge_router)
