# OWL-DL and run-history timeout verification — 2026-11-02

## Scope and result

Local acceptance only. External LLM services were not started. No customer deployment was changed.

The real HermiT regression suite passed **24 tests in 126.79 seconds** (`test_embedded_owl_dl.py` and `test_owl_dl_agent_integration_review.py`). The engine availability assertion is mandatory, not a skip. Coverage includes embedded foundation consistency, contradictory individuals, unsatisfiable classes, unsupported profiles, unresolved imports, worker timeout/busy behavior and retained agent reasoning evidence.

This does not establish consistency of every retained customer ontology. The retained PLMXML/SysML union references external imports for OSLC Core, Dublin Core Terms, SKOS and SHACL. The current offline reasoner accepts only its bundled foundation imports; there is no external offline import catalog. Those results correctly remain unknown/unresolved_imports. Completing this requires a reviewed, complete local import closure and resolver, followed by checks of the exact retained artifact digest. Removing imports or treating structural validation as OWL-DL proof is not acceptable.

## Timeout reproduction and correction

The original soak recorded three ten-second client read timeouts. Historical database wait traces were not captured, so their exact cause remains unproven.

A separate real PostgreSQL/HTTP experiment reproduced the symptom using relation-lock contention. It used only a disposable schema in `depo_acceptance_test`, with an actual pipeline router and request/QoS middleware on an isolated listener. The live application tables were not locked. The test schema was removed afterward.

Before the correction, three clients timed out near 10.6 seconds; a fourth received HTTP 500 near 10.9 seconds. PostgreSQL showed four sessions waiting on a relation lock. `LockNotAvailable` escaped the run-list handler.

The correction in `backend/data_pipeline_service/router.py` gives run-history reads a five-second operation budget covering pool acquisition, locks and SQL, preserving any shorter parent deadline and request identity. Lock/query cancellation becomes a sanitized HTTP 503 with `Retry-After: 2`. This does not retry a write or replay a job.

After the correction, all four clients received correlated HTTP 503 responses in 5.53–5.55 seconds, with no client timeout or HTTP 500. Database waiters cleared while the test lock was still held. Reads returned HTTP 200 after release. Structured outcome logs retained request IDs, route, status and duration.

Regression verification: **58 tests passed in 5.76 seconds** across run-list budgets, pipeline service, replay idempotency, QoS admission and request-outcome logging. No migration or dependency addition is required.

Evidence retained locally under `outputs`: `owl-dl-acceptance-20261102.log`, `isolated-pipeline-lock-report.json`, `isolated-pipeline-lock-report-after.json` and corresponding isolated server logs.

## Release status

The run-list correction is source-tested. Deploy it through the normal update process and restart the pipeline service before expecting the new budget in a running installation. A busy-history response should prompt a later read, not repeated replay submissions, credential rotation or database reset.

Open: complete external offline imports for full retained-ontology checks; definitive attribution of the original three timeouts. The controlled reproduction establishes a confirmed defect and its correction, not retrospective proof of the original incident.
