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
