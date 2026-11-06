# Architecture review — 2026-10-03

> Dated audit record: use [the current audit index](README.md) for latest validation and acceptance status. Findings and test counts below belong to their recorded review; they are not a current release certificate.

## Result and evidence

The current design supports a single customer deployment of ten APIs, two durable workers, PostgreSQL control-plane metadata, content-addressed artifacts and Neo4j projections. Local HTTP/token and gateway routing are valid deployment profiles; optional Spark is an execution capability. Recent definition authorization/atomic insertion and authenticated startup fixes are present in commit 85e3eaa.

Full Code Network generation could not run: networkx is absent and no cached report exists. Instead, the audit reused Code Network's actual file discovery and Python import-resolution helpers through dependency-free AST extraction. The trace covered 618 discovered source files, 458 parsed Python files and 881 resolved Python import edges; 41 files directly depend on backend/mesh_store.py. The trace artifact is data/code_audit/architecture_dependency_trace.json (generated/ignored). This is not a PageRank/community or complete dynamic-call report.

## Actionable architectural findings

| Priority | Finding and code trace | Impact and recommended change |
|---|---|---|
| P2 | Worker lease heartbeat failure only sets heartbeat_stop; execute_claimed_job continues handler.execute and creates artifacts before terminal transition ownership is checked. worker.py → router.py:execute_claimed_job → runner.py/run_records.py. | Terminal registry transitions are fenced, which protects run-state completion. Expired workers can still perform wasted/duplicate handler work and retained-artifact writes. Propagate a lease-loss cancellation signal through handlers and check attempt/lease ownership at persistence boundaries. Do not claim exactly-once execution. |
| P2 | Pipeline /readyz checks PostgreSQL but does not include active worker availability. Windows startup verifies worker PID survival, not durable heartbeat. app.py → service_runtime.py; start-depo-services.ps1. | API may be ready while queued jobs have no available executor. Expose execution readiness separately from API readiness and check current worker heartbeats during installation acceptance. Keep HTTP reads available during worker outages. |
| P2 | Data-product outbox loads store.all() before applying [:limit]. router.py:reconcile_pending → mesh_store.py:all. | The limit bounds network attempts, not PostgreSQL reads or Python memory. At scale every poll reads the full namespace. Query due pending records with ordering and a database limit; use per-record claim/version guards for parallel reconcilers. Catalog idempotence still matters. |
| P2 | Code Network includes generated frontend/dist JavaScript (27 files in this checkout) and omits .mjs, .ps1 and .sql. tools/code_graph_audit.py:EXCLUDED/SOURCE_SUFFIXES. | Old bundles distort recommendations while buildReceipt.mjs and deployment/schema effects are omitted. Exclude build outputs, include source module suffixes, and add explicit script/SQL/config dependency edges. |
| P2 architecture constraint | 41 direct users share one generic registry implementation and the same configured PostgreSQL schema. backend/mesh_store.py and postgres_schema.py. | Service processes are separated, but persistence failure/change impact is broad. Publish namespace ownership/contracts, add scoped repository methods and migration compatibility tests, then introduce per-service grants where justified. A DB-per-service rewrite is not required for the current single-customer topology. |
| P2 acceptance gap | Live browser/APIM, worker failover, concurrent PostgreSQL creation, restore/rollback and actual customer acceptance are not exercised by offline checks. | Structured evidence validation prevents malformed acceptance files; it does not run or attest the workflows. Execute the drills on the intended deployment before customer certification. |
| P3 coupling | Pipeline worker imports HTTP router for runner and execute_claimed_job; router imports app inside scheduler health. worker.py → router.py → app.py. | Worker dependency surface includes HTTP adapters and supervisor wiring. Move execution orchestration into a service module used by router and worker; leave API serialization in router. |

No new P1 finding is confirmed by this architectural review. Severity must not be inferred from centrality or an arbitrary target count. Lease-loss side effects need runtime characterization before stronger severity claims.

## Existing safeguards and limits

- Job creation is now credential protected with server actor ownership and atomic conflict handling.
- Run terminal transitions use attempt/worker/live-lease guards; durable replay retains input artifacts.
- Graph publication uses durable receipts for timeout reconciliation; it is separated from worker transformation.
- Data-product catalog registration uses a durable outbox, but its polling query needs bounds.
- Shared browser read keys identify a deployment principal, not individual people. Agent session ownership acknowledges that constraint. A multi-user/multi-tenant deployment needs an explicit identity/isolation design; no such isolation certification is implied here.
- Shared artifact paths work on one VM or a genuinely shared durable mount. Changing Spark master/worker placement does not automatically make local paths shared.
- XSD analytics outputs are schema-design drafts; generic XML-to-warehouse materialization and business fact/dimension/KPI definitions remain pending.

## Implementation order

1. Execution readiness and lease-loss handling, with worker outage/expiry tests.
2. Bounded due-outbox queries and parallel reconciliation guards.
3. Correct Code Network coverage and add deployment/config/schema impacts.
4. Extract worker execution from HTTP router and record registry namespace ownership.
5. Run real browser/database/gateway/restore/rollback acceptance and attach reviewed evidence.

This turn changed audit documentation only. It did not install dependencies, mutate customer configuration, fix the listed issues, or certify a release.


## Implementation follow-up

Implemented cooperative lease-loss persistence fencing, execution readiness checks in Windows startup and deployment diagnostics, bounded due-outbox selection, advisory locking and conditional reconciliation updates, and worker execution extraction from the HTTP router. Code Network now excludes generated bundles and includes `.mjs`, PowerShell, SQL, and JSON references. Registry consumers are inventoried in `docs/architecture/REGISTRY_NAMESPACE_OWNERSHIP.md`.

The shared database remains an architecture constraint; the inventory does not introduce database permission isolation. In-flight external work cannot be cancelled or rolled back by cooperative fencing. Real browser, PostgreSQL, Neo4j, gateway, restore, and rollback acceptance remains outstanding.

Validation: 27 dependency-light regression checks passed, and installation package validation passed for 48 PowerShell scripts. Full service-runtime and frontend build tests were not run because their dependencies are absent. Commit and push status is recorded in Git history.
