# Local clean-state acceptance — 2026-11-02

## Scope and authority
Local deployment D:\GenAI_Projects\Apps\PMem only. User explicitly approved clearing local application test data, preserving credentials/configuration/embedded foundation, and re-ingesting representative SPLM source files. Customer environment and external LLM execution are excluded.

## Confirmed results
- Failure/recovery backend cohort: 68 passed.
- Frontend API/session cohort: 14 passed; renewal/read/polling/run tracking/Admin cohort: 56 passed.
- Real isolated PostgreSQL materialization, rollback, unit and business-mart tests: 7 passed.
- Real owned worker kill/restart: 1 passed. Zero partial datasets after crash; replacement attempt 2 completed exactly one dataset; disposable schema removed.
- Eighteen application routes opened without an error boundary or captured console error. This is smoke coverage, not completion of all business scenarios.
- SPLM source inventory: 292 supported files, 224 distinct contents, 43 duplicate groups. No source files deleted. Apple __MACOSX/._ metadata must not be used as XMI test inputs.
- Confirmed Windows defect: isolated maintenance guard rejected its own virtual-environment launcher parent. Fixed by exempting only the direct parent with the identical isolated uvicorn invocation under the application root. Unrelated Python workers still block. Reset regression cohort: 20 passed.
- Admin UI reset receipt vanilla-65088a86913e4b5199b8cbb3fd758e95: graph, PostgreSQL and owned-file phases completed. Credentials and embedded foundation retained. No PostgreSQL schema drop.

## Endurance result — not a clean pass
600.5 seconds, concurrency 12; 21,765 successful reads, 3 client ReadTimeout exceptions on the pipeline run-list endpoint at the 10-second client deadline. Median successful latency 32 ms, p95 140 ms, max 1,359 ms. Renewal 200/200; revoked session 401; independent session 200; no QoS admission rejection. The three request IDs are retained in outputs/local-read-endurance-2026-11-02.json. Their cause is not established; do not label this a green endurance certificate.

## Evidence
Local outputs (uncommitted): failure-endurance-regressions-final.log; session-failure-regressions-final.log; session-concurrency-final.log; worker-crash-acceptance-20261102.log; data-load-acceptance-20261102.log; reset-identity-tests-20261102.log; splm-test-inventory.json; splm-duplicate-groups.json; local-read-endurance-2026-11-02.json; admin-reset-completed-20261102.png.

## Fresh-data UI acceptance
- Normal managed startup completed after reset: ten APIs, three workers, migrations 1–17 and baseline jobs/assets verified. Credentials retained.
- Imported three PLMXML instance files: requirements (22 entities / 39 relationships), mBOM (704 / 1,324), manufacturing process (1,305 / 2,256). Reviewed and loaded through the UI using paritosh as test approver.
- Three selected PLMXML XSDs formed one schema-set row and one ontology. Published PLMXML projection: 6,529 resources / 19,993 relationships.
- AP242 DomainModel and SugarPlantMBSE XMI reviewed and published: 70,052 / 197,372 and 883 / 3,863 respectively. Independent XSD root namespaces were rejected with actionable companion guidance, preserving source meaning.
- Where Used failed to find Motor Cover Machined because the route supplied a limited overview snapshot. Fixed the route to perform bounded business-object search, cancel stale responses and traverse the selected identity. Same-name identities remain separate. Live verification found four candidates and traversed the selected record's references.
- Recommendations exercised all three direct-graph tabs. Missing eligible impact/process paths remain explicitly unestablished; references are not claimed to be physical BOM or causal process links. Similar Parts returned ten evidence-ranked candidates with bounded-coverage disclosure.
- Created and approved graph-source-snapshot and rdf-semantic-materialize test definitions; both worker runs completed. Snapshot retained 10,048 RDF triples; semantic preparation exposed typed MBSE records in Data Products.
- Replay accepted and completed run 7d203500-237c-5456-92fd-09779a5789ce, retaining replay lineage to 7d18784c-cf0d-4f97-939a-0098edc390f8. This does not publish a product.
- Found missing-reviewer approval enabled in Data Flow. Approve now requires reviewer setup; setup navigation and defensive pre-request validation tested (22 Data Flow tests passed).

## Browser and scoped-metrics corrections
- Graph toolbar layout produced CLS 0.249 when asynchronous summary data arrived. Reserved a bounded, scrollable summary row and fixed selector width. Measured retest: CLS 0.0932, INP 56 ms, LCP 800 ms. These are local measurements, not customer field certification.
- Optional measure_heap=1 (only with measure_ui=1) samples Chromium heap every 15 seconds, bounded to 40 samples, and clears the timer on departure. Unsupported browsers report unsupported. Observed collection/reclamation does not prove absence of all leaks.
- Home selected PLMXML was verified both by authenticated API and browser: 6,529 resources / 19,993 relationships. The reported zero state was not reproduced after publication. Zero resources no longer incorrectly asserts publication never happened; guidance distinguishes registry registration from publication. Focus refresh picks up changes made in another tab.
- OWL browser now offers Class list and Class hierarchy as alternative views, one grid at a time. Anonymous superclass expressions are counted rather than repeated as identical parent labels. Duplicate edges collapse by identity; distinct named parents sharing a label retain their identifiers. Underlying axioms and ontology artifacts are unchanged.
- Full frontend regression before the final Home/OWL changes: 153 files / 932 tests passed. Final Home/OWL cohort: 12 passed; production frontend build passed. Import test was corrected to await asynchronous digest completion, without changing production parsing.
- Post-ingest read retest: 4,392 successful requests / zero failures over 120.4 seconds at concurrency 12, p95 125 ms. This does not explain the three earlier timeouts.

## Remaining limits
- Three earlier run-list read timeouts remain unexplained. Longer, controlled endurance and customer-environment acceptance remain open.
- External LLM execution was excluded by instruction; Companion/agent model output quality is not certified by these tests. The later follow-up below exercised mapping and structural union publication; full OWL-DL union checking remains unknown because referenced imports are unresolved.
- A representative STEP file was later ingested and published (see follow-up); every duplicate source file was not exercised. Route smoke checks are not full business acceptance.
- No customer-approved KPI formulas, effectivity baseline or governed analytics product was invented or published by this test.

## Follow-up acceptance and fixes
- A further 600.7-second mixed local run (concurrency 12, while browser import/merge tests ran) completed 21,936 reads with zero failures. Median 32 ms, p95 125 ms, max 4,141 ms; renewals both 200, revoked session 401, independent session 200. The original three timeouts remain unexplained; their retained evidence is not overwritten.
- Slow successful requests (5 seconds or more) now log at WARNING, so default warning-level deployments retain correlation, route template, status and duration. No raw URLs, payloads or credentials are logged. Slow-read and QoS regression tests passed.
- Actual instance workflow run run-61698aa2-7913-48a5-94db-1282e7400f2d published seven mappings and held fifty. Receipt bridge-publication-dec2a897707e442a8bb8a203ee19e31f. Reload and source/target reselection recovered the same receipt without resubmission.
- STEP source 000700_A;1-Rotor Shaft Key.stp validated via Import into Data Flow run f652443c-c930-4524-a646-a9cc06acb749 (292 entities / 280 relationships). The UI correctly distinguishes validation from pending graph publication.
- Live PLMXML/MBSE union preview exposed a confirmed typed-literal identity defect: explicit conflict checking collapsed typed literals to lexical text, falsely conflating string/decimal "1" and string/boolean "true". Preserve RDF literal datatype/language and blank-node identities. Tests still block genuine same-term contradictions.
- Imported-standard default editorial SHACL warnings (missing owl:versionInfo) incorrectly blocked the otherwise valid union. Default editorial warnings are now advisory only for imported_standard, retained in the report; enterprise_curated and custom semantic shapes remain strict. Validation fingerprints include the governance policy hash so policy changes invalidate old evidence.
- A held saved plan now explains its pending/failed validation state rather than instructing users to generate an already-existing plan.
- Expanded backend merge/bridge/logging/QoS regression cohort: 141 passed and 35 subtests passed. Focused frontend merge/selection cohort: 18 passed. The full frontend suite found one test still expecting simultaneous class grids; its expectation was migrated to switch views while preserving the 805-class inventory/800-row hierarchy checks, and the full rerun is recorded separately.

## Verified follow-up completion
- Full frontend rerun: 153 files / 934 tests passed. Subsequent receipt-recovery and guidance cohort: 21 passed. Production builds succeeded.
- Managed backend restart completed endpoint/schema/credential checks; frontend correctly rejected stale input hashes until rebuilt, then started with matching receipt. Post-restart temporary read-only browser sessions passed all ten services, ontology health and catalog reads. No LLM process started.
- STEP Data Flow run f652443c-c930-4524-a646-a9cc06acb749 published under explicit local reviewer settings; retained scope ceim-ap242-a603cdec7ade091deeee91a2. Graph Explorer contextual search for Rotor Shaft Key returned a three-node recorded context after completion.
- Corrected live PLMXML/MBSE union: zero explicit/inferred RDF conflicts; both SHACL profiles conform; editorial warnings retained. Requested full OWL-DL remained unknown because OSLC, DCTERMS, SKOS and SHACL imports were unresolved. No consistency proof is claimed.
- Explicit structural-only review then passed Steward governance (imported-standard profile, no quarantined identities). Reviewed union with zero identity consolidations published as merged_1793596319926_627ca19b92d94902, 7,403 resources / 23,855 relationships. Source ontologies remain separate. Publication digest c935e6eb0e9ff19e28152779c80b1aed294f1f6862de5c295e65146d7bd9a85b verified independently against current graph receipt.
- Found and fixed a further resume defect: browser reload restored the preview but omitted its applied-result publication state. Resume now reads the retained applied result, verifies the current ontology publication identity/receipt, and restores published/running status without calling apply. Mismatched scope, stale receipts and invalid counts are rejected; late responses are fenced by the existing generation guard.
- Local screenshots and detailed test logs remain outside Git. Customer deployment, LLM output acceptance and unavailable offline OWL-DL imports are not certified by the above results.
