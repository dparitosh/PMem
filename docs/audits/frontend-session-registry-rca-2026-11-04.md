# Frontend session and registry root-cause analysis

## Scope and outcome

Reviewed delegated browser access, request generations, renewal/logout, ontology catalog aggregation and Metadata Registry rendering. Four timing/resource behaviors were reproduced with executable tests; a fifth presentation defect was confirmed by the provider/consumer contract. All five now have source corrections and regression coverage (see correction verification below). The original audit was read-only; subsequent remediation changed production source. This is not a complete application or customer-network certification.

## Existing flow

1. Runtime service configuration and the local broker/Admin flow obtain delegated profiles.
2. `serviceAuth.js` owns tokens, same-tab sessionStorage restoration, expiry, renewal and cross-tab signals.
3. Custom window events invalidate requests in `requestSession.js` and reset feature state. Axios attaches credentials based on service contracts.
4. `OntologyContext` reads the native catalog and ingestion registry, merges identities and exposes a list/error/warning.
5. Metadata Registry separately reads governed assets and dictionary terms. These records are distinct from imported ontology registrations and graph publication.

The architecture has useful isolation: no credential transfer through cross-tab signals, request-generation checks against late responses, identity checks on renewal results, abortable reads and no automatic replay of accepted writes. The defects concern lifecycle coordination around those safeguards.

## Confirmed register

### FS-01 / High — renewal single-flight belongs to the module, not the session

- Exact location: `frontend/src/services/serviceAuth.js:206`, `:211`, `:240`.
- Reproduction: start renewal for A, install B before A returns, request renewal for B, then complete A. Only one fetch occurs and both callers receive null. B's credentials remain intact, but B never issued its own renewal.
- Root cause: `renewalInFlight` lacks a token/generation key and reconnect does not detach it. The response identity guard protects against restoring A, but cannot provide B's renewal.
- Impact: a slow old request delays or suppresses renewal of a replacement session. Expiry is a risk when B has little time remaining; actual expiry was not demonstrated.
- Recommended fix: session-keyed single-flight with an owned controller; retire the old flight on replacement/logout. In `finally`, clear only the flight instance being finalized. Do not retry writes.

### FS-02 / Medium — wall-clock timestamps cannot order equal-millisecond events

- Exact location: `frontend/src/services/serviceAuth.js:63`, `:176`.
- Reproduction: create a logout timestamp, install a replacement session in the same mocked millisecond, deliver the older signal. The new credentials clear.
- Root cause: `sentAt < connectionStartedAt` cannot distinguish earlier events with an equal timestamp. The logout signal is not tied to a connection identity.
- Impact: intermittent reconnect cancellation across tabs. This is not token disclosure or an authentication bypass.
- Recommended fix: define cross-tab logout semantics explicitly, associate signals with the connection/session generation they revoke, and keep independent sessions separate. Preserve deliberate global sign-out as a distinct action if required. Do not rely solely on `Date.now()`.

### FS-03 / Medium — caller abort listeners outlive successful requests

- Exact location: `frontend/src/services/requestSession.js:28`, `:38`.
- Reproduction: prepare and track a request using a caller signal, then release it after completion. The parent signal's abort listener remains and the credential controller remains un-aborted.
- Root cause: release only removes the controller from the pending set. Its listener is anonymous and is removed by the child signal only when that controller aborts.
- Impact: callbacks/controllers can accumulate when a long-lived parent signal serves many completed requests. The retained listener is confirmed; production heap growth was not measured.
- Recommended fix: retain a listener-disposal handle and remove it on release, including error paths. Preserve/reattach forwarding for bounded Axios retries rather than breaking cancellation during backoff.

### FR-01 / Medium — independent registries share one completion barrier

- Exact location: `frontend/src/contexts/OntologyContext.js:56`, `:105`.
- Reproduction: native catalog resolves immediately, ingestion remains pending. The context still exposes no catalog records until ingestion settles.
- Root cause: a single `Promise.allSettled` gates publication of both source results. A 15-second ingestion timeout or multi-page catalog load becomes user-visible delay for an already-ready source.
- Impact: apparently empty/loading registry despite available data. This is frontend source coupling, not proof of database failure.
- Recommended fix: maintain per-source loading/error/generation state, publish successful results progressively, merge by stable identity and show partial completeness. Apply one session generation to every source so older identities cannot repopulate the list.

### FR-02 / Medium — partial registry warning is dropped by the page

- Exact location: `frontend/src/contexts/OntologyContext.js:105`; `frontend/src/pages/MetadataRegistryPage.js:71`.
- Reproduction: one source fails and the other succeeds. The provider emits a warning, not a fatal error. Metadata Registry does not consume that warning.
- Root cause: the consumer destructures list/loading/error but ignores completeness metadata. Governed-asset success does not establish that the ontology-source list is complete.
- Impact: available ontologies can look like the complete registry even when one owner service failed. This finding is source-contract inspection, not a newly executed browser scenario.
- Recommended fix: render a persistent nonfatal source/completeness notice and offer targeted retry. Keep ontology registrations, governed assets, publication and service authorization statuses visibly separate.

## Cross-cutting root cause

Session correctness is distributed across mutable module variables, custom event strings, window storage signals and feature-local abort controllers. Each layer protects its own late response, but no shared connection identity governs renewal flights, cross-tab ordering and registry completeness together. Registry presentation similarly reduces several independent sources to one list/loading flag.

Recommended structure within the existing SPA:

- One session snapshot: connection generation, delegation identity, scoped profiles, expiry and renewal state.
- One subscription boundary to that snapshot. Feature reads receive its generation and cancellation scope.
- Renewal scoped to the current delegation; no refresh cascade or automatic write retry.
- Per-source registry states: not connected, loading, available, partial, stale or unavailable. Zero is shown only for a successful empty result.
- Retained workflow IDs remain independent of access tokens. Reconnect verifies receipts rather than replaying operations.

This does not require microfrontends, another identity platform, Redux or a new query dependency. The highest-value work is clarifying ownership and contracts in the current modules.

## Verification

### Correction and regression verification

All five findings now have source corrections. Renewal single-flight ownership is keyed to the session object; an obsolete flight cannot clear a replacement flight. Non-secret logical revisions order sequential cross-tab connection/logout events, with conservative timestamp handling for legacy signals. A restored session advances that revision too. This is browser coordination, not server-side revocation or a replacement for authorization.

Completed requests explicitly detach caller abort handlers; retry backoff retains cancellation and final completion removes it. Registry sources publish independently, keep native merge precedence, and ignore completions from aborted generations. Metadata Registry displays the provider's completeness warning alongside loaded content.

The four diagnostic cases have been converted to desired-behavior regression assertions. Additional checks cover partial-source failures, late completions after replacement, renewal ownership after an old flight finishes, and the Metadata Registry warning. The complete service/context and Metadata Registry selection passed: **29 test files, 164 tests**. Production Vite build passed (existing large-chunk warnings remain). No database migration or credential change is required.

These corrections are in the source checkout. They have not been copied into the separately installed application. Real multi-tab browser acceptance and a production memory soak remain unverified; automated event/async tests do not establish those outcomes.

### Customer installer interruption remediation

The reported E:\\App\\PMem setup failed because Setup did not invoke the process-visibility/elevation guard before entering shutdown. Backend stop discovered an unreadable tracked ingestion PID only after initiating other stops. Setup now routes hidden identities through the existing UAC flow, preserving Python, reinstall and credential policy arguments and preventing elevation loops. Setup/update/backend stop also perform a read-only batch visibility check before any stop request. Process ownership/creation-time checks remain enforced; ExecutionPolicy Bypass does not grant process access.

Installer regression result: **41 passed, 3 subtests passed, 1 Bash-only skip** across management elevation, customer entrypoints, process guards and upgrade preflight. The added behavioral fixtures use fake processes and exercise hidden, visible, exited and malformed tracking states. Detailed November release notes were moved to the operator reference so the customer runbook remains concise. No migration or credential rotation was introduced.

Customer recovery requires deploying this complete release and rerunning the original Setup command. If UAC is unavailable, run that command as administrator. If inspection remains denied while elevated, Windows access policy must be corrected; deleting PID tracking is not a repair. The E: customer host is not accessible from this session, and these source changes have not been deployed there.

### Follow-up code review and corrections

The review found and corrected the following additional paths:

| Defect | Location | Correction and regression |
| --- | --- | --- |
| A retry delay was removed from the pending-request set, so reconnect did not immediately abort it | `frontend/src/services/requestSession.js`, `releaseRequest` | Retain the controller during backoff; an explicit reconnect-event test verifies immediate cancellation. Final completion still releases it. |
| Errors during request preparation could lose the request config and retain the parent abort handler | `frontend/src/services/apiClient.js`, request interceptor; `frontend/src/services/agenticApi.js`, `applyAgenticAuth` | Both preparation boundaries release on throw. Tests force an expired deadline and malformed agent headers. |
| A fast empty ingestion refresh temporarily removed an existing native ontology selection | `frontend/src/contexts/OntologyContext.js`, `fetchOntologies` | Retain each source's last confirmed rows while that source refreshes under the same identity. Clear all source caches on identity replacement, expiry and cleanup; final partial results retain their warning. |
| A malformed non-secret logical clock could become Infinity | `frontend/src/services/serviceAuth.js`, `nextSessionRevision` | Validate the stored counter; corrupted-clock regression verifies a finite safe integer. |
| Setup elevation could append management-only flags unsupported by Setup | `infra/windows/process-control.ps1`, `Invoke-DepoVisibleManagement` | Forward those flags only to management; assert their absence in the elevated Setup command. |
| A readable tracked service using an unapproved runtime was not rejected until its turn in shutdown | `infra/windows/process-control.ps1`, `Assert-DepoTrackedProcessVisibility`; `manage-depo.ps1` | Validate known tracked service modules/runtimes before the first stop across setup, update and management. A behavioral fixture verifies rejection without mutation. |

Resource regression: **10,000 completed requests leave zero caller abort listeners attached**. This is bounded automated resource testing, not a browser heap soak. Follow-up Windows regressions: **42 passed, 3 subtests passed, 1 Bash-only skip**. The final complete frontend service/context and Metadata Registry selection passed **170 tests across 29 files**. Production Vite build and `git diff --check` passed; existing large-bundle and React test-utils deprecation warnings remain. No customer-host or real two-tab browser acceptance result is claimed.

### Customer install/update path review

The customer entrypoints were reviewed through release/package gates, retained configuration, dependencies, process shutdown, migrations/indexes, service startup and post-upgrade review. Confirmed gaps corrected:

- Updates previously skipped Python lock reconciliation when runtime files existed and frontend dependencies were current. All updates now use the existing checkpointed installer; verified unchanged dependency receipts skip installation, while changed Python/frontend and isolated worker/API locks are reconciled. The legacy `-InstallDependencies` flag remains accepted.
- Tracked ownership checks now run during read-only update preflight and before optional timeout configuration edits. Guided Setup requests any required elevation before entering this preflight.
- Direct root installation now validates the release package before dependency installation or migrations, matching the guided/update entrypoints.
- The disposable PostgreSQL upgrade test no longer assumes version 18 is unused; its injected failing migration uses the next version after the current release.

Verification: package validation passed for **84 PowerShell scripts, 10 APIs, 3 workers, 190 locked Python distributions and 18 migration files**. The selected installer/dependency/migration regression suite passed **85 tests and 24 subtests**. Two explicit skips: Bash unavailable, and no isolated `DEPO_TEST_DATABASE_URL` for `depo_acceptance_test`. The maintained offline upgrade fixture additionally checks dependency reconciliation by default, process-ownership failure before timeout edits, read-only preflight, preserved settings, idempotence and nonzero child failures. This does not claim a live customer database upgrade.

`INSTALLATION.md` and the linked operator reference contain the Administrator PowerShell preflight/update/diagnostic sequence. Preserve customer environment files, artifacts, history and dependency checkpoints; no reset or automatic publication is part of this update. These source changes still require deployment as a complete matching customer release.

### Original diagnostic baseline

Executed six Vitest files: 61 tests passed. Of these, four RCA tests deliberately assert the observed defective behavior and are diagnostic reproductions, **not acceptance proofs**. The other 57 are existing session/registry regressions. React emitted a test-utils deprecation warning.

Reproduction files:

- `frontend/src/services/sessionRegistry.rca.test.js` — three session/resource behaviors.
- `frontend/src/contexts/OntologyContext.rca.test.js` — slow-source coupling.

Command from `frontend`:

```powershell
.\node_modules\.bin\vitest.cmd run src/services/sessionRegistry.rca.test.js src/contexts/OntologyContext.rca.test.js src/services/serviceAuth.renewal.test.js src/services/apiClient.session.test.js src/contexts/OntologyContext.cleanup.test.js src/pages/MetadataRegistryPage.test.js
```

Before closing fixes, convert diagnostic assertions to desired behavior, add a partial-warning UI test, and run real two-tab reconnect/logout, delayed registry responses, repeated request cleanup and refresh restoration. No browser or production memory-soak run was performed in this audit.
