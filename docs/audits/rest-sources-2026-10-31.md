# REST sources: database, backend and frontend audit

Date: 2026-10-31. Scope: the newly added Admin REST source registration,
Semantica acquisition adapter, pipeline worker integration and PostgreSQL
registry. This is not a certification of every PMem feature.

## Outcome

**Remediation update:** All six findings below are implemented in source. The
original findings and reproduction details remain as the audit history. Current
verification is recorded in the remediation section at the end of this document.

At the initial audit, the capability was not ready for unrestricted customer release. Five defects
were reproduced by added failure tests. An additional scalability gap is
confirmed by the list implementation. Existing happy-path checks did not cover
these state transitions or a real streaming HTTP body. No application fixes or
database modifications were made during this audit; new red regression tests
are intentionally retained as evidence.

## Live verification

The installed deployment at `D:\GenAI_Projects\Apps\PMem` responded successfully:

- PostgreSQL database `depo`, schema `semantic`, was reachable.
- The registry contains 5 job definitions and 67 run records. No REST source is
  registered yet, so zero forbidden-secret-field records does not establish
  secret handling for an actual customer registration.
- `semantic.depo_registry` has its unique `(namespace,key)` index plus namespace,
  status, recent-run and runnable-worker indexes. These support current lookup
  and queue access; this audit did not benchmark production-scale query plans.
- Health endpoints on ports 8010–8019 returned HTTP 200.
- Authenticated REST-source listing returned HTTP 200 and an empty list.
- Worker execution readiness and the frontend returned HTTP 200.
- No customer API was called, no source registered, no key changed and no graph
  publication attempted. No end-to-end customer acquisition or actual PostgreSQL
  REST-registration write was tested.

## Trace

Admin Data sources → explicit management/execution credential profile →
`apiClient` session/deadline policy → pipeline REST router → PostgreSQL
`depo_registry/rest_sources` → approved job definition → durable run input and
worker lease → `rest_sources.execute` → Semantica `RESTIngestor` → requests
response hook → bounded record extraction → ArtifactStore JSON/provenance →
PostgreSQL run output reference → Data Flow.

Preview branches directly from the REST router to acquisition and does not
retain a run. The target-model field is descriptive only. The resulting source
artifact is not an accepted semantic partition and cannot use the existing
semantic-publication endpoint directly. There is no automatic ontology mapping,
relational materialization or product publication in this connector.

## Defect register

### REST-01 — P1 — Response deadline does not interrupt a slow body

Location: `backend/data_pipeline_service/rest_sources.py:73`, `:80`, `:82`.

Root cause: the wall-clock check is inside the loop after
`iter_content(65536)` yields. A server can keep that read alive by sending small
chunks within the socket read timeout. DNS resolution also occurs before the
adapter's response budget starts; DNS delay is a separate untested risk.

Reproduction: `backend/tests/test_rest_source_timing_audit.py` uses a disposable
local HTTP server, the actual Semantica ingestor and requests body reader. Only
the SSRF transport destination is redirected within the test fixture. The
adapter clock is accelerated so its 20-unit budget is 0.2 seconds. A small body
dripped below the 64 KiB yield threshold takes about 0.78 seconds before the
adapter rejects it. The required interrupt assertion fails. No production SSRF
configuration was changed.

Impact: a slow endpoint can occupy worker execution or preview thread capacity
beyond the promised budget. A lease fence prevents subsequent persistence; it
does not interrupt the blocked HTTP reader.

Fix: enforce a cancellable absolute acquisition deadline around connection and
body reading, with bounded DNS/transport time. Preserve Semantica's SSRF-safe
transport and always close the response/session on cancellation. Do not merely
lower the per-read socket timeout or move the same check after another large
buffer.

### REST-02 — P2 — Failed preview retains a previous success result

Location: `frontend/src/Components/RestSourcesPanel.js:48`, shared action catch
at `:21`.

Reproduction: preview succeeds with Part A; the next preview rejects. The error
is displayed but `Connection succeeded` and Part A remain visible. The added
`failed preview must remove previous connection-success data` test fails.

Root cause: preview is only set on success or source change; starting/failing a
new preview does not invalidate it.

Impact: users can mistake old data and connection evidence for the latest test.

Fix: clear or explicitly mark prior preview stale when a new preview starts;
associate results with source identity and timestamp, and distinguish the
latest failure from any deliberately retained historical view.

### REST-03 — P2 — Empty refresh retains an invisible selected source

Location: `frontend/src/Components/RestSourcesPanel.js:36`, `:48`.

Reproduction: select a source and job, then refresh with empty catalogs. The
source dropdown no longer has that option but Preview remains enabled. The
`an empty refresh must clear a previously selected job and source` test fails.

Root cause: refresh replaces arrays without reconciling `source`, `job`, and
preview against the new arrays. Preview is gated on a nonempty string, not
membership in the current source list.

Impact: requests can target stale identities while the visible selection looks
empty. Server lookup still enforces existence; no successful unauthorized write
was established.

Fix: reconcile selection after each catalog result; disable actions unless the
selected record exists in the current loaded catalog and invalidate its preview.

### REST-04 — P2 — Reconnect permits duplicate unresolved acquisition submissions

Location: `frontend/src/Components/RestSourcesPanel.js:14`, `:51`;
`backend/data_pipeline_service/router.py:327`;
`backend/data_pipeline_service/run_records.py:116`.

Reproduction: submit Fetch with its response unresolved; dispatch session
replacement; reload sources/jobs; select the same source/job and Fetch again.
`reconnect must not enable a second submission while the first outcome is
unknown` observes two API calls and fails its single-submission assertion.

Root cause: reset releases the action lock and discards submission state. Initial
job execution has no stable idempotency identity for the UI to reconcile; the
backend creates a new run UUID for each enqueue.

Impact: repeated network snapshots, duplicate work and confusing run evidence.
This acquisition does not publish graph data, so duplicate graph publication is
not an established consequence.

Fix: retain an operation identity/outcome across reconnect and navigation; make
initial enqueue idempotent for that identity and actor/definition/source intent.
Reconcile a retained run before enabling resubmission. Another component-local
boolean alone will not cover two tabs.

### REST-05 — P2 — Job-catalog failure blocks independent source browsing

Location: `frontend/src/Components/RestSourcesPanel.js:35`.

Reproduction: source listing resolves successfully while definitions rejects.
The added `source browsing remains available when only the job catalog fails`
test fails: no source option is populated.

Root cause: `Promise.all` makes the independent reads an all-or-nothing UI load.

Impact: an unavailable job catalog prevents connection preview of a reachable
registered source.

Fix: load source and definition catalogs independently with separate errors and
generation guards. Gate acquisition on valid approved-job availability while
keeping source browsing and preview usable.

### REST-06 — P2 — Source listing has no pagination or result bound

Location: `backend/data_pipeline_service/rest_router.py:12`.

Confirmed by inspection: `.all()` loads the entire namespace and returns every
record. Reproduction: populate a disposable registry with N source entries and
call GET; there is no limit/offset contract to cap the response. No live scale
test was performed because the live namespace is empty.

Impact: future registration growth produces increasing database result, response
and dropdown-rendering costs. Existing namespace indexes do not bound result
size.

Fix: use the registry's bounded page query, expose total/next offset, and support
source search or paging in Admin. Do not silently hide sources with a fixed slice.

## Verified protections and explicit limits

Existing tests verify named request fields, strict malformed-field handling,
management versus execution authorization, secret references rather than secret
values in the registration, immutable source insertion, host allowlisting,
private-address rejection, redirect rejection, response byte/record caps,
record-path validation, worker queueing without API-thread ingestion and artifact
handoff without semantic acceptance claims. Pipeline OpenAPI validation passes.

HTTP with keys is explicitly requested behavior, not an audit defect. It sends
keys without transport encryption. HTTPS is preferable. The current connector
still supports only public hosts on standard ports, three header forms, one GET
request, no pagination and no automatic semantic mapping. Private-network APIs,
custom ports, OAuth refresh and query-parameter API keys are unsupported—not
tested as working.

## Test result accounting

- Existing backend/connector/request-body checks: **79 passed, 112 schema
  subtests passed**.
- Existing source-panel/Admin/session checks: **20 passed**.
- New frontend failure regressions: **4 failed**, confirming REST-02–05.
- New real-reader timing regression: **1 failed**, confirming REST-01.
- REST-06 is a confirmed implementation gap; scale impact remains unmeasured.
- Customer network, live outbound authentication, PostgreSQL source insertion,
  worker retry/crash after remote response, and two real browser tabs remain
  unverified. Health 200 responses do not substitute for these cases.

Evidence logs are local under `../outputs/rest-source-audit-ui.log`,
`../outputs/rest-timing-audit.log`, and `../outputs/rest-audit-runtime.log` from
the repository root. The red tests are in the repository for subsequent fixes;
they are not deployed into the running application. Implementation was unchanged
at completion of the initial audit; subsequent fixes are recorded below.

## Remediation — 2026-10-31

| Finding | Implementation | Verification |
| --- | --- | --- |
| REST-01 | Semantica acquisition runs in a killable child process with a maximum 20-second budget, bounded by an earlier inherited operation deadline. A child watchdog covers parent loss. | Real HTTP slow-body test reaches the actual requests reader and is terminated; blocked-startup and independent child-watchdog tests pass. |
| REST-02 | Preview clears at the start of each new connection check. | Previous-success/next-failure regression passes. |
| REST-03 | Source and job selections are reconciled with refreshed arrays; preview checks current source membership. | Empty-refresh and page-change regressions pass. |
| REST-04 | A persistent browser submission reference survives reconnect/navigation. PostgreSQL submission receipts, intent locks and initial enqueue reconciliation share one active run for an actor/source/job. Receipt lookup does not require re-executing a disabled job. | Reconnect, same-key retry, different-tab references, identity/version mismatch, pending-enqueue recovery and completed/new-snapshot tests pass. Real PostgreSQL simultaneous requests produced one run. |
| REST-05 | Sources and definitions settle independently with separate loading gates and generation checks. | Source browsing/preview works while definitions fail or remain unresolved. |
| REST-06 | Source listing uses registry page queries (default 50, maximum 100); Admin exposes next/previous pages and total count. | 121-record bounded page/no-overlap test and UI page-transition test pass. |

Regression result: **91 backend tests plus 112 request-schema subtests passed**;
**26 frontend tests passed**. The original red regressions now pass. The timeout
message correction was additionally rechecked by all four real-process tests.

PostgreSQL acceptance used three unique `rest_audit_<uuid>` registry namespaces
for sources, submission receipts and runs. It verified source registration
round-trip, concurrent submissions, one durable queued run and retained receipt
recovery using the real registry and advisory locks. Those exact namespaces were
cleared afterward; existing application namespaces were preserved. Test artifacts
remain under the local outputs directory. No external API or customer key was
used. The connector still does not infer semantic mappings or publish records.

Customer-origin browser, customer outbound authentication and external network
acceptance remain distinct from these completed local regressions. The initial
audit's release restriction is resolved for these six defects; it is not a claim
that every customer integration or PMem page has been certified.

Local deployment verification: backed-up deployment, staged frontend build,
schema/credential checks, all service endpoint contract checks and browser
authentication passed. Admin Data sources loaded the paged registry controls
with Online/read access verified; source/job refresh produced no browser console
errors. Runtime SHA checks matched tested acquisition, process, submission,
router and UI files. Databases stayed running and no existing records were cleared.
