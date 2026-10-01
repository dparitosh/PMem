# Frontend page audit — 2026-10-01

## Remediation update

The findings below describe the original audit state. Application fixes now
address F01–F19: scoped QIF write credentials; task/request generation guards;
independent QIF initial loads; commit transport identity; predicate direction;
safe error messages; bounded/coalesced refreshes; partial-evidence warnings;
unknown quality for unavailable evidence; theme tokens; and source-level
Semantic Bridge review coverage. Where Used remains a snapshot search with an
explicit scope warning, rather than a claim of complete graph search.

Validation: full existing suite plus QIF write-key/missing-quality regressions
passed (100 tests); four additional taxonomy-direction tests passed. Vite
production build passed. Dependencies were installed temporarily using pnpm
without modifying the committed npm lockfile; this validates source behavior
but does not certify a fresh npm-ci customer install. Customer browser checks
for gateway identity, live failures and light/dark layout remain required.

Static review of the 13 registered application routes, home page, shared API
clients, and underlying page components. This is an actionable inventory, not a
claim that every possible bug has been found. No live browser/backend exercise
or new dependency installation was performed. Existing uncommitted fixes were
preserved; this review does not change application code.

## Confirmed findings

| ID | Priority | Page / file and line | Trigger and effect | Suggested fix |
| --- | --- | --- | --- | --- |
| F01 | P1 | QIF and Import/QIF — QifPage.js:96; services/apiClient.js:413; app/AppShell.js:154; backend/qif/router.py:22 | Shell instructs users to enter GRAPH_READ_TOKEN. QIF POST routes require ONTOLOGY_APPROVAL_TOKEN, but QIF actions use the generic read header and have no scoped write credential control. With distinct generated keys, start/commit/cancel/retry actions receive 403. | Supply a scoped runtime write credential or authenticated gateway identity to QIF actions; keep global read identity unchanged. |
| F02 | P2 | QIF — QifPage.js:54,90,135 | Poll A, then open B while A's response is pending. refreshTask unconditionally sets task; old A response can restore A. One-second intervals also overlap when requests take longer. | Abort or generation-check requests and use one in-flight poll per selected task. |
| F03 | P2 | QIF — QifPage.js:66,79 | Failure of any catalog/agents/history request discards the combined initial result and shows generic service-unavailable text, including authorization failures. | Load independent sections separately and distinguish authentication from network failure. |
| F04 | P2 | Import — DataImportPipeline.js:1310 | Background commit uses native fetch instead of the authenticated client. It supplies Authorization only when a local approval token exists; configured global/gateway bearer identity is omitted. | Use the shared transport with explicit endpoint credential selection; test token and gateway paths. |
| F05 | P2 | Ontology Junction taxonomy — OntologyMapper.js:37,457,848 | narrower/parentOf are handled with the same child-to-parent direction as broader/subClassOf, reversing their hierarchy. relatedTo is also treated as a parent edge. | Normalize direction by predicate and keep associative relations out of parent/child trees. |
| F06 | P2 | Ontology Junction merge — OntologyMapper.js:2130,2151,1607 | Start preview for A/B, then change source while it runs. Selection effect clears the preview, but the older response restores it. mergePlanReady does not check preview source/target against current selection. | Bind previews to a selection generation and validate their source/target before enabling commit. |
| F07 | P2 | Ontology Junction inference — OntologyMapper.js:2357,2370 | Change ontology while inference is pending. The old result is stored without checking the active ontology. | Bind results to ontology ID and request generation; cancel stale reads. |
| F08 | P2 | Requirements — OntologyMapper.js:60,75 | Change source filter rapidly. Responses may arrive out of order and show old-source requirements under the new filter. | Abort obsolete requests or check monotonically increasing request IDs. |
| F09 | P2 | Registry, Model Workbench, Reports, Requirements, Inference, Merge and Recommendations — MetadataRegistryPage.js:100,200; ModelWorkbenchPage.js:366,494; ReportsTab.js:341,361,386,835,1321; OntologyMapper.js:68,2160,2372; RecommendationsTab.js:539,657 | FastAPI detail may be an object or validation array. These handlers put it into state and JSX renders it directly, producing React's invalid-child error rather than an actionable error message. | Apply the existing apiErrorMessage helper consistently; test 422 arrays and structured service errors. |
| F10 | P2 | Recommendations — RecommendationsTab.js:568 | Start analysis, change service/input while pending. Response is unconditionally adopted; old scenario results can appear beneath new controls. | Freeze request context and only apply the result if it still matches the selected service/input. |
| F11 | P2 | Where Used — WhereUsedView.js:204,240 | Search only uses the retained graph overview, fetched with limit 1200. The duplicated local fallback is identical to primary search; there is no server search or completeness indication for omitted nodes. | Use server search or explicitly label results as limited to the loaded graph and show truncation. |
| F12 | P2 | Where Used — WhereUsedView.js:314,355,395 | A traversal request fails during parent expansion. Inner catch logs and continues; partial ancestors are displayed with autoExpanded=true and no incomplete-result warning. | Track failed branches and display partial coverage with a retry action. |
| F13 | P2 | Data Flow — DataFlowPage.js:118,125,139,65 | Health succeeds while runs/definitions fail. Failed sections are replaced with empty arrays, and QualityOverview reports ok whenever failed-run count is zero. Missing evidence appears as zero failures/healthy quality. | Preserve last good section data, mark it stale/unavailable and use unknown/degraded quality when evidence is absent. |
| F14 | P2 | Graph Explorer — GraphHEB.js:1638 | Selected contextual root load fails. Catch logs only, leaving prior graph without a visible failed-load message for the requested root. | Surface contextual-load error, retain prior graph with a stale-context label, and permit retry. |
| F15 | P3 | Reports — ReportsTab.js:334 | Pipeline telemetry loads only once at mount. Later job results do not update while the report remains open. | Add explicit refresh or bounded polling with last-updated/stale status. |
| F16 | P2 | Code Audit — CodeAuditPage.js:57,75,331 | Manual refresh starts while an automatic poll is pending. load has no in-flight or sequence guard, so an older audit response may overwrite the newer one and loading can clear prematurely. | Abort obsolete reads or serialize/coalesce refresh requests. |
| F17 | P3 | QIF — QifPage.js:8; QifPage.css:1–30 | Fixed white panels and pale backgrounds remain in dark mode. CSS also uses fixed dark text; generic dark overrides selectively change text without consistently changing these surfaces. | Use theme surface/text/border tokens and visually test both schemes. |
| F18 | P2 | Ontology Junction Semantic Bridge — ontology/SemanticBridgeJobs.js:89–98 | Backend now retains alignment_items, unmatched_count, ambiguous_count and unresolved_checks, but UI only displays candidate count/list. Users cannot inspect omitted or ambiguous sources and required semantic checks. | Display coverage totals and source-level statuses/checks alongside candidates. |
| F19 | P3 | Home — LandingPage.js:157,195,212 | Refresh calls can overlap and have no generation guard. Older metrics/ontology responses may overwrite newer snapshots. | Coalesce refreshes or abort/check obsolete requests. |

F09 groups one error-handling defect across several pages rather than counting
each occurrence as a separate bug. F04 concerns requests without a supplied
local approval token; it does not claim the explicitly token-authorized path
always fails. F06 concerns incorrect review context; backend approval and
preview contracts still enforce their own publication boundaries.

## Page coverage

| Route / workspace | Findings / review result |
| --- | --- |
| Home | F19; metrics and ontology failure banners already present. |
| Import | F04; QIF workspace inherits F01–F03/F17. |
| Data Flow / jobs / quality | F13. |
| Ontology Junction taxonomy | F05. |
| Ontology Junction vocabulary | Shared F09 where errors are rendered; no additional independent vocabulary defect confirmed in this pass. |
| Ontology Junction alignment / Semantic Bridge | F18; saved-preview source/ontology identity guards already present. |
| Ontology Junction inference | F07/F09. |
| Ontology Junction merge preview | F06/F09. |
| Metadata Registry / dictionary | F09; list requests are capped at 1000, so complete-inventory pagination still needs customer-scale validation. |
| Graph Explorer / contextual graph | F14. |
| Code Audit | F16. |
| Model Workbench | F09; graph-loading request IDs and cancellation already present. |
| Requirements | F08/F09. |
| QIF | F01–F03/F17. |
| Where Used | F11/F12. |
| Recommendations (quality route) | F10/F09. |
| Reports | F15/F09. |
| Admin | No additional independent breaking defect confirmed; registry/catalog cancellation and structured-error string conversion already present. Visual/service-failure checks remain required. |

## Checks still required

- Run every route in light/dark mode at desktop and narrow widths against the
  customer's configured service topology.
- Exercise distinct read/write keys, token expiry, 403, 422 object/array errors,
  timeout, slow out-of-order responses and partial-service outages.
- Verify gateway and direct-service paths, download authorization, ontology
  switching, long jobs and background publication recovery.
- Existing page-level error boundary is keyed by active page/auth revision in
  App.js:242, so navigation remounts it. An initial concern that page navigation
  would remain trapped in the old boundary was ruled out.
- No finding here claims the application is comprehensively bug-free or that
  static review substitutes for browser acceptance tests.
