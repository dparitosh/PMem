# Tests, reports and logs

Executable tests are source code. Generated results are evidence of a particular run; they are not test cases and do not prove current release readiness.

| Location | Purpose | Treatment |
| --- | --- | --- |
| `backend/tests/` | Python unit, contract and integration regressions | Retain and maintain; consult conftest before running manual/live scripts |
| `frontend/src/**/*.test.js` | UI behavior and API-boundary regressions | Retain; run with Vitest |
| Browser/RPA automation | Removed on 2026-10-10 at the user's request | Playwright configs, audit specifications and screenshot helper are no longer shipped or maintained |
| `docs/audits/` | Findings, correction history and acceptance limitations | Dated evidence; use the current index rather than adding historical counts |
| `release-evidence/YYYY-MM-DD/` | Generated reports removed on 2026-10-10 | Not required in the customer package; historical summaries are not retained machine evidence |
| `deliverables/*-results.json` | Generated browser navigation results | Earlier local outputs removed in the reviewed 2026-10-10 cleanup; keep new evidence in release-evidence |
| `deliverables/*.log` | Generated build/test output | Earlier local outputs removed; logs are ignored and old pass counts are not current totals |
| `logs/`, `.pytest_cache/`, `frontend/test-results/`, `frontend/playwright-report/` | Runtime/generated data | Ignored; review for secrets before sharing |
| `excluded-review/` | Previously excluded material awaiting review | Reviewed presentation intermediates and superseded patch packages removed on 2026-10-10; future material requires content/reference review |

Run tests using the environment installed for the project. The isolated dependency directory used in this workspace is a local convenience, not a customer installation procedure. Do not sum overlapping focused runs or equate mocked tests with live integration tests. A changed working tree is not the same version as its HEAD commit.

Minimum evidence for a run: command, time, revision, modified-tree status, suite and counts, exit status, dependency/runtime context, mocked/live boundary and skipped checks. Test output without a timestamp or revision is historical evidence with incomplete provenance.

The current verified summary is maintained in [the audit index](audits/README.md). Customer release gates are maintained in [the handoff guide](../infra/deployment/CUSTOMER_RELEASE.md).
