# Workflow fixes — 2026-10-29

## Follow-up audit

Two additional defects were reproduced with failing tests, then corrected:

1. A successful access-verification event was ignored while Data Flow's older load was in flight. Verification now supersedes that load and starts a fresh request generation; the old response cannot replace current evidence.
2. Replay receipt recovery unnecessarily reopened the original input and required the definition to remain present/enabled. Receipt lookup now occurs first, after current execution authorization. It validates the stored run ID, actor and original-run binding, returns retained status without executing work, and still rejects revoked access or mismatched records. Fresh replays retain all input/definition approval checks.

Follow-up validation: 46 backend tests and 20 frontend tests passed. These counts overlap the earlier suites and must not be added as unique coverage. Tests cover original-input expiry, removed definition, current authorization, receipt identity mismatch, reconnect during a pending load, and suppression of the obsolete response. No live duplicate job or publication was submitted.

Follow-up deployment: backed up the two changed runtime files, rebuilt successfully and completed managed startup. All ten endpoint checks passed; the frontend launcher verified registered browser access and ontology reads. Frontend asset: `index-CMV_q16c.js`. The additional interactive browser check could not finish because browser control lost its connection after opening the page; do not count that attempt as a passed UI test. The reconnect race is covered by the executed regression test.

Implemented the confirmed workflow audit fixes:

- Data Flow invalidates obsolete session reads, selected evidence, reviewer/source settings and approved-release choices on credential/session changes. Successful access verification refreshes the page. Late release-list, replay, definition and publication responses cannot restore old-session choices.
- One immediate operation lock serializes UI lifecycle writes, preventing rapid replay/publication/definition submissions before React rerenders.
- Replay and Run now retain a submission identity until a durable run response is confirmed. The backend derives a run identity from actor, original run and submission key under a PostgreSQL advisory lock. A retry returns the retained run without enqueueing or executing it again. Distinct keys permit intentional later replays. This applies in worker and inline modes. Existing clients without a key remain compatible.
- Import aborts obsolete artifact/catalog requests, clears stale source/ontology/review selections and refreshes choices after access verification. Retained job history is preserved; native task polling is invalidated on session replacement and resumed after access verification.
- STEP guidance now sends validated engineering runs to Data Flow for review/publication before linking. Legacy human-readable status labels display “knowledge graph”; retained source/audit records are unchanged.
- Merge, dictionary and taxonomy descriptions distinguish comparison/export reports from governed registration or publication. The Data Flow health badge explicitly names the execution engine instead of implying that the whole workflow is disabled.

Validation: 97 backend tests passed, including replay identity reuse and invalid-input rejection, existing pipeline API, worker retry limits, RDF statistics, import, registry, recovery, bridge, publication, semantic decision and product-authorization boundaries. Fifty-five frontend tests passed across Import routing/polling, Data Flow, workflow presentation and four audit-derived regressions. Four stale AST harness failures were repaired by providing the current bounded-timeout dependency and runner work-context test double; assertions were preserved. The formerly expected-failure probes are now normal passing regression tests.

Local deployment completed with backups and a successful 3443-module production build. All ten API readiness endpoints passed and registered browser access was verified. Live OpenAPI includes the bounded replay key contract. Browser acceptance confirmed corrected STEP guidance, no old “published to Neo4j” history label, retained run counts, explicit execution-engine status and successful revalidation refresh. Frontend asset: `index-C0VXBQwI.js`. Screenshot: `outputs/workflow-fixes-20261029.png`. Live duplicate replay execution was not deliberately submitted; idempotency was tested through isolated API tests in both execution modes. No LLM calls, graph publication, schema reset or credential rotation were performed.

Limits: another tab or cleared browser storage cannot infer a lost replay intent; users must inspect retained runs before resubmitting. Legacy API clients omitting an idempotency key are not deduplicated. Cancelling obsolete browser requests does not revoke completed server writes. A central cross-page CR/CO authority, every provider/model path, and complete customer-network failure acceptance remain separate work. No claim that every timing risk in the audit is eliminated.
