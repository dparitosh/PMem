# Trace review and confirmed defect remediation

2026-10-31. This supplements the frozen initial audit; it does not replace its
inventory or claim that every static candidate is obsolete.

## Implemented

- OBS01: Customer ZIP creation refuses any modified or untracked working tree.
  This prevents the reproduced mixed tracked-content/untracked-dependency
  package. Selection-only checks remain available and are not certification.
  The complete reviewed change set still needs to be committed before release.
- OBS02: The older customer builder delegates to the canonical packager instead
  of maintaining a conflicting traversal, root file list and exclusion policy.
  Generated Maven target directories are excluded.
- OBS03: Preserve the exact authored API inventory consumed by the packaged
  request-contract tests. Other generated audit JSON/XML/images remain excluded.
- OBS04: Upload rejection returns failure; failed pre-commit prevents commit.
  The entire old import-helper directory and old frontend port-check helper
  are excluded from customer packaging. They remain development-only compatibility
  tools, not migrated/supported customer APIs.
- OBS05: The three identified direct graph loaders are excluded from customer
  packaging. Local migration tools are retained; none was executed.
- OBS06: Remove the five unsupported active-use claims from Admin's dependency
  allow-list; acknowledge active Siemens IX, XYFlow and ECharts dependencies.
  Unknown dependencies are explicitly unverified (`used: null`) rather than
  asserted unused. The maintained list is not a runtime coverage proof.
- OBS07: Remove contradictory Owlready2 supported-tool statements and replace
  obsolete memory-endpoint instructions with the current agentic endpoints.
  Standalone external connectors remain separately configured compatibility
  integrations; their defaults are not proof of a running PMem endpoint.

## Embedded traceability review

The existing tool is `tools/code_graph_audit.py`, surfaced by CodeAuditPage and
the compatibility host's `/api/v1/code-audit`. Its first scan included generated
audit reports as source/configuration nodes; literal file references made those
reports appear as high-priority application hubs. Both traversal paths now
exclude `docs/audits` from source analysis. Audit evidence remains on disk.

The reported foundation/owl_dl cycle contains a `__main__`-only import and is not
by itself a demonstrated startup failure. PowerShell cycles include literal
file references as well as invocation; they are not proven recursive execution.
Do not automatically delete or merge these nodes.

## Validation and limits

32 tests and 112 subtests passed: new package-policy and failure-sequencing
regressions, scanner hierarchy/exclusion, embedded foundation/JAR packaging,
runtime cleanup boundaries, request-body contracts and retirement behavior.
Tests use fixtures and mocks; no customer DB, import, publication or credentials
were changed. No application service restart was needed for these changes.

Follow-up cleanup removed the five confirmed unused frontend dependencies:
`@mui/material`, `@mui/x-tree-view`, `@emotion/react`, `@emotion/styled`, and
`web-vitals`. Offline npm installation succeeded; the lockfile lost 55 entries
without changing any retained package version. `npm ls --all` passed, and the
production build passed using an isolated output directory (served assets were
not replaced). No Python package was uninstalled without caller evidence.
The embedded scanner does not implement general code-clone detection or Git
branch comparison. Those analyses and external caller confirmation remain
necessary before broad consolidation; the original orphan candidates are not
approved deletions. Supplementary `clone-branch-review.json` records 878 Python
functions of at least 25 lines with no exact AST duplicate groups after ignoring
outer names/docstrings, and committed comparisons against seven local branches.
This is not general near-clone detection or proof of semantic equivalence.
The cache cleaner now reports individual permission failures and continues;
nine targeted cleanup/remediation tests passed, including simulated access denial.
Existing customer-environment acceptance and a clean release build are not
established by these tests. No commit or push performed.


## Final cleanup verification

All 837 frontend tests passed across 137 files after the dependency removal.
Production build and complete npm dependency-tree validation passed. Removed
15 reproducible cache directories (2,356,953 bytes). Windows denied deletion
of `.pytest_cache`; it remains local and excluded from releases. No credentials,
customer records, logs, retained uploads or artifacts were deleted. Detailed
results are in `cleanup-results.json`. Changes remain local and uncommitted.

Approved follow-up: `.pytest_cache` was successfully removed after verifying
its absolute repository path and rejecting reparse points. No ACL or ownership
changes were made. The earlier permission failure above records the first pass.

## Remaining-source follow-up

Fixed two additional scanner correctness defects: definition metadata no longer
overwrites complexity/oversize finding categories, and module-cycle analysis now
uses a separate eager-import edge set. API/file references, lazy imports and
`__main__`-only imports remain visible but do not establish module-initialization
cycles. An eager import followed by a lazy import/reference remains correctly
classified for cycle detection.

Identifier-normalized Python similarity screening examined 878 functions at least
25 lines long (9-token shingle Jaccard threshold 0.85). Seven candidates were
reviewed: five are overlapping enclosing/nested functions; one pair implements
different OWL existential/universal restriction semantics and must stay distinct.
The remaining generic/3DXML shared-attribute connection block was consolidated
into the base extractor. Their distinct explicit missing-target rules and
idempotent neighbor lists are preserved by regression tests. The similarity
report is a frozen pre-refactor screening result, not removal authorization.

38 targeted tests and 112 subtests passed after these changes. This includes
scanner false-positive controls, extractor behavior, retirement, package
foundation checks, cleanup and request contracts. The previous full frontend
test/build results remain applicable: this follow-up changes Python/tooling only.
External/customer environment acceptance and committing the reviewed change set
remain release steps; no automated source scan proves every path bug-free.

## Frontend legacy remnants

Removed `frontend/tools/check_backend.js`, an unreferenced checker hardcoded to
the retired port 8000 host. Removed `package.json`'s stale Create React App
`react-app`/`react-app/jest` ESLint extends configuration; the corresponding
toolchain is no longer installed and the supported build/test runner is Vite.
The obsolete checker path remains excluded from release selection to prevent
an old copy being reintroduced through customer packaging.

There is no separately identified old frontend application to blanket-delete.
`src/App.js`, `App.css` and `index.css` are live imports; `setupTests.js` is the
Vitest setup entry. `public/depo-runtime-config.js` is referenced by index.html.
`dist` is generated deployment output; old hashed chunks are intentionally
retained for already-open sessions. The refactored page wrappers and diagnostic
benchmark utilities are not obsolete merely because they lack source imports.

## Release preparation

The reviewed source set includes the earlier REST acquisition, workflow/session,
recommendation and dependency-profile fixes and their regression tests.
Generated audit captures are ignored instead of committed. Prompt contract tests
now use a maintained schema-only fixture under `backend/tests/fixtures`, so
release tests do not depend on an untracked workstation capture. An encoding
regression discovered during that move was corrected; all 89 prompt-security
tests pass. Development-only helper tests explicitly skip in customer packages
where those helpers are intentionally absent, and continue to execute in source.

Installation preflight passes (83 PowerShell files, 38 documented paths, ten
services, three workers, 190 locked distributions, fourteen PostgreSQL
migrations). All ten existing local service health endpoints return HTTP 200
with status ok; this is not acceptance of the new archive or customer deployment.
Full frontend results remain 837 passing tests and a successful production build.
Provider-dependent, backup/restore and customer-upgrade acceptance are not
certified by these source checks.

## Post-upgrade recommendation display correction

Live direct Change Impact testing found a recorded technical `name` displayed as
an encoded resource identity. Recommendation display now prefers usable recorded
names/labels/titles, then exact vocabulary label literals in bounded RDF metadata.
Resource URIs, scoped IDs, hashes, UUIDs and serialized markup are not business
names. Missing names are explicitly shown as "Business name not recorded".
Change Impact tables and dependency graphs also sanitize older retained path
labels; record identities remain unchanged and inspectable separately. No graph
records or ontology annotations are rewritten and no LLM call is added.

Validation: 73 backend recommendation/policy tests and 67 frontend result/recovery
tests passed, including label fallback, vocabulary literals, malformed metadata,
preserved part numbers and keyboard-accessible graph inspection.
