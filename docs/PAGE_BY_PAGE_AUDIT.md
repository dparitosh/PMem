# Page-by-page audit — 8 October 2026

Scope: all 17 sidebar routes and their primary components, API wiring, asynchronous state and credential handling. This is source review with existing regression/browser evidence. No new live customer browser or service run was performed. Previous complete frontend suite: 42 files, 185 tests passed. Existing all-page Chromium evidence uses mocked service responses at desktop/mobile widths; it does not prove backend integration or current dark-mode rendering.

## Every page

| Page | Reviewed components / flow | Assessment and pending acceptance |
|---|---|---|
| Home | LandingPage, graph metrics and chat | Credential-triggered refresh exists; distinguishes retained records from published projection. Live graph scope/count agreement and Ollama stream completion remain required. |
| Import | DataImportPipeline, QIF workflow, SysML repository | Existing routing and scoped-write tests. Cancellation, upload/job persistence and credential changes during long imports need dedicated end-to-end verification. |
| Data Flow | DataFlowPage, definitions and retained runs | Credential refresh and bounded telemetry covered by tests. Live enabled job execution, retained artifacts and approved quality/business-rule flow pending. |
| Ontology Junction | OntologyMapper, merge, SemanticBridgeJobs | Reviewed proposal/approval and retained status paths. Merge guards now cover explicit contradictions, not inferred equivalence. Live validation, merge and graph publication pending. |
| Data Catalog | DataProductsPage in catalog mode | Shared pagination, duplicate protection and error states. Confirm registration/outbox delivery after publication and correct retained totals in live services. |
| Data Products | DataProductsPage, SchemaProductPublisher | Completed evidence draft and approval boundaries tested. Live publication, receipt, revocation and catalog consistency pending. |
| Metadata Registry | MetadataRegistryPage and registry widgets | Empty governed registry does not fall back to unrelated ontology rows. Governed assets do not explicitly invalidate on credential changes (F4); ontology context updates are a separate state path. |
| Graph Explorer | GraphExplorerPage, GraphHEB | Configured/offline states covered. Missing or unrecognised health status mounts graph view (F2); malformed health should be unavailable. Live traversal, scope and rendering pending. |
| Code Network | CodeAuditPage | Abort on unmount, error and retry backoff exist. Credential change does not clear retained report (F4). No dedicated page regression; mocked navigation only. |
| Modeling | ModelWorkbenchPage | Selection/request generation protects view changes. Credential change does not clear retained dataset (F4). No dedicated page regression; mocked navigation only. |
| ReqIF | RequirementsPage / RequirementsWorkbench | Shares large OntologyMapper implementation. Dedicated ReqIF import/preview/approval/page regression and live traceability validation missing. |
| QIF | QifPage, QifAp242Mapping | Authenticated downloads and task selection regression verified; mapping credentials invalidate evidence. Live schema conversion and graph synchronization pending. |
| Where Used | WhereUsedView | Requests have abort controllers, but credential invalidation is not explicit (F4). Live relationship direction, node scope and capped traversal completeness need verification. |
| Data Quality | QualityPage | Latest 100 runs explicitly described; completion is not quality conformance. Retained evidence survives credential change (F1); background polling also runs while hidden. |
| Recommendations | RecommendationsTab | Input/service changes invalidate old analysis. Readiness is loaded only on mount and credential changes do not invalidate results (F3). No dedicated page regression. |
| Reports | ReportsTab | Telemetry refresh reacts to credentials and skips hidden-page polling. Retained graph/chat export context and live download authorization still need acceptance checks. |
| Admin | Credentials, service integrations, AgentProposalPanel, AgentControlPanel | Targeted component coverage for sessions, queued results, recovery and capabilities. Live registered-session scopes, service readiness and model probes pending. |

## Actionable findings

- F1 — P1: Data Quality retains old run evidence across credential changes/session expiry. Abort outstanding reads, clear rows and timestamps, and reload only under the current credential context. Source: `frontend/src/pages/QualityPage.js` lines 13–30.
- F2 — P2: Graph Explorer defaults absent health status to ready and accepts every status outside a small failure list. Validate the health contract and accept only known ready statuses. Source: `frontend/src/pages/GraphExplorerPage.js` lines 28–38.
- F3 — P2: Recommendations readiness only loads at mount; connecting credentials or restoring dependencies leaves controls stale. Add credential-driven refresh and request cancellation; invalidate old results when credentials change. Source: `frontend/src/Components/RecommendationsTab.js` lines 529–552 and 580–598.
- F4 — P1: Metadata Registry governed assets, Modeling, Code Network and Where Used do not explicitly reset retained local state on credential change. Their API interceptors protect new requests but do not erase previously displayed state. Add shared credential invalidation and late-response protection, with page regressions. This is a credential-context bug even though multi-user support is deferred.
- F5 — P2: Dedicated page regression coverage is absent for Modeling, Code Network, ReqIF, Where Used, Data Quality and Recommendations. Mocked navigation success does not verify interactive task execution, API failures or recovery.

## Release gate

Do not label every page production-ready based on unit or mocked navigation tests. Fix F1–F4 and add focused F5 coverage, then perform a customer-environment rehearsal with registered credentials, PostgreSQL, Neo4j and APIM. Verify failed reads do not appear as successful zero counts, approved writes agree with graph receipts, and restart recovery preserves outcomes. Check both themes, collapsed navigation, desktop/mobile sizing and keyboard interactions in the deployed build. No application code was changed during this audit.


## Follow-up correction and fixes

Tracing the full App/AppShell wiring corrects F1, F3 credential invalidation and F4: `handleServiceAuthChange` already clears shared graph/search/chat state and increments a revision used to remount the page outlet, chat and schema provider. The absence of per-page listeners was not sufficient evidence of an active credential-change bug in normal application use. Do not duplicate these listeners across every page. Standalone component mounting must supply its own credential boundary.

The concrete missing boundary was session expiry: AppShell now handles `depo:session-expired` through the same reset callback. Graph Explorer accepts only recognised healthy statuses and defaults missing status to unavailable; its malformed loading text is corrected. Recommendations exposes a readiness retry with cancellable, bounded requests and invalidates late analysis results on unmount. Data Quality skips hidden-page background polling. Added focused shell, graph-health and recommendation readiness regressions.

Remaining: dedicated interactive regressions for Modeling, Code Network, ReqIF and Where Used; live customer API/database/graph verification and visual acceptance. Previous F1/F4 statements above are superseded by this full-application wiring correction.

Recommendation analysis now also checks readiness for keyboard submission, and readiness cannot remain usable during a refresh. Full frontend suite passed: 43 files, 189 tests; final focused tests passed after the readiness guard change. Existing bundle-size warnings remain.


## Ontology Junction and Metadata Registry tab stabilization

Ontology Junction previously nested its navigation inside the successful-data render branch, hiding tabs during loading or errors. The tab bar now stays mounted independently of that branch. Both pages share WorkspaceTabs with selected state, roving tab focus and Arrow/Home/End navigation. Taxonomy no longer starts an empty semantic loader merely because alignment reasoning is absent.

Metadata Registry dictionary reads support the wrapped and direct dictionary payloads. Invalid payloads show a service-contract error instead of an empty table. Regressions cover tabs remaining available during a request and late responses after selection clearing, plus keyboard focus/selection. Targeted suite: 22 tests passed. Live visual and backend verification remains pending.


## Taxonomy and Mapping Vocabulary isolation

Taxonomy browser now receives its own nodes/edges; taxonomy loading no longer overwrites mapping state, and vocabulary loading no longer resets retained taxonomy/reasoning. Mapping errors/loading gate only mapping tabs, so a vocabulary failure cannot hide taxonomy. Dictionary parsing is shared with Metadata Registry and supports direct/wrapped and property-only dictionaries. Taxonomy fallback errors are no longer swallowed as absent data. API helpers forward cancellation and deadlines; obsolete loader requests abort on tab/source changes.

Backend refuses shared-prefix graph fallback for a distinct retained version identity. Explicit prefix browsing retains graph-native support and labels its projection scope. This can reveal previously hidden unavailable version data as HTTP 409; restore or repair that exact artifact rather than substituting another version.

Verification: 66 isolated backend tests and 19 focused frontend tests passed. Actual PostgreSQL/Neo4j projection and browser tab-switch acceptance remain pending.


Inference follow-up: rule/source/limit changes invalidate preview results and abort obsolete requests. Backend requires supported boolean rule flags and integer limits (25–1000); invalid inputs return validation errors instead of silently coercing values. Preview is described as structural-rule review evidence, not a full consistency proof. Live reasoner and customer-data acceptance remain pending.


Rule-validation follow-up: extracted a cancellable validation hook. Editing the expression, changing ontology/view or unmounting invalidates the previous response and clears its result. The helper forwards deadlines and signals; malformed validation payloads show an error. Targeted frontend suite: 21 tests passed. Live rule-engine validation remains pending.
