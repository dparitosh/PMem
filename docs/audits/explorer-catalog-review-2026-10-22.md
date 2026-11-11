# Explorer, navigation and data workspaces review — 22 October 2026

## Findings and changes

1. Three navigation destinations reused the database icon and two reused the audit icon. All 17 destinations now have distinct registered iX icons. Product, registry and recommendation destinations use network-device, tag-eye and shield-check respectively.
2. Explorer exposed Best Match and Many Matches even though their only distinction was one versus multiple seed nodes. Removed the buttons and their UI state; search returns a bounded matching set and still chooses a focus node automatically. Kept the native contextual API compatibility contract for existing callers.
3. Schema/full Explorer search only searched its loaded node slice. Added an authenticated Graph service explorer-search endpoint that searches the selected Neo4j scope across nodes, relationship types/IDs, property keys, scalar values and list values. Relationship matches retain both endpoints. Search input is parameterized, scope applies to both relationship endpoints, staging/retained activation records are excluded, and credential-like top-level properties and embeddings are excluded. Results return bounded property excerpts (32 fields, 256 characters per value); they are not a complete property export.
4. Searches have a shared 30-second read budget and bounded result sets (default 80, maximum 200 node matches plus 200 relationship matches and their endpoints). Reads use the existing publication/maintenance barrier. On server failure the UI labels its loaded-view fallback as incomplete. Isolated matching nodes are retained rather than removed as graph orphans. Unicode search terms remain usable.
5. Live Neo4j initially contained only two lookup indexes and MetadataAsset.asset_id. The existing idempotent schema provisioner restored and verified four required publication constraints and two scope/identity indexes. No records were deleted. Startup now validates this schema before backend launch whenever Neo4j is configured; missing schema gives the existing Bootstrap repair instruction. Arbitrary key/value substring matching is a bounded scan, not an indexed full-text query. Chunk full-text/vector indexes are not substitutes for universal engineering-object search.
6. Catalog leads with discovery of ingested sources and product versions. Products leads with package readiness/delivery and optional creation journeys. Both offer name/domain/owner/status filtering and row-driven details. Structured ownership, lifecycle, analytics readiness, quality, source/artifact/release counts and pending delivery replace raw JSON as the default detail view. Technical payloads remain collapsed. Pipeline packaging, schema/KPI design, first-product help and Governor review are expandable so empty forms do not dominate the page. Unknown inventory counts are not reported as zero after a failed read.

## Verification

- Backend search, graph/repository and Neo4j schema tests passed (34 tests).
- Frontend navigation, Explorer, universal matching, Catalog/Products, product detail and ingested-inventory tests passed (58 tests, including existing graph normalization/display tests).
- Production build passed; existing bundle-size warnings remain advisory.
- Live transactional Neo4j checks found node names, property keys, string/numeric/boolean/list values, relationship types, relationship keys and values. Staged and credential-like fields were excluded. Temporary fixtures were rolled back; no test graph was retained.
- Source syntax and updater hashes are verified during packaging.

## Deployment boundary

The index/constraint repair is already applied to the configured local Neo4j database. The frontend, new Graph API and startup-source changes require the refreshed existing Governor/Steward update launcher. This session cannot safely restart the tracked installed processes because Windows hides their process identity; no guard is bypassed. Live end-user acceptance of the new screens remains pending that deployment. No product, dimension, KPI, approval or publication is fabricated by these changes.


## Live acceptance follow-up

All 95 deployed files initially matched the update manifest. Refreshed Products/Catalog loaded the new overview and expandable analytics controls. Catalog returned 10 retained import records independently of the empty product and ontology registries. All ten readiness endpoints returned HTTP 200.

Mounted UI testing exposed two missed integration boundaries: search activation changed the shared-result callback identity, causing the ontology selection effect to reset the query; and the new search term was passed as `query` to a method whose first positional argument was also named `query`. The first is fixed by consulting the existing active-search ref in a stable callback. The second is fixed by naming the Cypher parameter `needle`. A mounted-component test reproduced the query reset before the fix and passed afterward; the backend fixture now mirrors the actual method signature. The corrected full native search function successfully executed against configured PostgreSQL/Neo4j and returned the expected empty result, and all 34 backend tests passed again.

The frontend fix and source-table spacing were deployed using a verified staged build, retained hashed assets, unchanged runtime routing and atomic entry replacement. Sources and entry/receipt backups are under logs/frontend-static-update/20261022-145856-b8743142dbab4d46a6c43e828b641151. No service was stopped. The corrected Graph source is staged in the installation but its running Python process must restart to load it. Windows still hides the tracked process executable/command line from this session, so no process guard is bypassed. Final live HTTP search acceptance remains pending that restart.


## Evidence product discoverability

Added always-visible Structural analytics and Pipeline evidence cards to both Catalog and Products. The cards explain their actual artifacts, distinguish creation capability from published availability, show type-specific loaded-version/package counts, and show schema draft availability separately. Unknown/error states are not rendered as zero. Catalog deep links reveal the matching native Products workflow; Products review buttons open and scroll to the existing tools. Added an Evidence type column and updated the first-product guide. Eleven focused frontend tests passed, including counts by product kind, unavailable counts, empty Catalog guidance and deep-link/workflow reveal behavior.


The evidence-card change passed 13 focused frontend tests and the installed production build. It was deployed without restarting services using a staged build and atomic index replacement; backups are under logs/frontend-evidence-update/20261022-164258-d26ab471ba4d40e782ef71b0e6e9bf55. Live Catalog showed both cards with zero published counts and 10 retained source imports. The structural deep link opened its schema tools, and the pipeline review button expanded retained-run tools. No source data or product approval was created by this UI change.


### Evidence workflow subtabs

Replaced side-by-side capability cards with accessible Structural analytics and Pipeline evidence subtabs in Catalog and Products. Preserved counts, descriptions and review links; added keyboard navigation, selected states and labeled panels. Removed the obsolete grid styling. Focused tests: 14 passed across three files. Production build and static deployment passed; no database or backend restart required.


### Data lifecycle cockpit and workflow refactor

Replaced long mixed-purpose pages with a shared lifecycle navigator and accessible workspace tabs. Data Flow separates run monitoring, pipeline definitions, quality, approval settings and agent assistance. Products separates portfolio, creation/review and governance. Catalog defaults to ingested sources, with published products and creation opportunities distinct. Kept existing service calls, retained evidence, governance boundaries and polling; removed the previous always-visible section ordering. Forms remain mounted while hidden so workspace navigation does not discard edits.

Added run-status filtering, explicit empty states and missing-input guidance. Disabled Run now and Schedule when no retained run matches the definition/version; backend guards remain intact. Unavailable operational telemetry no longer displays fabricated zero totals. Fixed selected-run agent context to use job_version and the package-delivery cockpit action to open the portfolio.

Validation: 27 focused tests across five files passed, including workspace keyboard navigation/state retention, no execution on tab change, missing-input guards and catalog source/product separation. Production build and staged atomic static deployment passed. Live navigation checks cover Products creation deep link, Data Flow workspaces and Catalog source discovery. Current installation has no retained pipeline runs or product packages, so this UI verification does not establish successful execution/publication of a new business product.

Final visual review compacted telemetry to a single row at desktop width and corrected the no-run quality indicator to Unknown / not evaluated. Verified all five Data Flow workspace panels, pipeline missing-input actions, Products pipeline deep link, Catalog published-product empty state and the return action to 10 retained sources.


### Recommendations simplification and Semantica boundary

Removed the duplicate page wrapper/title, welcome banner, repeated scenario selectors and obsolete demo prompts. The old prompts all selected Change Impact, including questions about reuse, ontology browsing and SHACL that the name-based endpoint cannot execute. Replaced them with one keyboard-accessible service selector, responsive input form, one readiness strip and one evidence area. Existing graph-prefill events remain supported; unknown service identifiers are ignored. Removed the unused props comparator and inline form/scenario styling.

Fixed boolean and object-form service readiness handling, blocked unavailable analysis actions, bounded requests to 60 seconds, invalidated/cancelled results after changing the result limit, and distinguished empty structured results from a completed recommendation. Normalized both manufacturing related-process response shapes. Exposed method/scope evidence and clarified scores versus calibrated confidence.

Code trace: graph_service/context_router.py -> depo_platform/decision_policy.py -> ontology_service/intelligence.py -> semantica.ContextGraph.enforce_decision_policy. Recommendation generation remains bounded Neo4j traversal / heuristic ranking. No agent planning or memory is invoked by the Analyse button. This UI change introduces no second orchestration path or duplicate agent panel.

Validation: eight focused tests passed, covering readiness recovery, credential invalidation, one-selector layout, keyboard navigation, per-service availability, endpoint routing, result-limit invalidation, stale response cancellation and empty-evidence presentation. Production build and backed-up atomic frontend deployment passed. Live checks cover service selection, input controls and readiness gating. The live graph has no recommendation context, so analysis is correctly disabled; no live result or Semantica assessment was produced. Semantica engine execution with configured customer policies is not established by frontend tests.


### Existing Graph Analyst connected to Recommendations

Supersedes the earlier direct-only Recommendations boundary. Added three read-only recommendation tool bindings to the existing graph-analyst, using the existing durable read-goal queue, model planner, PostgreSQL observations, authorization grants, recovery and cancellation. Added canonical /api/v1 recommendation route aliases so OpenAPI-based agent dispatch and existing direct callers share the same handler and Semantica policy adapter.

The controller pins analysis/object/result-limit/source scope and requires a cited, completed, untruncated selected-tool observation with a recognized policy assessment before goal completion. Trusted result metadata binds the conclusion to that observation. Missing policy configuration, unavailable assessment and blocking findings remain explicit. The browser renders only the cited evidence matching its current selection. No new agent or execution engine was added.

Recommendations defaults to agent investigation; direct graph analysis remains an explicit method. Reused ReadGoalPanel in compact form and retained the existing page task history; removed the duplicate generic agent panel from Recommendations task guidance. The backend advertises an evidence-contract version; the UI refuses to submit to a legacy controller. Credential changes clear the visible agent result.

Validation: 39 backend controller/routes/binding tests, four focused Semantica policy/ranking tests and 22 frontend tests passed. Production build and backed-up static deployment passed. Installed backend sources await restart: Windows enumerates process records in the agent session but hides executable/command-line identity for the tracked graph, agent and workflow worker. The existing shutdown guards were retained. Live model execution and customer-policy assessment are not claimed; graph readiness was empty at the last check.


### Windows lifecycle UAC preflight

The attempted restart failed at tracked frontend PID 5068 because CIM supplied blank executable/command-line fields. The current process token was confirmed non-elevated. Previously the frontend guard reported this as a mismatch, and manage-depo.ps1 did not resolve visibility before starting shutdown.

Added preflight in the existing shared process-control helper and manage-depo.ps1. Hidden tracked-process metadata causes one normal Windows UAC elevation request before any stop/start phase. Literal argument quoting plus an encoded command preserves paths, environment selection, profile and skip switches without interpolation. Elevated retries are bounded; cancelled UAC and persistent metadata restrictions fail closed. Frontend diagnostics now identify visibility failure separately. No ownership checks or PID tracking were removed.

Validation: 15 focused Windows deployment tests passed. Mocked cases cover visible unrelated records, successful UAC handoff, cancellation, elevated-command failure, persistent restrictions and retry-loop prevention, argument preservation and retained tracking. Live elevated restart still requires OS approval and subsequent readiness verification.


Live verification: UAC handoff succeeded and the elevated lifecycle command completed the full restart. Backend services, durable workers and frontend readiness passed; PostgreSQL and Neo4j were not stopped. Recommendations now recognizes the evidence-contract capability and no longer shows the pending-backend message. Graph readiness is still empty, so model-driven recommendation execution remains unverified.

The live handoff exposed Windows Start-Process -Wait waiting for service descendants after the lifecycle command exited. Replaced that wait with Process.WaitForExit on the lifecycle process only, retaining exit-code checks. Re-ran all 15 focused Windows tests successfully, including a regression that rejects a tree-wide wait. Installed the correction and released only the verified waiting caller; running PMem services were left intact.
