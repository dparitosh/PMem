# Current validation and audit status

Updated 2026-10-18. Committed baseline: `3892cab` on `codex/ontology-bridge-stability`. This change set adds obsolete-code cleanup, shared LLM execution, and semantic alignment. Deployment to customer environments remains pending. This index distinguishes current cleanup checks from dated evidence; it is not a release certificate.

## Current cleanup

- Removed unreachable document-upload processing while retaining HTTP 410 compatibility responses.
- Retired direct-write ontology and standalone QIF worker entry points with migration guidance.
- Removed the unused duplicate XMI parser and session helper; active XMI ingestion remains covered by regressions.
- Retired estimated enrichment, Neo4j load, and post-load health results. Read-only RDF/SHACL validation is maintained in `backend/Services/ontology_validation_service.py`.
- Preserved meaningful mapping/quality regressions and compatibility routes still used by the UI. Compatibility routing remains hosted by the owning standalone service, rather than the aggregate server.
- Original retired material is preserved locally under the Git-ignored `external/excluded-review/2026-10-17-code-cleanup/` folder and in Git history.

Focused cleanup validation: **55 tests passed** across retirement behavior, real RDF validation, mapping integrity, document jobs, XMI parsing, service inventory, and standalone contract boundaries. These are local tests with isolated/mocked service boundaries. The broad metadata/taxonomy suite did not complete collection within the local 45-second attempt and is not counted as passing. No historical full-suite count below represents a new run of this working tree.

## LLM consolidation

Active agentic inference now uses one bounded LangChain Runnable for Companion summaries, tool proposals, ontology evidence review and capability probes. Prompt pairs use ChatPromptTemplate with literal policy/evidence values. Existing GraphRAG LangChain clients and service-owned authorization, persistence, receipts and MCP controls remain in place. The pinned agentic profiles already contain langchain-core; no new dependencies or package reductions were introduced.

Focused LLM/agent validation: **83 tests passed**, including exact APIM URLs/headers, structured/tool payload preservation, response limits, operation deadlines, split Unicode streams, citation buffering, prompt isolation and asynchronous model initialization. Tests use mocked upstream HTTP, not customer APIM. The previously failing merge/engineering fixtures now import real service implementations and use valid RDF/XML inputs instead of stripped imports and obsolete service doubles.

## Merge validation correction

Real-service regression testing exposed default SHACL checks targeting built-in vocabulary introduced by OWL-RL (for example owl:Thing), which incorrectly held valid merges for missing editorial metadata. Default targetClass rules now target submitted declarations before inference; custom/embedded SHACL targets and inferred OWL conflict checks remain unchanged. Missing labels on submitted classes still block application. Validation: **92 tests passed** (91 in the combined LLM/service regression run, plus the newly added custom-SHACL regression). This includes real subprocess merge preparation/validation, receipt reuse, concurrent preview retention, selective registry writes, authored-label rejection, retained conversion references, and custom-SHACL enforcement. PostgreSQL/HTTP boundaries remain isolated; this is not a full repository or live customer acceptance run.

## Semantic enrichment alignment (2026-10-18)

Shared read-only semantic inventory now aligns catalog statistics and graph kinds for OWL/RDFS classes, property categories, datatypes and explicitly/domain-typed individuals. Catalog statistics are stored in the existing PostgreSQL ontology_catalog JSONB registry with semantic_inventory_version=1; no relational DDL migration is required. The existing analytics-backfill API refreshes older inventories without approval/publication changes. Existing graph projections acquire updated kinds/rdf_types only after governed republication.

Taxonomy includes individual assertions and disconnected blank-node/axiom/rule structures; datatype ranges are distinct from class declarations. Cypher mapping accepts rdfs:Class and constrains RDF type targets to the same ontology. Public projection/search/traversal reads expose rdf_types; staged activation uses the same resource query.

SWRL-style rules retain all supporting fact IDs, accept full RDF type predicates and explicit namespaces, parse quoted separators, and enforce fact/atom/join/time/result limits. API inference runs off the event loop. Inverse-property previews are included in the request schema and UI. This remains a bounded application subset, not a complete SWRL/OWL-DL reasoner. Enrichment does not fabricate labels or axioms, or automatically execute imported RDF rules.

Validation: **78 backend tests passed in the latest combined run (36.05 seconds)**. The 3 UI tests passed in the preceding run; the follow-up changes affect backend parsing, fact conversion and backfill tests. Coverage includes real merge preparation/SHACL validation, an isolated authoritative registry persistence test, catalog analytics, scoped Cypher contracts, publication batching/staging, inverse API request validation, namespaces, quoted literal round trips and bounded SWRL joins. No live PostgreSQL or Neo4j server was contacted; database execution/customer acceptance remains required.

Follow-up verification: rule separators now ignore quoted arrows and reject multiple top-level separators. Rule HTTP APIs preserve zero-valued facts. A focused backfill regression verifies that existing approved records retain approval/provenance, receive the current semantic inventory, and produce no further changes on a second call. The registry is isolated in this test; maintenance-lock acquisition and live database behavior are not certified by it.

## Customer acceptance still required

Verify installation/update and PostgreSQL migration against existing customer data; large Neo4j publication and receipt reconciliation; Semantic Bridge merge and instance linking; real APIM/Ollama generation, streaming and tools; browser sessions and workflows; and shared-storage QIF failover before enabling replicas. Live customer services were unavailable to this local cleanup.

Use [installation](../../INSTALLATION.md) and [customer acceptance](../../infra/deployment/CUSTOMER_RELEASE.md) as operational authorities. See [test evidence guidance](../TESTING_AND_EVIDENCE.md) for provenance and [the document index](../DOCUMENT_INDEX.md) for references.

## Historical status retained below

<details>
<summary>October 9 baseline, findings and reported test counts — historical evidence</summary>

# Current validation and audit status

Updated 2026-10-09. Baseline: `cea9484` on `codex/semantic-bridge-release`. The working tree contains subsequent code and documentation fixes; they are not yet committed, pushed or deployed. This page is the status index. Other audits retain their dated findings and evidence.

## Verified locally

| Check | Latest result | Scope and limitation |
| --- | --- | --- |
| Full frontend Vitest suite | **265 tests passed in 61 files**, none failed or skipped | Current code; component/service mocks, not customer live APIs |
| Focused backend suite | **41 tests passed**, plus 5 passing subtests | Bridge jobs, Admin maintenance and audit regressions; isolated dependencies/mocks |
| Production frontend build | Passed | Local Vite build; large-chunk advisory remains |
| Markdown file-link check | Passed | Relative file targets; fenced code excluded; anchors/remote URLs not certified |
| `git diff --check` | Passed | Whitespace only |

Vitest JSON reports 71 suites because nested suites are counted separately; there are 61 result files. The earlier 261-test run preceded four new UI regressions and is superseded by this 265-test run. Focused runs overlap the full run and must not be added to its count.

The generated machine reports for 2026-10-09 were removed on 2026-10-10 at the user's request. The counts above are historical summaries and cannot be independently reproduced from retained run artifacts. [Testing and evidence guidance](../TESTING_AND_EVIDENCE.md) explains older deliverables and executable test cases.

## Current correction records

- [Recursive folder structure review](folder-structure-review-2026-10-10.md): first-party folder inventory, tracked TTL cache and reference duplicate findings; vendor/runtime boundaries excluded. This does not supersede the dated functional test results above.

- [Admin session handling review](admin-session-handling-review-2026-10-09.md): three remaining P2 request/revalidation/preference gaps; no P1 bypass confirmed in the audited paths.

- [Admin maintenance session correction](admin-maintenance-session-2026-10-09.md): central login no longer loses maintenance authorization; old sessions require reconnection after deployment. The full-suite counts above predate this additional change; its focused authorization/UI checks are recorded separately in the correction report.

- [Service P1 review](p1-audit-2026-10-09.md): receipt validation, reset invalidation, APIM headers, worker startup recovery and ReqIF limits are corrected locally; live concurrency/gateway validation remains.
- [Frontend priority review](frontend-priority-audit-2026-10-09.md): eight items have changes and regression coverage for QIF mutations, run navigation, agent inspection/status, retained-input replay and request lifecycle.
- [XSD/XML analytics](xsd-relational-analytics-audit-2026-10-02.md): structural loading is implemented; live PostgreSQL and specialized schema/business mappings remain pending.
- [Customer release status](customer-release-status.md): working-tree readiness, not a release certificate.

The Quality credential finding applies to standalone mounting as defense in depth. Earlier full-app review established that App/AppShell remounts page state when credentials change. Do not count it as a proven cross-user leak in normal shell use. The frontend review did not establish eight P1s or 50 P1s.

## Acceptance still required

1. Install the selected revision and approved dependencies on the target server; record build/startup evidence.
2. Verify PostgreSQL migrations, XML transaction/rollback, worker outage recovery and cross-process concurrency against isolated data.
3. Verify Neo4j publication, bridge receipts, reset reconciliation and concurrent reset/publication behavior.
4. Verify real APIM authentication and Ollama generation, chat and streaming individually. Nonstreaming chat does not establish streaming or tool calling.
5. Exercise live browser workflows, failure recovery, both themes, keyboard navigation, responsive tables and collapsed navigation.
6. Review customer-specific stored-secret cleanup/rotation and revoked-package download policy. No destructive cleanup or credential rotation was performed here.

Dependency locking exists at `backend/requirements-lock.txt`. Platform compatibility, vulnerability/license review and target-runtime validation remain release work. Multi-user project isolation and complete dimensional warehouse behavior remain outside these fixes.

## Documentation ownership

Use [INSTALLATION.md](../../INSTALLATION.md) for installation and [CUSTOMER_RELEASE.md](../../infra/deployment/CUSTOMER_RELEASE.md) for acceptance. The [document index](../DOCUMENT_INDEX.md) locates architecture references, demo scripts and dated audits. Historical logs/navigation reports remain preserved; mocked services and incomplete revision provenance prevent treating them as current live acceptance.

</details>
