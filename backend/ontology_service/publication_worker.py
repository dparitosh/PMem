"""Lifecycle-managed worker for retained, explicitly approved publications."""
import asyncio
from contextlib import asynccontextmanager, suppress
import logging
from starlette.concurrency import run_in_threadpool
from .publication_jobs import publication_jobs


def execute(job):
    from .router import catalog, _publish_registered_ontology
    return catalog.with_publication_lock(job['ontology_id'], lambda: asyncio.run(
        _publish_registered_ontology(job['ontology_id'], {}, None,
            approved_actor=job['approved_by'], expected_sha256=job['artifact_sha256'])))


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
    task = asyncio.create_task(poll())
    try:
        yield
    finally:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
