# Frontend navigation, session and runtime refactor — 2026-11-02

## Scope and architecture decisions

PMem remains one React/Vite SPA. Existing lazy routes, shared API interceptors, single-flight delegated-session renewal, server approval checks and bounded workflow receipts remain in place. No new framework, query package, identity provider or service is introduced.

URL state owns workspace views for Data Flow, Data Products, Catalog, Metadata Registry and Ontology Junction. Existing structural/pipeline/portfolio deep links remain recognized. Form data and D3 coordinates are not promoted into URL state. Change Control already uses abortable reads; its read-only approval boundary is preserved.

## Confirmed gap register

| Severity | Location | Root cause / reproduction | Result |
| --- | --- | --- | --- |
| High | frontend/src/services/serviceAuth.js:52 | Logout in one tab did not clear another tab. A delayed cross-tab signal could also clear a newer connection. | Same-deployment non-secret storage signals; logout across tabs, same-delegation expiry matching, timestamp guard against pre-reconnect signals. Tokens never travel through the signal. Independently authenticated tabs retain their own credentials and renewals. |
| High | frontend/src/app/AppPageOutlet.js:15 | Route ErrorBoundary retained its error when moving to another page; shared Products/Catalog component could retain the wrong workspace state. | Boundary keyed by page, isolating errors and page-local state. |
| Medium | frontend/src/pages/DataFlowPage.js:147 | Leaving/reconnecting discarded late results but continued unnecessary reads. | Owned AbortController for health, telemetry, runs, definitions and selected-run reads; abort on departure, reconnect and run-link changes. Already submitted writes retain receipt recovery rather than pretending HTTP cancellation undoes execution. |
| Medium | frontend/src/app/useRouteView.js | Local tab state diverged from history/deep links. | Shared validated URL-backed view hook, with legacy Product link aliases; run selection also writes its run_id. Back/forward does not submit work. |
| Medium | frontend/src/app/AppShell.js:52 | Focus stayed on departed page controls; transient access banner insertion moved content. | Main-landmark route focus, body scroll reset and a reserved access-status area. Existing nonmodal Companion focus return retained. |
| Medium | frontend/src/app/pageRegistry.js:12 | Cold route chunks waited for click. | Shared finite import-promise cache and hover/focus prefetch; save-data/2G avoids speculative loads. This caches code, not approval evidence or credentials. |
| Medium | frontend/src/services/analyticsProductDraft.js:36 | Retained sources containing analytics schema metadata but no artifact_id were dropped. | Preserve schema lineage alongside the originating immutable run; original draft is not mutated. |
| Medium | backend/depo_platform/service_log_stream.py | Actively redirected Windows logs were unbounded. | Standard rotating handler with a thread-safe text stream: 10 MiB per file, five backups per stdout/stderr stream. Dedicated bootstrap redirects avoid Windows file ownership conflicts. Previous launch logs still archive before restart. |

## Rendering changes and limits

Stable workspace skeleton geometry, stable scrollbar space, visible keyboard focus, 44px controls, reduced-motion support and transform-based quality-bar animation replace avoidable layout work. Off-screen native reporting sections use content-visibility with intrinsic sizing; D3 canvases and virtualized grids are excluded because they measure their parent geometry. Existing 25-row run rendering remains bounded.

Do not interpret these changes as measured zero CLS or an INP/LCP guarantee. Large chart/grid bundles remain a build warning. Prefetch is interaction-driven, not a request to download every route merely because all navigation items are visible. Existing per-workspace retained snapshots and single-flight refresh remain the stale-while-revalidate boundary; no global cache of mutable authorization/proposals is introduced.

## Verification protocol

1. Cold-load each affected route in browser DevTools Performance with network/CPU throttling. Record LCP, interaction latency and layout-shift clusters, excluding expected user-triggered changes. Compare identical data/viewport/cache conditions; target CLS <=0.1, INP <=200ms, LCP <=2.5s, but record actual results rather than declaring compliance from CSS alone.
2. Open URL view/run deep links, switch tabs rapidly, then use Back/Forward. Verify URL, selected tab and run identity agree and Network shows no write caused by history navigation.
3. Delay read responses, navigate away and reconnect. Verify requests abort, old responses cannot populate the new scope, and submitted writes remain inspectable by immutable receipt.
4. Use two app tabs. Disconnect one; the other must clear displayed access. Reconnect, then deliver an old logout signal: new access must remain. Expiry of a shared delegation clears its clone; an independently connected session must not inherit credentials from another tab.
5. Cycle six workspaces at least 20 times with browser Memory/Performance recordings. After GC, inspect detached nodes, listeners, timers, D3 simulations and retained promises. A finite module cache is expected; growing business-record retention is not.
6. Test keyboard navigation, focus visibility, Companion close/Escape, reduced motion and narrow viewports. Check parent overflow, grid clipping and stable graph bounds.
7. Verify runtime log rotation with an isolated temporary writer (including simultaneous writes, Unicode and oversized output), and verify current service startup plus request/worker correlation after managed deployment. Archive deletion remains an explicit operational retention decision.

## Acceptance boundary

Local automated and live results are recorded below. Customer-origin/APIM networking, sustained production workload, actual customer KPI acceptance and the unreproduced customer-specific “not processed” response require that deployment's evidence. No credentials were rotated, customer product approved, graph republished or application database reset by this refactor.

## Automated verification results

- Final complete frontend suite: **151 files passed, 924 tests passed** (302.45 seconds). Evidence: workspace `outputs/frontend-full-final-2026-11-02.log`.
- Runtime/installation cohort: **48 passed, 3 subtests passed, 1 skipped** (Bash unavailable). Includes log-stream rotation, request outcome logging, actual PowerShell archive execution and installer compatibility. Evidence: `outputs/frontend-runtime-install-check.log`.
- Production Vite build passed; existing >500 kB chart/grid/shared chunk warnings remain. Evidence: `outputs/frontend-build-2026-11-02.log`.
- Offline package validation passed: 84 PowerShell scripts parsed, 38 documented paths, ten APIs, three workers, 190 locked distributions and 18 migrations. No dependency or migration added.

The first broad run found a genuine schema-lineage loss and outdated replay test fixtures (missing identity preflight, assuming health implied run-list completion). The source/fixtures were corrected before the final complete green run. Earlier failing logs are diagnostic history, not the final result.

## Final deployment and browser evidence

The release-wide rerun after retained-run reuse correction passed **151 files / 925 tests**. Final browser-found focus/landmark corrections passed **16 targeted tests** with existing retention/deferred-render tests preserved. Runtime logging rerun passed **26 tests**, including real logging reconfiguration in an isolated subprocess.

The first managed launch exposed Uvicorn dictConfig closing a handler owned by the text stream. The live stream now reopens its file after logging reconfiguration; the new subprocess regression reproduces that boundary. The managed retry completed, all ten service browser-session checks passed, and environment hashes were preserved. Prior failure/boot logs remain retained. No customer job was replayed or graph republished.

Real browser checks passed: URL-backed Data Flow/Product tabs and Back; selected-tab focus after Back; one main landmark; two tabs both disconnected after clearing one, then both independently reconnected. At the sampled 1265px viewport there was no document horizontal overflow; the sampled tab was 48.68px high. Access verification preserved the banner's 52px height and top position. No captured console errors remained in the tested tab. These observations are not a page-wide CLS/INP/LCP measurement or a sustained memory soak.

Evidence: workspace `outputs/frontend-release-final-2026-11-02.log`, `frontend-landmarks-final.log`, `runtime-log-final.log`, `frontend-refactor-deploy-retry.log`, `frontend-final-service-check.log`, `frontend-browser-acceptance.json` and `frontend-refactor-verified.png`. A final invalid-authorization probe produced a correlated 403 log without its marker credential. Runtime source/deployment hashes matched for all changed runtime files.

## Performance and upgrade follow-up

An explicit `?measure_ui=1` query before the hash enables a local, bounded Web Vitals probe, for example `http://127.0.0.1:3000/?measure_ui=1#/data-flow?view=runs`. Normal sessions do not load this chunk. The probe registers once and stores only CLS/INP/LCP numeric values, rating and units in `script#depo-performance-probe`; it sends no telemetry. Missing observations remain null. It uses the pinned [official Web Vitals library](https://github.com/GoogleChrome/web-vitals) and measures one document, not independent SPA route loads.

Local visible-browser sample: CLS 0.039083, INP 64 ms, LCP 924 ms. Eighteen navigation actions across Products, Catalog, Registry, Ontology, Graph and Data Flow produced no captured console errors. This is a navigation smoke test and local lab sample, not a long-duration heap-leak or customer acceptance certificate. Evidence: `outputs/performance-browser-2026-11-02.json` and `.png`.

A 180.5-second localhost read-only service soak completed 1,352 reads at concurrency four: no failures, median 16 ms, p95 63 ms, max 109 ms. Two temporary sessions renewed successfully; revocation returned 401 while the independent session remained 200. No QoS rejections were reported. No customer jobs were replayed. Evidence: `outputs/local-read-soak-2026-11-02.json`.

The updater now checks installed direct frontend dependencies against the lockfile before stopping services. Missing/changed versions enable the existing checkpointed dependency installation; unchanged Python environments reuse their checkpoints. This is a direct build-dependency check, not exhaustive transitive integrity verification. Offline upgrades still require the locked packages in the npm cache or an accessible registry. `-SkipFrontend` remains respected.

Verification: probe/startup tests 12 passed; dependency/upgrade cohort 9 passed, 1 skipped, 3 subtests passed; source and deployed production builds passed. Existing bundle-size warnings remain. Customer-network/slow-link acceptance, production-scale load and long-duration heap profiling remain unverified.
