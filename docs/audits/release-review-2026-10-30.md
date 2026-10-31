# Release review — 30 October 2026

Scope: the last 24 hours, including commits faa1dbd, 47b599e, f18c35c,
e163688 and the current uncommitted diff. This is an incremental review,
not certification of every changed line or customer-environment acceptance.

## Confirmed corrections

- Pipeline API, scheduler and readiness checks default consistently to worker mode.
- Analytics evidence identifies schema, instance and receipt artifacts and preserves
  dependency relative paths.
- Product creation consumes typed retained artifacts; switching to untyped evidence
  clears prior inputs. Existing recovery state continues to take precedence.
- Committed analytics receipts remain visible when packaging evidence is pending.
- Existing projections are displayed before offering another materialization.
- Change Control now has navigation journey guidance.
- Chart dependencies have a separate bundle; Home is loaded on demand.
- Prompt audit uses the current learning API schema and complete observation fixtures.

## Executed verification

- Pipeline and XML materialization: 47 tests and 9 subtests passed.
- Cross-layer session, workflow, lineage, change-control and recommendation selection:
  75 tests and 9 subtests passed.
- Expanded installation/release/reasoning selection: 81 passed, 1 skipped;
  async cases initially could not execute without pytest-asyncio.
- Installed the existing requirements-dev dependency pytest-asyncio and reran
  prompt audit: 89 passed. The reasoning selection's async test also executed
  successfully in the combined run; that run had seven stale prompt-fixture failures,
  subsequently fixed and covered by the 89-pass rerun.
- Full frontend: 814 passed, 1 failed (missing Change Control guidance).
  Corrected that finding; affected suite: 6 passed. Full suite not rerun afterward.
- Product/loader focused regression: 21 passed before subsequent guidance-only edit.
- Production builds passed. Core bundle reduced from about 626 kB to 85 kB;
  entry reduced from about 702 kB to 688 kB. Browser loading benefit unmeasured.

## Remaining acceptance work

- Live browser verification against deployed changes, including reconnects, multiple
  tabs, slow responses, navigation and interrupted workers.
- Actual PostgreSQL/graph query-plan measurements and representative large inputs.
- Older runs without typed artifact roles need explicit artifact resolution.
- Complete end-user tables/columns, dimensions and KPI consumption experience.
- Verify retained recovery when source selection changes during an active submission.
- Review audit captures for sensitive content and retention before packaging.

## Cleanup and deployment

No existing audit captures, uploads, database records or logs were deleted.
Untracked historical audit outputs must not be included wholesale in a release.
Local source fixes have not been deployed or pushed. Generated frontend dist is
verification output and is not evidence that the running installation was updated.

Release decision: acceptance pending. Automated checks do not establish live
performance or customer-environment readiness.

## Subsequent deployment and acceptance evidence

Ten application files were installed with backups under
`D:/GenAI_Projects/Apps/PMem/logs/workflow-fix-deploy/30a3e5fa6c3e409d93404875d14f1799`.
Managed restart passed configuration, PostgreSQL schema/index checks, graph
constraints/indexes, embedded reasoning, all ten endpoints and browser auth.
Installed frontend asset: `index-CWMKipyJ.js`.

Live UI confirmed verified access, 67 retained pipeline runs, one available
pipeline worker, preserved run-to-product navigation and approved-release
selection that fills asset/version automatically. No publication was submitted.

Recovery/concurrency acceptance selection: 24 passed, 1 skipped
(`test_workflow_manifest_concurrency`, `test_durable_workflow_worker`,
`test_analytics_audit_recovery`, `test_xml_analytics_postgres`).
The PostgreSQL integration skip means real analytics materialization is still
unverified. Automated worker fixtures do not constitute a live worker-kill test.

Current remaining gates: representative database query measurements, real XML
analytics integration, live interrupted-worker and two-tab/expiry acceptance,
and review of retained audit captures. Source changes remain uncommitted.
