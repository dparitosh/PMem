# Ontology import resilience: root cause review

Date: 26 October 2026. Scope: multi-XSD selection, engineering conversion, ontology catalog persistence, quality checks, publication verification and customer service startup. Evidence combines customer tracebacks, source inspection, synthetic Semantica reproduction and fault-injection tests. This is not a live certification of the customer's E: deployment.

## Findings and corrections

| Finding | Evidence and impact | Correction/status |
| --- | --- | --- |
| Resource similarity confused with RDF identity | Two distinct synthetic XMI-style IRIs ending in `0001` and `0002` produced one Semantica duplicate candidate. The engineering workflow rejected any duplicate candidate. This can block valid distinct terms. The customer's exact XMI assessment is still unavailable. | Engineering RDF quality checks now explicitly use complete resource identity, including URNs. Repeated identities still block; similarity remains available for entity matching. Identity checks do not claim ontology consistency or semantic equivalence. |
| PostgreSQL success followed by mirror failure | `_save_metadata` committed PostgreSQL before writing `metadata.json`. A disk error could turn an accepted registration/transition into an API failure and encourage retries. | Mirror replacement is atomic. PostgreSQL failure still fails the operation. After a successful database commit, an OS failure writing the secondary mirror is logged without claiming that the commit failed. Mirror repair/monitoring remains operational work. |
| Missing artifacts caused publication-status 500s | Customer tracebacks identify missing `corrected.ttl` and `uploaded-schema-set.ttl` files referenced by catalog records. PostgreSQL schema verification cannot prove those files exist. | Verification reports missing/unreadable/invalid artifacts and an explicit recovery action. It does not replace graph receipts or publish data. UI publication stays disabled. This prevents the crash; it does not restore missing files. |
| Legacy registry rejected native registrations | The reason route resolved only the old upload registry before calling a resolver that already supports both registries. | Removed the legacy-only preliminary lookup. |
| Multi-XSD batching was not enforced at the queue boundary | Customer reports separate original-XSD rows after one selection. The current pre-change file-input test already produced one schema-set row, so the exact differing customer execution path/build remains unverified. | Moved bundling to the shared queue entry point. One XSD-only selection produces one schema-set job, with a visible source list and dependency preservation. Existing separately registered ontologies are not merged automatically. |
| Expensive conversion shared only a broad HTTP admission limit | HTTP admission allows many work requests; each engineering conversion can spawn a large parser process. No conversion-specific limit existed. | Added `ENGINEERING_CONVERSION_MAX_CONCURRENCY`, default 2 and range 1–8, per ingestion process. Saturation rejects before spawning, without an unbounded parser queue. Restart after configuration changes. |
| Optional Neo4j property warnings obscured failures | Customer logs reference absent optional `file_type` and `source_format_detected` properties. These notifications are separate from missing-file exceptions. | Use dynamic optional-property lookup while preserving the query's ontology scope and fallback semantics. No graph data/index mutation is required. Live query-plan validation remains pending. |

## Timing, retries and database boundaries

Registration retries use a content-and-metadata workflow identity, a process lock, a PostgreSQL advisory lock and a filtered source lookup. Publication uses retained jobs and independently verified receipts. These controls must be preserved: a common prefix is not an idempotency key, and changing metadata/source after an uncertain response creates a different operation identity.

The engineering conversion/registration API is still synchronous. Its parser subprocess has a deadline and result-size limit, and service HTTP calls have bounded timeouts under an outer workflow deadline. Increasing only the browser timeout cannot repair a stopped service, missing artifact, invalid credential or shorter gateway timeout. Browser disconnection/restart can still leave an uncertain conversion/registration result; it is not the same durability guarantee as background graph publication. A durable conversion job with a persisted schema-set manifest, stage receipts and a status endpoint remains an architectural enhancement. Do not describe synchronous conversion as a resumable background job.

PostgreSQL connections used for advisory locks are dedicated autocommit sessions; normal registry operations use a bounded pool. The audit did not demonstrate PostgreSQL corruption or a database-service failure in the customer logs. The configuration-fingerprint rejection is an intentional safeguard against reusing a process with different settings. Use the root restart command with the same absolute environment path rather than a second manual start with different effective options.

## Customer recovery and deployment checks

1. Deploy one complete reviewed release, rebuild the frontend and restart through the root lifecycle command. Refresh the browser and confirm a multi-XSD selection shows one schema-set row and its source count.
2. Back up PostgreSQL, Neo4j, the ontology catalog directories and the content-addressed artifact store together. Database schema/index validation alone does not certify artifact availability. Do not copy a different TTL under an old identity.
3. Restore missing files from the exact matching backup. A catalog `artifact_id` may identify a second retained, hash-verified copy in the artifact store; verify it before any repair. This review does not automatically restore or relink customer records.
4. Verify publication after artifact restoration. Retain current graph data during reconciliation. If exact artifacts cannot be recovered, generate replacement drafts and follow review/approval/publication; do not silently migrate approvals.
5. Verify browser identity separately from service credentials. A browser 403, transport timeout, filesystem failure and quality rejection require different remedies.
6. Test database unavailability, response loss after registration, service restart, disk permission failure, concurrent conversion and interrupted publication in a disposable customer-like environment. Confirm bounded failures, retry identity and retained graph receipts. No live customer failure injection was performed here.

## Validation and remaining limits

The combined backend regression run passed 90 tests. Earlier frontend runs passed 34 import/schema-bundle tests and 16 publication-panel tests, and the production frontend build passed. These are local automated checks; the database failure cases use injected faults rather than customer database outages.

Regression coverage includes distinct/repeated RDF identities, URN inclusion, PostgreSQL failure, successful commit with mirror failure, atomic mirror replacement, conversion admission/release, multi-XSD one-request behavior, dependency closure, stale file-read cancellation, native-catalog reasoning and publication verification without artifact/receipt mutation. Existing provider/startup tests and the production frontend build are also checked.

Remaining customer evidence: the SugarPlantMBSE quality payload, exact cause of missing files, deployed frontend/release identity, actual APIM timeout chain, live database capacity/query plans, full schema-set import and verified graph publication after repair. Earlier tests passed locally; they do not certify customer end-to-end success or backup restoration.
