# Page audit remediation — 27 October 2026

Scope: Recommendations, Where Used, Ontology Junction and their shared read/session/workflow contracts. LLM execution is excluded. Earlier uncommitted changes were preserved.

| Audit ID | Change |
|---|---|
| AUTH-01 | Shared graph-read authorization guards the ingestion ontology-browser router. Exports use the authenticated client with cancellation and single-flight handling. Negative HTTP tests cover every browser route. |
| WU-01 | A new search invalidates traversal even on no match; a late response cannot restore the old tree. |
| WU-02 | Usage predicates define direction, including inverse PART_OF/USED_BY. Hierarchy links retain original endpoint identities. |
| WU-03 | Session replacement and expiry clear hierarchy state and cancel its requests. |
| WU-04 | Business typing and an explicit usage/reference predicate set exclude assertion/provenance records from the primary tree. |
| REC-01 | Process counts and nested result evidence are validated before rendering. Malformed evidence is an actionable response error. |
| REC-02 | Published scoped candidate retrieval uses the existing OntologyResource ontology_id index. Default search scope follows the selected ontology; legacy candidates use explicit label anchors. Coverage is disclosed. |
| REC-03 | Recommendation errors retain a Graph Explorer recovery path instead of a technical dead end. |
| AG-01 | Permanent status failures pause immediately; transient read failures have a three-attempt budget. Manual status refresh never resubmits work. |
| OJ-01 | Successful mappings remain visible when the dictionary and taxonomy fallback are unavailable; a warning explains the missing descriptions. Authorization failures remain fail-closed. |
| OJ-02 | Unknown source formats use all-source browsing rather than guessed PLMXML. Vocabulary browsing requests all source formats inside the selected ontology scope. |
| OJ-03 | Steward assessment is explicit and single-flight. Reviewer edits do not submit work; old results cannot attach to a different review key. |
| OJ-04 | Selected task status/preview errors and loading are visible with retry; new bridge work is held while source evidence is unavailable. Retained workflow recovery remains available. |
| OJ-05 | Catalog loading has elapsed, page and record limits; empty advancing pages are rejected as protocol errors. |
| UX-01 | Corrected ontology loading text encoding. |
| QA-01 | Merge test intelligence implements the current policy-evaluation contract. Tests retain production policy holds rather than bypassing them. |

Deployment uses the existing repository-root `update-depo.ps1`. These changes require matching backend/frontend files and a rebuilt frontend; no new PostgreSQL migration or credential rotation is introduced. The existing graph provisioning step creates and verifies `idx_depo_ontologyresource_source_scope`. Scoped retrieval unions the indexed ontology_id and source_ontology paths so legacy scope aliases remain eligible. Installation instructions include the sequence and customer smoke checks.

Validation records are saved separately under `outputs/page-audit-fixes-20261027`. The production build, complete frontend suite, expanded backend suite and real Neo4j EXPLAIN are recorded there. The scoped candidate plan uses NodeIndexSeek; legacy label retrieval remains bounded by the service time budget and is not a claim of arbitrary whole-graph performance.

No customer deployment, live merge/publication, destructive cleanup, live LLM response or multi-user load certification is implied. The installed local application may still serve its earlier release until the normal update is performed. Temporary preview checks use rebuilt frontend files against the existing local services; isolated HTTP tests exercise the changed backend boundary with synthetic artifacts.

## Validation results

| Check | Result |
|---|---|
| Complete frontend suite | 126 files, 725 tests passed |
| Final additional traversal/assessment checks | 12 passed, including two regression cases added after the full suite |
| Expanded backend suite | 180 passed, 4 skipped |
| Final index/upgrade/recommendation/policy checks | 55 passed, 1 skipped; overlaps the expanded suite |
| Final production build | Passed |
| Real Neo4j scoped query plan | Two NodeIndexSeek branches; no AllNodesScan |
| New source-scope index | ONLINE in the local validation graph |
| Git diff whitespace check | Passed |

Do not add overlapping recheck totals to the full-suite count. The optional OWL skips are due to `owlready2` being unavailable in the test interpreter. Existing React/RDFLib deprecation and build chunk-size warnings remain recorded in the logs.

The temporary loopback preview loaded the rebuilt shell but API reads from its test port were blocked by the installed services' CORS configuration. No production CORS rules were loosened. Therefore this run does not claim a successful live customer UI smoke test. After deploying the matching release through the documented updater, perform the same-origin browser checks in INSTALLATION.md. No customer runtime files, credentials or retained graph records were overwritten by this fix run; only the new non-destructive graph index was provisioned locally.
