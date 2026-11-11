# Semantic decision loop remediation

Date: 2026-10-28. Follow-up to [the integration review](owl-dl-agent-integration-review-2026-10-28.md). Functional guide and dependency map: [Semantic evidence in engineering work](../SEMANTIC_DECISION_LOOP.md).

## Implemented corrections

| Finding / workflow | Result |
|---|---|
| DL-01 semantic completion | Completion requires a typed disposition for executed or retained semantic observations. The controller renders the semantic conclusion from cited evidence; generated prose cannot replace unknown with success. Wrong-source semantic results are rejected. |
| DL-02 empty scope | Both semantic evidence reads and explicit consistency checks require a selected ontology; missing context yields a missing-input state. |
| DL-03 foundation semantics | Foundation inspection exposes bounded labels, definitions, types and parents, with query/limit controls and reference bundle identity. |
| DL-04 Companion | Explicit semantic questions use current semantic evidence or actual foundation definitions without a live model. Scoped business answers retain their instance evidence and separately include model assessment. No schema property descriptions are substituted for part/PMI or requirement facts. |
| DL-05 repeated parsing | Retained checks reuse the catalog's parsed graph. Deterministic unresolved-import results reuse identical hash-bound evidence as unknown; transient reasoner errors do not become cached success. |
| DL-06 token budget | Large classifications retain a compact typed verdict and provenance envelope, with details explicitly truncated. |
| DL-07 Steward wording | Structural-only checks are distinguished from executed scoped OWL-DL evidence. Read-goal instructions explain the typed completion contract. |
| Retained state | Ontology revision receipts include foundation/worker/adapter dependencies. Resumed goals and DL-checked merge application detect dependency changes. |
| Merging | UI enables exact-union OWL-DL review by default. Synchronous and background review retain union evidence. Conflicts prevent application; unverified DL results hold automatic union approval. Existing explicit manual review remains separate. |
| Linking | Steward reads current target-model evidence; publication rechecks after receipt reconciliation. Whole-model inconsistency or a known unsatisfiable selected target holds new writes. Unrelated unsatisfiable classes do not hold every target. Unknown does not create a new blanket publication gate. |
| Recommendations | Change Impact, Similar Parts and Process Context keep recorded graph evidence and policy assessment, adding scoped model evidence rather than a fabricated consistency-derived score. |
| Data Products | Detail reads show current referenced-model evidence beside immutable package evidence, bounded to two explicit ontology references. Package contents and approved semantic-release requirements are preserved. |
| Data Flow | Run detail reads show current publication-model assessment beside validation and graph delivery receipts; completion is not relabeled publication. |

The shared business assessment requires executed evidence plus artifact/foundation digests before treating a consistency decision as established. Every assessment remains advisory and explicitly does not authorize publication, establish instance conformance or verify a graph projection. Owning-service reads use existing bearer authorization and service-specific gateway headers, a total five-second deadline and a 64 KiB response limit. No write token is substituted for a missing read bearer.

## Live database verification

Read-only inspection of the installed local application's databases succeeded:

- PostgreSQL schema `semantic`: all **13 migrations**, **11 relations**, **53 columns**, **22 constraints** and **12 expected indexes** verified, including registry source lookup index structure and migration checksums.
- Graph schema: **4 required constraints** and **6 required performance indexes** verified against the release definitions and ONLINE state; 75 total indexes were inventoried.
- Retained namespaces observed: one prior DL evidence record, 63 data-job runs and five bridge jobs. An absent data-products namespace in these counts means no rows in that namespace, not a failed query or an invented product.
- New evidence uses existing `(namespace, key)` registry lookups. No SQL migration, graph schema rewrite, reset, deletion or credential rotation was needed.

Machine-readable result: `outputs/semantic-loop-database-check.json`. This check establishes schema/index readiness, not that every graph query or production-size workload has an optimal plan.

## Verification and release limits

The final combined backend run completed with **351 passed** (`outputs/semantic-loop-release.xml`, 115.32 seconds). The earlier focused corrected integration run completed with **203 passed** (`outputs/semantic-loop-qualified.xml`). Frontend validation completed with **58 passed** across the affected workflow/recommendation panels, and the production build succeeded. Test counts from overlapping runs must not be added together. Local installation verification is recorded separately after applying the code.

Tests use real local HermiT for consistency/contradiction/union cases; service and publication scenarios use isolated registries/HTTP or graph doubles. Tests exercise selected-source binding, missing access, stale artifacts/foundation revisions, incomplete results, conflict holds, preserved package/run evidence and publication receipt handling. Live LLMs remain disabled. The historical integration audit and its original failing reproductions remain historical; the four strict expected failures were converted to passing regressions in the current test source.

Not claimed: automatic source alignment, automatically publishing inferred graph assertions, full business-instance OWL-DL conformance, verified requirement satisfaction/interchangeability, minimal inconsistency explanations, or complete customer offline import closures. RDF preparation has byte/triple budgets; the API's RDF parsing/preparation does not yet have the same independent process deadline as the JVM. Customer-scale memory/latency and live-model quality remain qualification work. Approved offline imports are still required for models that reference external ontologies. No unresolved import is silently removed to obtain a success verdict.
