# Pages, UX, session state and service handling audit

Date: 30 October 2026. Repository: PMem, branch `codex/windows-setup-audit-fixes`, including current uncommitted application changes. Live app: `http://127.0.0.1:3000`. This is an audit, not a release certification. No production implementation was modified.

## Evidence and coverage

- Executed the complete existing frontend suite with the direct configuration loader: **135 files, 817 tests passed**, duration 330.09 seconds. React act/deprecation warnings remain. The first default-loader attempt failed on environment directory permissions, before application tests.
- Added a temporary diagnostic reproduction, executed it separately, then removed it from source. **One isolated session-replacement assertion failed**: retained-run retrieval remained at one invocation instead of refreshing. Its fixture and output are retained outside the repository under `outputs/PageSessionAudit.reproduction.test.js` and `outputs/page-session-reproduction-isolated.log`. An earlier combined expiry test had event-listener interference and is excluded as evidence.
- Live end-user checks: Home load and verified access; Metadata Registry loading, successful asset retrieval, dictionary source selection (2,230 terms); Ontology Junction default taxonomy eventual population; Recommendations tab switching and direct Similar Parts object lookup; Data Flow eventual 67 runs, worker availability and selected run evidence; access revalidation; Admin overview; Graph Explorer eventual grouped/entity inventory.
- Navigation smoke checks also reached Import, Catalog, Products, Where Used, Quality, Change Control, Code Network, Modeling, ReqIF, QIF and Reports. Several snapshots captured only their lazy-loading state. These are navigation checks, **not completed functional acceptance of every page or tab**.
- No new imports, publication, replay, deletion, credential rotation or LLM execution. No injected live outage, real session-expiry wait, mobile/contrast certification, multi-user isolation or load benchmark. Fault behavior is covered partly by existing mocked tests and code tracing.

## Confirmed findings

| ID / severity | Exact source | Reproduction and root cause | Impact / recommended correction |
|---|---|---|---|
| PS-01 High | `frontend/src/pages/DataProductsPage.js:114` and `:161` | Render with `#/data-products?run_id=...`, complete initial retrieval, dispatch `depo:session-replaced`. The page's list and run-evidence effects subscribe to changed/cleared credentials but omit session replacement. Isolated test confirmed `getRun` stayed at one call. | Reconnect can leave an old artifact/receipt snapshot or canceled request outcome in the page. Subscribe consistently to session replacement, invalidate retained UI evidence before reloading, and test a late reply from the prior generation. Transport cancellation alone does not refresh already-rendered state. Do not replay a write during recovery. |
| PS-02 High / deployment | `frontend/src/Components/XmlAnalyticsLoader.js:42` | SHA comparison of source and `D:\GenAI_Projects\Apps\PMem` showed different loader contents. Products, Data Flow, Registry and serviceAuth matched in that comparison. The newer loader session guard is not in the installed source copy. | Passing source tests do not demonstrate installed behavior. Deploy a coherent release, rebuild frontend assets and verify the served bundle fingerprint. Retest reconnect during artifact upload and materialization result retrieval. |
| PS-03 Medium | `frontend/src/Components/registry/RegistryAssetsSection.js:96` | Open Metadata Registry while the request is pending. `!registryLoaded && entries.length > 0` renders “governed registry is unavailable” without checking loading or a failed outcome. Live reproduction showed this message with refresh disabled, followed by successful retrieval of one approved asset. | False outage message undermines trust. Represent loading, successful empty, stale and failed separately. Require a completed failure before showing unavailability; test slow successful retrieval. This was **not** a confirmed registry service outage. |
| PS-04 Medium | `frontend/src/pages/DataProductsPage.js:206` | Open Products before its collection request resolves. Live page simultaneously showed “Loading products”, “0 of 0 loaded versions match” and the widget's “No records available”. Discovery/table rendering is unconditional during loading. | Users read incomplete retrieval as empty business data. Show a loading row/skeleton and defer empty-state wording until successful completion. Preserve known rows with an explicit stale label during background refresh. |
| PS-05 Medium | `frontend/src/pages/DataProductsPage.js:219` | Empty-product instructions tell users to “Connect Admin credentials” while separately requesting ingestion/product scopes. Admin maintenance is a distinct optional capability, as the global banner correctly states. | Users may seek unnecessarily broad access or believe lack of maintenance access prevents publication. Name the required operation scopes and direct users to the existing connection flow. Do not imply maintenance authorization is mandatory. |
| PS-06 Low | `frontend/src/pages/MetadataRegistryPage.js:305` and `frontend/src/Components/registry/RegistryAssetsSection.js:98` | Live Registry shows a route title and a second identical page title. Footer says editing/approvals “will use” dedicated APIs while the page already renders register and lifecycle transition controls backed by those APIs. | Redundant hierarchy and outdated guidance confuse users. Keep one page title and describe current ownership and approval behavior. |

Line numbers refer to the current local source and can shift after edits. PS-02 is deployment evidence, not a newly discovered implementation defect. Severity describes workflow correctness and user confusion; no cross-user data leak was demonstrated.

## Confirmed code limitations / risks requiring further execution

| Risk | Evidence | Required validation or change |
|---|---|---|
| Health conflates listener reachability with capability readiness | `frontend/src/services/apiClient.js:407` accepts any fulfilled response whose status is not in a short denylist. `backend/ontology_service/router.py:273` returns `status: ok` independently of registry readiness. Header aggregates ten service checks. | Test malformed/HTML success, degraded and dependency-unavailable responses. Prefer a positive response contract, retain capability-specific readiness, and label transport health separately from model, worker and scheduler health. “Online” does not establish all business operations work. |
| Expiry handling is inconsistent in Products | Same effect subscription omissions as PS-01. Expiry emits credential changes in the normal shared auth implementation, but standalone replacement and expiry paths differ. | Reproduce with the complete auth layer and local auto-reconnect, including sleeping tabs. Do not cite the discarded combined diagnostic as proof of an expiry defect. |
| Similar Parts candidate discovery is broad | Live lookup for “induction motor” offered requirements/documents as well as parts, with long scopes and graph identities. This is an observed UX issue; final analysis correctness was not tested. | Show business type, source and revision, prioritize eligible parts, and explain excluded candidates. Validate final selected identity before analysis. |
| Existing suite misses a session event boundary | All existing tests passed while PS-01 reproduction failed. | Add a session-event matrix across each long-lived page: changed, cleared, replaced, expired, renewed and verified; distinguish identity change from renewal. Add real browser acceptance rather than treating mocked green tests as release proof. |

## Positive checks

- Shared request-generation cancellation is present in `frontend/src/services/requestSession.js`. Old Axios responses are rejected before adopting server session state in `apiClient.js`.
- `serviceAuth.js` rejects delayed old-session rejections and checks the current delegation before accepting a renewal response. Raw service credentials are memory-only; bounded delegated sessions use same-tab storage. These are code-backed safeguards, not a penetration-test certification.
- Data Flow applies independent reads as they resolve, uses load sequencing and handles session replacement. Live page distinguished disabled scheduler/execution configuration from one available pipeline worker.
- Registry dictionary has bounded page rendering (25 terms), source scoping, definition expansion and request abort guards. Live source selection populated data.
- Live access revalidation retained Data Flow run evidence without automatically replaying or publishing a job. No 403 was observed in these particular local read-only checks. This does not reproduce or dismiss customer-environment authentication failures.

## Required acceptance before release

1. Address PS-01 and deploy the current loader guard as a coherent frontend release.
2. Add failing-then-fixed regressions for slow Registry loading, pending Products empty states and session replacement with retained run evidence.
3. Execute two-tab reconnect, expiry during navigation, late read after logout, worker interruption after accepted write, and offline/recovery scenarios.
4. Verify each page's final loaded state and important tabs at desktop and narrow widths, keyboard focus, modal escape/return and contrast. Current navigation smoke coverage is insufficient for that claim.
5. Test customer routing/origin, CORS and credential synchronization independently. Never resolve 403 by bypassing approval or authentication.

Recommendation: **do not call this release-ready based on the 817 passing tests alone**. Prioritize session replacement and deployed/source consistency, then loading-state truthfulness. Existing uncommitted work and local audit captures have not been committed or pushed by this audit.

## Remediation addendum — 31 October 2026

The preceding sections record the original audit. Implementation and deployment
work subsequently addressed the six confirmed findings:

- PS-01: Products list and retained-run evidence now invalidate/reload on
  delegation replacement and expiry. A regression resolves the earlier request
  after replacement and verifies that it cannot restore the old schema receipt.
- PS-02: The latest loader guard and page fixes were copied with backups to the
  local deployed frontend and rebuilt using its existing `.env.local` routing.
  This closes local deployment drift for these files, not customer deployment.
- PS-03: Registry shows loading instead of unavailability while its request is
  pending. A delayed-success regression covers this boundary.
- PS-04: Product discovery waits for initial retrieval to finish; the empty
  widget is also withheld when the request fails.
- PS-05: Product guidance names publication access and distinguishes maintenance.
- PS-06: Removed the duplicate Registry title and outdated future-tense guidance.

Health response validation now requires an explicit positive status. The shell
uses pipeline `/readyz`, independent of the optional Spark state shown in Data
Flow. A live check caught and corrected the initial false degraded status when
Spark was intentionally disabled.

Live rebuilding exposed another confirmed defect: Vite deleted lazy assets used
by an open tab. The Windows builder now builds into a separate staging directory,
merges new assets without deleting old ones and atomically replaces index.html
last. Success/failure tests verify preservation of the previous index/assets on
failed compilation and retention of open-tab assets on success. Old assets are
intentionally excluded from automatic cache cleanup.

Validation: **826 tests in 135 frontend files passed**. After the final pipeline
readiness correction, 54 focused tests passed. Dependency, release selection,
safe-cache and staged-build checks passed (10 + 2). Production builds passed.
React test act/deprecation warnings and large frontend chunk warnings remain.

Local backups: `D:\GenAI_Projects\Apps\PMem\logs\page-audit-deploy\b095899da52d44a4ba3ebef6a17f2fe8`.
Logs and reproduction output remain outside the customer release. No database,
workflow history, retained upload, credential or LLM configuration was cleared.

Still open: full two-tab/customer-origin acceptance, real expiry/offline and
interrupted-worker scenarios, and the broader Similar Parts candidate UX review.
The six implementation fixes do not imply those acceptance tasks are complete.

Final local verification: Registry loaded its approved asset with the corrected
guidance and a single page title. Products showed the revised scoped-access
instructions after retrieval. API revalidation retained verified access and the
shell reported Online with the corrected pipeline readiness probe. A real staged
rebuild retained all 94 pre-existing assets; SHA checks confirmed the six changed
runtime page/transport/builder files match the deployed copies. No customer
environment was changed.

### Similar Parts selection follow-up — 2026-10-31

The resolver now accepts an analysis scope. Similar Parts includes declared or
mapped parts and assemblies, excluding other/unverified types without guessing
from names. One bounded batch retrieves mapped types. The selection table shows
type, available revision/source, and expandable record identity and ontology
scope; duplicate names retain separate identities. Other analyses keep their
broader business-object scope.

Validation: 37 backend and 67 frontend focused tests passed; production build and
local restart passed. Browser authentication and ontology reads passed. In the
live Similar Parts UI, `induction motor` returned 10 eligible records and explicitly
reported 10 excluded records and additional bounded matches. Some requirement
specifications remain declared as products in the imported source; the selector
therefore still classifies those records as parts. Correct semantic typing is a
remaining data-quality issue, not resolved by this UI filter. Customer-origin,
real expiry/offline and interrupted-worker acceptance remain unverified. No LLM
execution, publication or database cleanup was performed.

Follow-up classification correction: mapping evidence is now checked for generic
parts/assemblies as well as unclassified records. Explicit Requirement, Document,
Specification, Test and Measurement types take precedence over a generic Product
type. Scalar RDF type values are handled without character expansion. This does
not infer semantic types from display names or repair absent source declarations.
Regression validation: 43 resolver/customer-audit tests and 34 recommendation
scope, goal and shared-policy tests passed (77 total); five existing merge-loader
deprecation warnings remain. No whitespace errors were found by git diff --check.
