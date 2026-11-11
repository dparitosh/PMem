# DEPO test validation report

Date: 24 October 2026. Source reviewed: working tree on `codex/windows-setup-audit-fixes`, baseline HEAD `2f3f8c8e42f4947f2423cf6b4e873ad3741caff2`. Review produced documentation only; no application, service, infrastructure, credential or production-data changes.

## Executed in this review

Command used the installed Python runtime, appended backup site-packages for pytest, disabled plugin autoload and enabled `pytest_asyncio.plugin`. Temporary pytest path: `C:/Users/Admin/Documents/Codex/t/memory-review-24`.

```text
pytest backend/tests/test_agent_memory_regressions.py
       backend/tests/test_companion_page_context.py
       backend/tests/test_read_goal_runner.py
       backend/tests/test_catalog_retention_recovery.py
       -q -p pytest_asyncio.plugin
Result: 42 passed in 3.57s
```

These tests use mocked boundaries or temporary artifacts. They cover identity/hash/configuration regressions, scoped context/projection boundaries, remembered failed reads and bounded goal recovery, and retention intent/recovery. They did not delete customer artifacts or query a live graph for acceptance evidence.

## Evidence limits

No live PostgreSQL or Neo4j migration, publication, restart, service configuration, LLM inference or destructive maintenance was executed. No answer-accuracy percentage, retrieval relevance, latency percentile, token reduction or memory-growth result is claimed. Live identity isolation, index performance, semantic revocation across historical publications and distributed recovery remain unverified.

Earlier frontend regression/build results and local MCP tests are historical baseline evidence recorded in existing audits; they were not rerun or counted among these 42 tests. Existing frontend changes remain uncommitted baseline work.

## Required next validation

1. Context isolation matrix: different principal, same shared key, tenant/project, ontology version and page; revocation during a run.
2. Recovery: worker stop after dispatch/before receipt; duplicate recovery; changed credential/tool/source fingerprints; uncertain write must not replay.
3. Retrieval: AP242–QIF and PLMXML approved fixtures, conflicting/revoked facts, unavailable source, partial/truncated evidence, unsupported question; manually score citation support and abstention.
4. Memory governance: legal hold; staged per-store deletion failure; artifact file and registry agreement; session expiry independent of mandatory audit receipts.
5. Performance: measure p50/p95 retrieval and answer latency, token usage, evidence volume and storage growth using disclosed fixture sizes and concurrency. Define thresholds after baseline collection.
6. UI: concise explanations, sources/revisions, mapping relation distinctions, explicit provider failures, no raw agent-run dump in chat; refresh/resume preserves task identity.

## Audit disposition

Focused regressions passed. The source supports persistent governed orchestration foundations, but not a claim of complete five-layer memory or certified customer release. Proceed to the prioritized implementation plan only after its review and approval, as required by the supplied brief.

## Subsequent approved implementation increment

See [implementation progress](DEPO_IMPLEMENTATION_PROGRESS.md): source fixes and 57 focused tests executed after review approval. The earlier documentation-only statement describes the initial review, not this subsequent increment.
