# Repository-wide obsolete and legacy code audit

Date: 2026-10-31. Checkout: `pmem-publish`, branch
`codex/windows-setup-audit-fixes`, committed base `ec9d8d5`, with existing
uncommitted work included in this audit. No application code, dependencies,
credentials, database records or retained artifacts were changed or deleted.

## Coverage and meaning of “100%”

Every file inside the defined inventory boundary has a classification and
disposition: **5,365 of 5,365 files**. This includes **all 3,270 tracked first-party
regular files**, plus 2,095 untracked/ignored local files. The only tracked entry
outside that inventory is the `external/sirius-web` Git submodule reference.

This is complete file inventory and automated screening, not a claim that every
line or possible execution path has been manually proven correct or unused.
No static analysis can establish that an externally invoked CLI, dynamic tool
registration, optional deployment or migration is dead solely because it has no
Python/JavaScript importer. This audit therefore provides removal candidates,
not blanket deletion authorization.

| Category | Files |
| --- | ---: |
| Application/tool source | 660 |
| Tests and fixtures | 579 |
| Deployment scripts | 111 |
| Documentation | 201 |
| Resources and configuration | 2,194 |
| Generated/runtime evidence | 1,620 |
| Total | 5,365 |

Explicit boundaries: Git objects, dependency environments, node_modules,
compiled/cache directories, frontend dist and the third-party Sirius submodule
were not recursively treated as first-party source. Every excluded directory is
listed in `summary.json`. The audit output directory itself is excluded to avoid
self-inventory recursion. Credential files are metadata-only where encountered;
business/runtime evidence is not copied into the report. A file hash is not a
semantic review of a binary or ontology. No unreadable metadata or Python parse
errors were found inside this boundary.

## Checks executed

- Parsed **906 Python files** with AST; no syntax errors.
- Parsed **84 PowerShell files** without executing install/start/stop operations;
  no parser errors.
- Parsed **393 JSON/XML-family resources**; no JSON/XML syntax errors. XML parsing
  disabled entity resolution, DTD loading and network access.
- Built conservative Python and JavaScript import graphs from the deployed
  service/worker manifest and SPA entry. Literal dynamic imports were included.
  Variable-driven imports and CLI invocation still need owner/reference review.
- Classified **80 no-static-inbound source files** and **42 exact-duplicate
  groups** for review. These are screening results, not counts of obsolete files.
- Screened 687 legacy/retirement/deprecation marker occurrences. Business
  lifecycle “deprecated” values are not treated as obsolete source code.
- Ran all frontend unit tests: **837 passed in 137 files**.
- Ran focused retirement, dependency-profile, OCR boundary, footprint cleanup,
  frontend-build publication and foundation-package tests: **21 passed**.
- Executed non-mutating packager inclusion predicates and isolated Admin package
  classification logic. Legacy HTTP helpers were tested with mocked HTTP only;
  no real upload, commit, database loader or LLM operation was executed.

## Severity-ranked findings

### OBS-01 — P1 — Current release selection omits new required source files

**Confirmed by executable file-selection probes.**

Location: `infra/deployment/build-release-package.py:31`, `:43`, `:81`.

Root cause: packaging selects tracked paths but reads their current working-tree
contents. It does not reject newly referenced untracked source modules. In this
checkout it prints PASS for 3,267 selected files while omitting:

- `backend/data_pipeline_service/rest_router.py`
- `backend/data_pipeline_service/rest_sources.py`
- `backend/data_pipeline_service/rest_submissions.py`
- `frontend/src/Components/RestSourcesPanel.js`

The acquisition subprocess entry `backend/data_pipeline_service/rest_fetch_worker.py`
is also untracked and required by `rest_sources._worker_command`; this dependency
is outside ordinary static import closure.

Reproduction: run the packager without `--output`, then compare its tracked file
selection against the current import edges and subprocess command. No ZIP is
needed to establish that tracked app/router imports point at absent archive files.

Impact: a source ZIP built now can fail imports/frontend compilation or acquisition
even though the local tested deployment works. This is a release blocker for the
current dirty checkout, not evidence that the deployed local services are down.

Fix: commit the complete reviewed source set before release; make packaging fail
closed on untracked required source and verify packaged import/resource/child
entry closure. Prefer packaging a clean reviewed commit over mixing indexed paths
with arbitrary working-tree content. Do not delete the new files as “untracked junk.”

### OBS-02 — P1 — Two customer packagers implement incompatible release contracts

**Confirmed by inclusion predicates and documentation references.**

Location: `tools/build_customer_release.py:12`, `:21`, `:39`;
`docs/REPOSITORY_MAINTENANCE.md:131`.

Root cause: the older walk-based packager is still documented, while the current
operator reference points at `infra/deployment/build-release-package.py`. The old
root whitelist excludes `Setup-DEPO.cmd` and `update-depo.ps1` (also `.node-version`
and `.nvmrc`). Its required-input check does not catch those omissions. Its folder
rules also admit generated `infra/reasoner/target/*` JARs alongside the canonical
verified runtime JAR.

Reproduction: call `permitted(Path('Setup-DEPO.cmd'))` and
`permitted(Path('update-depo.ps1'))`: both return false.
`permitted(Path('infra/reasoner/target/depo-owl-dl-1.0.0-shaded.jar'))` returns true.
No archive was built during the audit.

Impact: release contents and supported installation/update entry points depend on
which documented builder is chosen. Generated duplicate binaries can inflate the
older archive. The older builder also lacks the canonical foundation/JAR checks.

Fix: retire the older implementation or turn it into a thin delegate to one
canonical builder; update documentation and assert the complete customer-root
entry-point set. Do not retain two independent exclusion/required-file policies.

### OBS-03 — P2 — Broad audit exclusion removes a fixture required by packaged tests

**Confirmed by package predicates and the test's explicit file read.**

Location: `infra/deployment/build-release-package.py:21`;
`backend/tests/test_request_body_contracts.py:17`.

Root cause: every JSON file under `docs/audits` is excluded as workstation evidence,
but the tracked contract test reads
`docs/audits/api-crud-inventory-2026-10-10.json` as a required fixture. The test source
is included in the canonical package while that input is excluded.

Reproduction: evaluate `allowed` for the test and its inventory file: true/false.
Inspect the test's unconditional `Path(...).read_text()`.

Impact: the included test cannot run from that archive without a missing fixture.
This does not itself break production startup, but weakens reproducibility of
customer/release verification.

Fix: move maintained contract fixtures into an explicit test-fixture location or
whitelist those reviewed inputs; alternatively define a production-only package
that consistently excludes developer tests. Keep raw prompt captures excluded.

### OBS-04 — P2 — Legacy import CLIs have obsolete routing and incorrect outcomes

**Two behavior defects reproduced with mocked HTTP.**

Locations: `tools/import/upload_only.py:5`, `:22`;
`tools/import/run_commit.py:44`, `:45`, `:46`;
`tools/import/auto_import_xsd.py:23`;
`frontend/tools/check_backend.js:2`.

Root causes: helpers still default to retired aggregate port 8000 instead of the
selected service configuration. Several request calls do not carry required
current authorization. `upload_only.main()` returns zero even on HTTP 403.
`run_commit.main()` invokes commit after a failed pre-commit result rather than
stopping.

Reproduction: mock upload POST to return 403: exit code is 0. Mock pre-commit false
and commit as a spy: commit is still called. These probes performed no network
request or database write.

Impact: automation can report successful imports that were rejected, and request
a write after a failed prerequisite. Server-side checks still apply; no bypass
of those checks was established.

Fix: retire these developer-era helpers, preserving fail-loud migration guidance,
or consolidate required functions behind the current service URL/credential and
tracked-workflow clients. Stop on failed validation, propagate nonzero failures
and remove obsolete screenshot-helper branches. Eleven `tools/import` files are
classified for this migration in the disposition inventory.

### OBS-05 — P2 — Direct graph loaders remain outside governed publication

**Confirmed operational risk by code trace; intentionally not executed.**

Locations: `scripts/load_ontology_to_neo4j.py:1`, `:51`, `:204`;
`scripts/load_mbse_xmi_instances.py:409`, `:418`, `:442`;
`scripts/load_xpdmxml_instances.py:337`, `:349`, `:373`.

Root cause: historical sample loaders obtain configured database credentials and
write directly through the driver. The ontology loader explicitly advertises
bypassing the import pipeline; instance loaders include dataset cleanup switches.
These paths do not use the canonical retained publication/version/approval
workflow. The files remain tracked and selectable by customer packagers.

Reproduction: trace `main` to driver/session writes and optional `DETACH DELETE`;
there is no canonical publication receipt boundary on those paths. Do not run
these commands against a customer database to reproduce this audit finding.

Impact: an operator with database privileges can create legacy-shaped data or
delete a dataset outside the application's governed lineage and recovery model.
This is not a remote authentication vulnerability; it requires invoking the
privileged local loader.

Fix: quarantine as explicitly unsupported developer/migration tools, exclude from
ordinary customer distribution, or replace them with governed import clients.
Preserve any needed migration as a separately reviewed administrative operation.

### OBS-06 — P2 — Admin package usage flags are obsolete; unused frontend candidates remain

**Classification inconsistency reproduced by isolated function execution.**

Locations: `backend/routes/admin_routes.py:394`, `:447`, `:453`;
`frontend/package.json:6`–`:9`, `:29`.

Root cause: Admin hardcodes an older keep/remove list. It marks MUI/Emotion and
Web Vitals as `used: true` while marking current Siemens IX, XYFlow and ECharts
as `used: false / needs_import_audit`. The latter are actively imported by the SPA.
The current source import scan finds no usage of `@mui/material`,
`@mui/x-tree-view`, `@emotion/react`, `@emotion/styled`, or `web-vitals`.

Reproduction: execute only the AST-extracted `_package_registry` function against
the current package manifest; compare with `probes.json` import-file lists.

Impact: Admin gives misleading dependency-cleanup advice and old UI packages
continue to enlarge installation dependencies. No precise size reduction or
production bundle improvement was measured.

Fix: replace hardcoded “used” truth claims with maintained/derived evidence;
remove the five candidates as a coordinated manifest/lockfile change only after
peer-dependency review, clean installation, production build and tests. Emotion
supports MUI peers, so do not remove those in isolation. Testing Library DOM is
needed by the test ecosystem despite no direct app import; do not classify it as
unused. Consider moving test-only dependencies to devDependencies separately.

### OBS-07 — P2 — Operational documentation still instructs removed tools and routes

**Confirmed contradictory/current-route references.**

Locations:
`standalone/ontology_agentic_service/HOW_TO_BUILD_AND_TEST_WORKFLOWS.txt:30`,
`:72`, `:80`, `:106`;
`docs/AGENT_MEMORY_AUGMENTATION.md:67`.

Root cause: the standalone guide still describes executing Owlready2 tools and
lists their formats, then later says the obsolete tool has been removed. Memory
documentation still points at port 8000 and the old `agent-memory` namespace.
The active agentic router exposes `/api/v1/memory/status` on its configured service.

Impact: customers can try removed registrations, incorrect dependency installs
or unsupported endpoints even when current code is working.

Fix: rewrite the supported steps around current tools/routes and selected routing;
label historical upgrade instructions explicitly. No active application
`owlready2` import or direct requirement was found in the scoped code search;
the stale references here are documentation, not proof of a runtime dependency.

## Retirement opportunities, not deletion approvals

- `backend/main.py` is a 5,582-line controlled compatibility host; root `main.py`
  re-exports it for tests. The supported manifest does not launch it. The old
  `backend/agent`/`backend/chains` stack is reached through that host. Plan its
  migration separately; static production absence does not prove all external
  consumers have migrated. Do not delete it or remove LangChain packages blindly:
  shared graph/embedding modules still use parts of that dependency family.
- `parsers/xsd_parser.py` is test-referenced and outside the default manifest
  closure; evaluate consolidation against the active engineering schema parser.
  Its preservation tests are evidence of behavior, not an active production caller.
- `step_0_generate_ontology.py`, `backend/qif/worker.py` and the historical stage
  simulator are already small fail-loud retirement shims. The 21 targeted checks
  confirm retirement behavior. These are not simulated-success implementations
  that should be resurrected.
- The `legacy_artifact` endpoint, `Services` imports and legacy registry/identity
  aliases still have active service callers. Their names alone do not make them dead.
- AOI `__main__`, frontend server CLI, installer helpers, optional standalone packs,
  MBSE plugin tools, dynamic coded tools and package `__init__` files have legitimate
  non-import entry mechanisms. This is why the 80 no-inbound results are not a
  deletion list.
- Preserve versioned PostgreSQL migration history. Old version numbers are needed
  to upgrade existing customer databases and validate recorded checksums.

## Duplicate/resource cleanup boundaries

The 42 byte-identical groups are recorded in `duplicates.json`. Important cases:

- `.node-version`/`.nvmrc` copies serve different tools and are intentionally aligned.
- Service dependency-profile input copies preserve independently deployable roles.
- The two identical business PPTX filenames are documented compatibility aliases
  in `deliverables/README.md`, not two independently authored decks.
- A verified runtime reasoner JAR and generated Maven target JARs share content;
  clean only the generated build outputs after preserving the canonical resource
  and checksum contract.
- Artifact `.write-lock` files, version-named ontology resources and retained
  content-addressed evidence must not be deduplicated or purged based on hash alone.
  Database references, legal holds, versions and provenance must be reviewed first.

The 1,620 generated/runtime-evidence files are separated from application source.
They are not all unwanted, and their inventory is not permission to delete them.
Use the existing allowlisted cache cleanup for caches; use governed retention for
uploads, artifacts, histories and logs.

## Recommended sequence

1. Resolve OBS-01–03: produce one complete reproducible customer archive before
   removing legacy source. Commit the complete reviewed runtime changes.
2. Fix OBS-04/05 and documentation: retire/quarantine old write helpers and
   direct loaders, update operator paths and preserve explicit migration entry points.
3. Correct Admin dependency evidence, then validate a clean MUI/Emotion/Web Vitals
   removal with lockfiles and the full frontend suite. Measure disk savings afterward.
4. Migrate remaining compatibility callers and tests before removing the old host,
   old chat stack or duplicated parser implementation.
5. Clean generated caches/build outputs separately from governed retained data.

## Evidence files

- `file-inventory.json`: per-file size, hash where appropriate, category,
  tracked state and import/reference screening.
- `dispositions.json`: one disposition for every inventoried file; no deletion approved.
- `import-edges.json`: conservative first-party import edges.
- `duplicates.json`, `markers.json`: duplicate groups and line-based marker locations.
- `format-checks.json`, `powershell-checks.json`: complete format/parse results.
- `probes.json`: release selection, legacy helper outcomes and dependency evidence.
- `summary.json`: counts, roots, parse results and explicit excluded boundaries.

Frontend test log: `../outputs/obsolete-audit-frontend-tests.log` from the repository
root. Non-mutating probe log: `../outputs/obsolete-probes.log`. Inventory generation
and probe scripts are retained locally under that outputs directory. No full
backend suite with live integrations, destructive loaders, external LLMs, optional
Sirius/MBSE deployment, or customer installation was executed. No cleanup or
application fix was performed as part of this audit.
