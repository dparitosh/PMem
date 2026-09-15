"""Pytest collection policy for backend tests.

Some historical files in this folder are manual live-environment scripts. They
perform HTTP calls, wait for services, or mutate Neo4j at module import time.
Keeping them out of default collection makes `pytest backend/tests` reliable
while preserving the scripts for explicit acceptance runs.
"""

from __future__ import annotations

import os


_MANUAL_LIVE_TESTS = [
    "customer_acceptance_test.py",
    "integration_test.py",
    "test_api_smoke.py",
    "test_e2e_ontology.py",
    "test_end_to_end_integration.py",
    "test_neo4j_connection.py",
    "test_neo4j_diagnostic.py",
    "test_ontology_corrected.py",
    "test_ontology_creation.py",
    "test_ontology_e2e.py",
    "test_ontology_upload.py",
    "tests_comprehensive.py",
]


collect_ignore = (
    []
    if os.getenv("RUN_MANUAL_INTEGRATION_TESTS") == "1"
    else _MANUAL_LIVE_TESTS
)


def pytest_sessionfinish(session, exitstatus):
    """Always release test-created Spark JVMs before the CI Python process exits.

    Spark is optional in DEPO, but a locally initialized JVM can otherwise keep
    pytest alive after its final assertion. This is test infrastructure only;
    production shutdown remains owned by the data-pipeline service lifespan.
    """
    try:
        from backend.data_pipeline_service.runner import runner
        runner.shutdown()
    except Exception:
        # A Spark import/runtime may be intentionally absent from a unit-test
        # environment. Never turn test cleanup into a false failure.
        pass
