# Recursive folder structure audit

Reviewed 2026-10-10 in the working tree on `codex/semantic-bridge-release`.

## Scope

The inventory covered 1,017 first-party folders and 2,906 files at scan time. It records 48 excluded runtime, dependency, Git and metadata boundaries. Their contents were not code-reviewed. This is a structure, reference and duplicate-file audit, not certification of every service or customer deployment.

[Machine-readable inventory](folder-structure-inventory-2026-10-10.json) contains folder counts, excluded boundaries, duplicate groups and tracked runtime files. Duplicate detection covered tracked source/text/reference files of at least 512 bytes; binaries and small boilerplate were excluded. The relative Markdown file-link scan found no confirmed missing targets; anchors and remote links were not validated.

## Findings

| Priority | Finding | Evidence and corrective action |
| --- | --- | --- |
| P2 | Generated TTL cache files are tracked inside source | Five UUID-named files under `backend/ttl_cache` are tracked. `backend/Services/owl_generation_service.py` sets its disk cache to that source directory. Move the cache to configured durable storage, preserve existing artifacts and verify consumers before untracking the files. Adding an ignore rule alone does not remove tracked files. |
| P3 | Exact duplicate engineering reference files | Nine STEP pairs in `backend/STP` and three standards/reference pairs under `data` have identical content. Timestamp/version names carry possible provenance. Consolidate through a provenance/alias manifest and migrate references before removal; matching hashes do not establish obsolescence. |
| P3 | Mixed ownership and naming | Backend contains `Services`, `Data`, `STP`, lowercase service packages and active `legacy` compatibility code. Keep active imports intact; migrate naming and reference assets in separately tested changes. A bulk rename or deletion is unsafe. |
| P3 | Generated material beside deliverables | Environment-reference generation scripts and the empty `.env-reference-review` directory sit under `deliverables`. Separate generators from customer outputs after checking their invocation paths. These scripts are not proven dead code. |
| P3 | Root dependency cache without a root package | Root `node_modules` contains a `.vite` directory and there is no root `package.json`. Treat this as a generated cache boundary, distinct from the required `frontend/node_modules` dependencies. |

No new P1 folder-layout defect was confirmed by this audit. Priority describes the demonstrated structural issue, not speculative service failures.

Empty leaf directories observed include `backend/tests/cat_test_results`, `backend/test_data`, `data/ontology_service`, `data/source_profiles`, `deliverables/.env-reference-review` and `infra/neo4j`. Some may be runtime-created placeholders. Their emptiness is not sufficient evidence to delete them.

## Cleanup and verification

The preceding cleanup removed 73 reviewed files totaling 6,250,066 bytes. [The cleanup manifest](../repository-cleanup-2026-10-10.json) records paths and hashes; it is not a backup. Active compatibility code, engineering references, application data, credentials and frontend dependencies were retained. No additional deletion was performed during this folder audit.

The installation-package check passed after cleanup: 63 PowerShell scripts, 29 documented paths, 10 services, 3 workers, 202 locked Python distributions and 10 PostgreSQL migrations. The frontend production build also passed. These checks establish local syntax/path/build integrity; they do not establish live PostgreSQL, Neo4j, gateway, authentication or workflow acceptance. Dependency/runtime boundary contents were not audited for vulnerabilities in this review.

The changes and audit records remain local and uncommitted. Customer release requires the live acceptance checks in [the release status](customer-release-status.md).

## Folder audit corrections (2026-10-10)

Generated TTL writes now use ARTIFACT_STORAGE/ttl_cache with atomic replacement,
validated task identifiers and legacy read compatibility. Five tracked cache
files were moved to the ignored local data/artifacts/ttl_cache directory without
changing their bytes. Environment-reference generators moved to
 tools/documentation; their developer-specific attachment input was removed.
Ignore rules cover legacy cache and document review intermediates.
Engineering reference duplicates and active mixed-case compatibility packages
remain intentionally retained pending provenance/reference migration.
