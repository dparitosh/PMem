"""Lifecycle-managed worker for retained, explicitly approved publications."""
import asyncio
from contextlib import asynccontextmanager
import logging
from starlette.concurrency import run_in_threadpool
from .publication_jobs import publication_jobs


def execute(job):
    from .router import catalog, _publish_registered_ontology
    from backend.depo_platform.operations import OperationContext, operation_scope, remaining_seconds
    async def run():
        with operation_scope(OperationContext(job['job_id'], job['deadline_at'])):
            async with asyncio.timeout(remaining_seconds(job['deadline_at'])):
                return await _publish_registered_ontology(job['ontology_id'], {}, None,
                    approved_actor=job['approved_by'], expected_sha256=job['artifact_sha256'])
    return catalog.with_publication_lock(job['ontology_id'], lambda: asyncio.run(run()))


def verify(ontology_id):
    from .router import ontology_publication_status
    return asyncio.run(ontology_publication_status(ontology_id, include_job=False))


@asynccontextmanager
async def publication_lifespan():
    async def poll():
        while True:
            try:
                await run_in_threadpool(publication_jobs.run_once, execute, verify)
            except Exception as exc:
                logging.getLogger(__name__).error('Publication worker unavailable error_type=%s', type(exc).__name__)
            await asyncio.sleep(3)
    from backend.depo_platform.metadata_service import enabled
    enabled()  # Validate this service-owned setting before advertising readiness.
    async def metadata_poll():
        while True:
            try:
                from backend.depo_platform.metadata_projection import project_pending
                await run_in_threadpool(project_pending)
            except Exception as exc:
                logging.getLogger(__name__).error('Metadata projection pending error_type=%s',type(exc).__name__)
            await asyncio.sleep(3)
    import os
    capacity = int(os.getenv('ONTOLOGY_PUBLICATION_WORKER_CONCURRENCY', '2'))
    if not 1 <= capacity <= 8:
        raise ValueError('ONTOLOGY_PUBLICATION_WORKER_CONCURRENCY must be between 1 and 8')
    tasks = [asyncio.create_task(poll()) for _ in range(capacity)] + [asyncio.create_task(metadata_poll())]
    try:
        yield
    finally:
        for task in tasks: task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
