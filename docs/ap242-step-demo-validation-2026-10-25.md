# AP242 STEP demo validation — 25 October 2026

Source: `D:\GenAI_Projects\SPLM_Folder\step_files`. Tests use the local PMem application and retain source files unchanged.

## Scope and identity

The directory contains 29 files and 26 unique content digests. Three byte-identical duplicates are excluded from repeat imports. The assembly references 19 companion STEP files. Source editions include AP242 MIM editions 1 and 3 and the earlier AP242 business-object XML model. The separately published Domain Model is edition 5; importing these files does not establish equivalence to that ontology.

Document SHA-256 now scopes normalized entity identities. STEP record numbers and XML UIDs remain in provenance. XML business `id` values are not global identities; duplicate UIDs remain invalid. Explicit source references and containment become `TRACE_TO`, without inventing assembly membership or semantic equivalence.

## Verified fixes

- BO XML identification requires an actual typed AP242 container, rather than a string in comments.
- Explicit dimensional units are not confused with unrelated units in representation contexts.
- Missing external IDs fall back to source record identity; repeated display labels do not create identity conflicts.
- Bounded CEIM validation can run without Spark. Spark-dependent jobs still require Spark.
- Validation and publication share a 50,000-record bound, counting entities and relationships together. File byte limits remain separate.
- Default publication scopes isolate documents; existing publication intents remain pinned for reconciliation.
- Import status distinguishes validation from a retained graph publication receipt. Data Flow can find exact run IDs and suppresses Publish after a receipt is retained.
- Import history now reads normalized entity/relationship counts from the retained run manifest, including valid zero counts; queued runs do not invent count evidence.
- Publication normalization, SHACL validation and RDF serialization run in the thread pool, leaving the service event loop available for health and UI requests.
- Canonical CEIM business types survive both database-query and Python graph filters. Overview samples across scopes instead of allowing the first sorted ontology to consume the limit.

## Confirmed publications

AP242 Domain Model `domain_model_40c563f76dee4839` was reviewed, approved and published through Ontology Junction. Job: `bc43c3f8-3976-4a58-bb47-65ffdc5302c0`. Receipt: 70,052 resources and 197,372 relationships.

Assembly `000687_A_1-INDUCTION MOTOR ASSY 5HP.stpx`: run `273360bf-8734-4bc1-880b-4005701a7251`, 326 normalized entities and 339 trace relationships; SHACL conforms. Retained publication: `ceim-ap242`, 1,331 RDF resources and 3,995 relationships. RDF counts include provenance and vocabulary, and do not equal business-entity counts. The approved semantic release used is `boc-core@1.0.0`; this is not proof of automatic alignment to AP242 Domain Model classes. The authenticated delegated actor is recorded as `deployment-bootstrap`.

All 23 validated unique STEP/STPX sources now have retained Neo4j publication receipts in 23 distinct scopes. Combined receipt counts: 230148 RDF resources and 712190 relationships. These are projection counts across document scopes, not deduplicated business-object totals. Initial publication controls were tested through Data Flow UI; remaining approved publications were executed sequentially through the same service endpoint, with a read-before-write and retained-receipt check per run.

## Source and scalability exceptions

- `000685_A;1-Coil for Three Phase Winding.stp`: normalization exceeds the 50,000-record batch contract; run `e5f407d4-9819-4c8e-82c9-16091fea9211` is held. Do not publish a truncated subset as the whole file.
- `000684_B_1-Rotor Shaft Machined_1.stp`: source is truncated at record `#7520` and lacks `ENDSEC` / `END-ISO-10303-21`. Re-export from the source application is required; the importer correctly rejects it.
- `000684_B_1-Rotor Shaft Machined_1 (1).stp`: approximately 64 MiB, more than 1.25 million source records; synchronous normalization hit the request deadline before returning a run ID. Durable parsing/partitioning remains necessary. No successful publication is claimed.
- Three small XML sources that initially timed out validated on isolated retry after checking retained runs. Their first timeout cause is not yet proven.

## Checks and remaining acceptance

33 backend and 63 frontend regression tests passed, including graph utilities/search, Data Flow, run tracking, import routing and off-event-loop publication preparation. The production build passed with large-chunk warnings still present.

Live contextual search returned one canonical assembly match and, with neighbor expansion, two nodes and one relationship. Overview returned 750 sampled nodes across AP242 canonical, AP242 Domain Model, Teamcenter and PLMXML scopes; this is a bounded view, not a full graph census.

After the final managed backend restart, all ten service health endpoints (8010–8019) returned HTTP 200. All 23 run receipts remained published. Live assembly metrics matched its receipt (1,331 resources / 3,995 relationships). Final deployed backend/frontend patch hashes match the reviewed sources. Frontend build: `index-CzfAS4kG.js`. PostgreSQL and Neo4j servers were not stopped. Import history was verified in the browser with AP242 ontology status Published and assembly counts 326 / 339. Responsive layout, readable labels in dense graphs and friendly names for canonical document scopes still need further UI acceptance.

Pre-push verification also passed the full frontend suite (116 files / 641 tests), 90 backend unittest regressions across the changed test modules, backend compilation and Git whitespace checks. Two legacy AST-based workflow tests were updated to resolve the extracted modules correctly. Existing React test warnings and production chunk-size warnings remain; these checks do not certify the outstanding release gates below.

Remaining: verify cross-document business traversal and ontology alignment separately; durable oversized-file parsing/partitioning; browser rendering benchmarks; populated ArchiMate testing; coordinated PostgreSQL/artifact/Neo4j restore validation. The earlier offline Neo4j recovery drill predates this dataset.

## Retained component receipts

| Run ID | Graph scope | RDF resources | RDF relationships |
| --- | --- | ---: | ---: |
| `273360bf-8734-4bc1-880b-4005701a7251` | `ceim-ap242` | 1,331 | 3,995 |
| `da4217f8-bd3d-4b67-ae9e-4464387c2316` | `ceim-ap242-9259c11563baf60e49cb4254` | 28,623 | 88,864 |
| `e4225b17-166f-4af9-9347-b92dcac693ae` | `ceim-ap242-57f2d7330b2cbc24efef7cba` | 21,229 | 65,734 |
| `7d298d11-2319-4b4d-bcaf-2398fd6ce022` | `ceim-ap242-d077eb15f5af9e4f1da153e4` | 39,487 | 122,566 |
| `e0ced399-6d83-4075-b85d-a81f04269900` | `ceim-ap242-3d6627a7d45d16c0dac5ee40` | 20,334 | 63,076 |
| `0408d664-d17a-4445-b274-cd71fbc42b20` | `ceim-ap242-723872f63b2d281e1e6829e5` | 1,134 | 3,364 |
| `e872c82c-8642-4414-8a37-ff2a067ae787` | `ceim-ap242-509e1f15f9f0e796fcfb9d60` | 2,155 | 6,502 |
| `bed870a0-34b5-4ec4-81f1-98355630c5cc` | `ceim-ap242-4b644e5f79e0c60837951a42` | 36,862 | 114,520 |
| `7c040016-aa75-407f-acf4-6c9e7fe290be` | `ceim-ap242-b95f20523fe9a357766ce5ec` | 1,172 | 3,436 |
| `734094b1-9b9c-4d80-89bc-bdcf4a644302` | `ceim-ap242-df28baff2f202da780430a29` | 2,564 | 7,792 |
| `33f2a2e4-79ea-4b26-8418-e2102caaef3a` | `ceim-ap242-3c1578fdbd60c1811f395e9f` | 39,502 | 122,728 |
| `2e867856-2131-4a7f-8d91-4674dd98c510` | `ceim-ap242-486724bbc2a53f0ea5a6be5d` | 2,970 | 9,076 |
| `931809dc-4d05-4863-8302-02f4e72ff698` | `ceim-ap242-1cf3b759b9352d144f51226a` | 2,106 | 6,388 |
| `2147994c-3d45-4554-b7d5-b65c5c930bbb` | `ceim-ap242-c623223e68a3b3e941dbedf7` | 597 | 1,690 |
| `a63c4235-f9ba-4846-8246-f6a7da21bdeb` | `ceim-ap242-a98fd64110d965971b5edbe7` | 12,182 | 37,672 |
| `7b599d37-0625-41a0-844b-7726733662fd` | `ceim-ap242-49825b56230110e58b64810e` | 2,970 | 9,076 |
| `8c68fefc-7b4a-4a7e-8bac-a0cdd502d272` | `ceim-ap242-277a94844560f4c193625b39` | 2,106 | 6,388 |
| `05ea977a-5d2f-4fda-8b81-c18fd9d6312d` | `ceim-ap242-4908795773c0122ef40cc292` | 597 | 1,690 |
| `6580f3af-3ba8-4ad5-ba7d-e5733a180081` | `ceim-ap242-e4008046642c11f6da0b218a` | 12,079 | 37,349 |
| `c63ab172-cf4d-423d-9de9-5ac3600de7aa` | `ceim-ap242-8230b7f4cb04b6691b38bf06` | 39 | 77 |
| `5f46e9c7-dc9e-40ac-9954-d29bc34d207e` | `ceim-ap242-5bc99841d2a5ca2faf19472d` | 35 | 65 |
| `baa9b493-a245-4d48-9f96-88527e053e17` | `ceim-ap242-54db9dc916e4862cc4fb3759` | 39 | 77 |
| `32feac47-536f-4d0e-ba75-67ae9ddfff86` | `ceim-ap242-51e29a12795404740292cd17` | 35 | 65 |
