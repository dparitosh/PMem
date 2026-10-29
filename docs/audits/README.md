# Current validation and audit status

- [Workflow fixes](workflow-fixes-2026-10-29.md): session invalidation, late-response guards, immediate action locking, durable replay-intent identity and truthful Import guidance. Includes explicit cross-tab and legacy-client limits.

- [All workflows review](all-workflows-review-2026-10-29.md): ten Import types, six agent workflows, job/product/recovery boundaries; 123 existing UI and 118 backend passes, plus two expected-failure probes confirming unfixed session/replay defects. No production workflow changes made during review.

- [Central Change Control visibility](change-control-visibility-2026-10-29.md): OSLC-backed read-only evidence view, source coverage, explicit authorization/execution/delivery states and live PostgreSQL acceptance. Central CR/CO write enforcement remains a separate phase.

- [Lineage and projection fixes](lineage-projection-fixes-2026-10-29.md): owner-resolved lineage, reference-aware retention, catalog description preservation, indexed RDF projection and scope-checked graph loading. Includes a measured AP242 comparison and qualification limits.

- [Data lineage, catalog and graph projections](lineage-catalog-projections-2026-10-29.md): live inventory, isolated lineage/retention reproductions, 62 backend passes with 3 disclosed harness failures, and 12 catalog UI passes. Identifies remaining reference-validation, retention and catalog-description gaps; production code was not changed by this audit.

- [Ontology release versions](../ONTOLOGY_RELEASES.md): immutable family/version/predecessor records, declared change classification, concurrency control and artifact checks before publication. Declaration does not prove compatibility or authorize publication.

- [Local recovery qualification — 29 October](recovery-qualification-2026-10-29.md): PostgreSQL restored into an isolated cluster; all 10 tables and 384 rows matched the exported snapshot. Coordinated artifact/graph recovery and customer acceptance remain pending.

- [Governed learning verification](governed-learning-2026-10-28.md): 442 backend and 75 frontend tests; explicit scope and remaining qualification.

- [Governed mapping learning](../GOVERNED_LEARNING.md): receipt-bound human outcomes, explicit lesson review, revision-scoped advisory hints and revocation. Model training and automatic policy promotion remain unsupported.

- [L0–L4 remediation and database ownership](l0-l4-remediation-2026-10-28.md): durable semantic holds, exact-class checks, selected-record context and release completeness.

Updated 2026-10-28. Current workspace branch: `codex/windows-setup-audit-fixes`. The working tree contains uncommitted fixes; the local installed application has been updated with backups. Customer-network and live-model qualification remain incomplete. This index is not a release certificate.

## Latest verification

- [L0–L4 execution, autonomy and memory audit](l0-l4-layer-review-2026-10-28.md): fresh cross-layer tests and live read checks; confirms selected-record context gaps, retains the two publication findings, and records release-preflight/test failures and disabled memory configuration.

- [Governor / Steward boundary review](governor-steward-boundary-review-2026-10-28.md): follow-up execution found a truncated-target conflict miss and an established hold lost during an evidence outage. These qualify the earlier remediation claims and remain unresolved in this review.

- [Semantic decision loop remediation](semantic-decision-loop-fixes-2026-10-28.md): fixes the post-OWL-DL integration findings and connects current semantic evidence to merging, linking, Recommendations, Companion, Data Products and Data Flow. Includes live database/index verification and remaining qualification limits.

- [Agents, APIs and Companion after OWL-DL integration](owl-dl-agent-integration-review-2026-10-28.md): actual reasoner/API checks plus adversarial controller reproductions. Identifies unresolved semantic-completion, scope, context and evidence-budget gaps; it is not a release approval.

- [Embedded semantic foundation and OWL-DL operation](../EMBEDDED_SEMANTIC_FOUNDATION.md): the later implementation adds versioned offline IDO/DEPO resources, actual bounded HermiT execution and existing-agent tools. This supersedes earlier statements that the adapter was unimplemented; it does not close customer-network, live-model or standards-conformance qualification.

- [Listener, routing, broker, registry and semantic review](transport-semantic-review-2026-10-28.md): 48 backend cases, 70 frontend cases, both routing harnesses, and live checks across ten APIs/two configured origins. Includes exact findings, cleanup scope, evidence and the remaining full OWL-DL gap.
- [Prompt audit deliverable reconciliation](prompt-audit-2026-10-28/DELIVERABLE_STATUS.md) and [installed deployment verification](prompt-audit-2026-10-28/DEPLOYMENT_VERIFICATION.md): preserve the earlier audit/remediation evidence and its live-model limits. Later transport changes have their own dated evidence and do not rewrite old run counts.

The following cleanup/LLM-consolidation sections describe the 2026-10-18 review, whose committed baseline was `3892cab` on `codex/ontology-bridge-stability`. Their counts and deployment statements are historical.

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
