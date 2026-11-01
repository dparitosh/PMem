# Semantic analytics acceptance — 1 November 2026

## Verified locally

- Standard updater deployed commit `99a29cd`; schema migration 015 and service/browser-session checks completed. Customer testing remains deferred.
- Browser-selected QIF Geometry revision 1.0.1 preparation ran on the native worker: `28906bdd-0505-45b6-acd0-f2c010e4810b`. Retained 4,600 triples, 382 vocabulary terms and zero typed business instances. No business KPI is asserted for this vocabulary-only source.
- New baseline captured TRS order 3 before source resolution. Worker review `407dc984-430d-4f82-ba71-2028ecfee4c9` completed with `no_selected_source_change_detected`. Browser displayed the assessment after access revalidation. Existing review findings were retained.
- Isolated `depo_acceptance_test` acceptance passed with actual PostgreSQL migration/COPY, numeric aggregation, dimension preview, idempotent retries, pinned replay and lost-lease rollback. Its disposable schema was removed. This test uses synthetic fixture records, not customer KPI evidence.
- Publication/API/contract/package tests: 15 passed, including rejected missing approval, idempotent retry, conflicting content, retained package integrity and Windows long paths. These use isolated stores and do not certify live catalog delivery.
- Semantic workbench frontend tests: 8 passed, including duplicate-submit protection, session generation handling and distinguishable prepared snapshots.

## Defects corrected during this continuation

1. Prepared datasets with identical names showed indistinguishable options. Include source version and a short snapshot identifier; do not substitute the projection-format version for the source version.
2. Product packaging used ordinary Windows destination paths even though content-addressed sources supported extended paths. Deep customer storage/staging paths failed in `shutil.copy2` with WinError 3. Normalize the package output root to an absolute extended Windows/UNC path before creating staging, copying, verification and atomic promotion. Regression packages and retries beyond 260 characters.

## Still open — do not describe as full release acceptance

- Live business-instance KPI/dimensional model acceptance and a governed published package delivered to the live catalog.
- Live worker interruption/recovery, simultaneous browser tabs and slow-service acceptance for this new flow.
- End-user source registration currently needs a retained RDF reference; live graph snapshot discovery and a file/reference selector remain separate UX work.
- Namespace selector includes unused RDFLib aliases; execution-engine wording can confuse disabled Spark with a healthy native worker.
- Full data marts, domain KPI formulas, cross-entity joins and unit normalization require reviewed business models. Current dimension output is a bounded preview.
- Customer environment acceptance and external LLM testing were not performed.

## Follow-up closure

- Live native-worker synthetic record acceptance completed. Preparation `856b6e49-95a4-4e06-8f2d-936be41dcc7d` extracted three explicitly typed records. Numeric run `30bff7a8-fec8-48c1-9be7-3e00fead50ed` returned three observations and average 4 for values 2,4,6. Dimension run `c918a7f2-c98a-4ae8-9dfd-1f3b2aef91c9` returned three rows without truncation. This verifies execution, not an industrial KPI model.
- A labelled local test semantic source was reviewed/approved and a test evidence package retained. Repeated publication returned the same digest. Live catalog delivery exposed a producer/consumer mismatch: absent optional ontology references were serialized as null, rejected by the catalog list contract. The producer now omits absent optional fields; a shared-schema regression checks the actual payload.
- Namespace choices now show entity-type namespaces only, one choice per namespace; stored aliases remain retained. Data Flow explicitly labels Pipeline API and Spark engine separately and clears stale health after failed reads.
- Focused checks: 21 frontend tests and 16 publication/package/contract tests pass. Production build passed before deployment.
- Test artifacts/products are explicitly labelled LOCAL TEST ONLY and retained for audit. They do not certify customer data, full data marts or domain KPI formulas.

## Deployment and live catalog closure

Release `e68e13d` was deployed through the standard updater with backups at `outputs/PMem-backup-e68e13d-20261101-070414`. All ten service endpoints and central browser-session checks passed. The environment-file hash remained unchanged. Migration 015 and indexes were verified; database servers and prior publications were preserved.

Retried the existing package through its authorized retry-catalog endpoint after the fix. Product `local-acceptance-numeric-evidence-20261101:1.0.0` is now published and listed as latest 1.0.0 in the live catalog, with a readable manifest. Browser Product portfolio visibly shows one retained package and zero pending deliveries. Its name explicitly says LOCAL TEST ONLY. This closes the live deterministic fixture-to-package/catalog acceptance path, not customer business validation.

Two simultaneous authorized replay requests were serialized: an overlapping call returned 409, and retry with the same idempotency key returned the completed run `e0b073c0-0676-56ed-87cf-cd05e867d9fe`. Recovery/replay/publication-response-loss suites passed 55 tests. This is not a claim of killing a live worker mid-transaction.

Remaining work is explicit: retained-RDF upload/reference selection and live graph snapshot registration UX; live forced-worker interruption and slow-network write acceptance; customer-specific KPI models, warehouse joins/unit policies and customer-environment/LLM acceptance. No full dimensional mart was created by the bounded dimension preview.

## Source, failure-recovery and business-model implementation

- Added Data Products → Add a data source from an RDF file: business name/file selectors, immutable retention, existing Metadata Registry draft ownership, bounded safe syntax validation and deterministic retry identity. No artifact IDs or bypassed approvals. Existing registered snapshots remain selectable; automatic live graph export is not claimed.
- Added a reusable opt-in real PostgreSQL worker-interruption test. It kills only its owned child while the transaction is blocked before projection persistence; observes zero partial datasets; lets the 30-second lease expire; starts a replacement worker; observes attempt 2 and exactly one dataset; removes the disposable schema. The first manual execution and the reusable test passed. Production workers are untouched by the crash test.
- Added explicit product/part/requirement/process type and predicate mapping to the existing semantic analysis worker. Results retain distinct-IRI dimensions, classification groups, recorded typed link facts and rate formulas. A real PostgreSQL fixture validates product=1, parts=3, classification A=2/B=1, requirement-link rate=50%, process-link rate=66.67%, BOM link pairs=1, and BOM completeness=not assessed. No identity merging, revision/effectivity assumptions or unit sums are introduced.
- Data Flow now reads verified completed analysis artifacts and displays business metrics, classifications, dimension members and source/target names in tables. Foreign or pending result evidence is rejected.

These close the implementation paths for local source registration, controlled recovery and top-down snapshot analytics. Customer-specific expected BOM scope, approved units/quantities and physical warehouse/slowly-changing-dimension models remain explicit extension criteria; these cannot be inferred from mere link counts.

## Final local end-to-end acceptance

- Browser source upload, preparation and business analysis completed through the real native worker. Preparation `61654890-7fac-4f9a-a76f-f9249edac3f6` retained 17 triples / 7 typed records. Analysis `24209743-55e6-44d3-9fb0-32bfafe3ab7d` displayed four dimensions, classification A=2/B=1, requirement-link rate 50%, process-link rate 66.67% and one BOM pair. BOM completeness remains not assessed. Full-width report screenshot: local `outputs/portfolio-business-report-10ae371.png`.
- Two browser tabs concurrently uploaded the same 20,000-triple fixture. During pending writes, one tab navigated and the other revalidated access. Exactly one draft source remained, with no implicit approval/publication. This exercised real service delay, not simulated browser packet throttling.
- A temporary loopback proxy withheld a successful response beyond a real one-second socket read timeout. The server had committed; retry resolved the same identity and exactly one registered record. The proxy was removed. Evidence: local `outputs/network-response-loss-acceptance-20261101.json`.
- Live cold-start review found pipeline source discovery initialized a duplicate graph runtime. Source discovery and resolution now call the owning Metadata Registry service with a bounded, authenticated read; malformed, unavailable or foreign responses remain explicit failures. Regression covers timeout, identity mismatch, paging and missing source.

Earlier open-item lists above are chronological findings, superseded by these local results where explicitly closed. Customer environment, external LLM, automatic live graph snapshot export, physical dimensional warehouses, expected BOM completeness and unit-normalized quantity KPIs remain outside this acceptance result.
