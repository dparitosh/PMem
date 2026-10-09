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

Machine evidence is local and ignored under `release-evidence/2026-10-09/`: `frontend-tests.json`, `frontend-tests.log`, `backend-focused.xml`, `backend-focused.log`, and `run-metadata.json`. [Testing and evidence guidance](../TESTING_AND_EVIDENCE.md) explains older deliverables and executable test cases.

## Current correction records

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
