# SysML viewer audit — 2026-11-03

Scope: current uncommitted Modeling viewer changes, retained XMI reader, contextual graph identity handoff, and deployed localhost UI. This is an audit; application code was not modified. No LLM call, publication, credential change or database write was performed.

## Verdict

The named-view reader and basic SysML rendering work for SugarPlantMBSE, but the viewer is not ready to claim complete SysML fidelity or complete contextual engineering coverage. Eight defects/gaps below require correction. Successful startup and the existing tests did not cover these cases.

## Executed verification

- Existing frontend suite: 10 passed across ModelWorkbenchPage, SysMLDiagram and GraphInvestigation.
- Existing backend suite: 4 passed in test_xmi_diagram_views.py.
- Deployed browser: 15 named views, 437 source elements; requirements, use cases, parametric view and empty exported view tested. Element selection populated Inspector; Companion displayed the selected element context. No captured browser console errors in the inspected buffer.
- Adversarial API experiment: malformed retained XML (`<broken>`) through the real route with read authentication overridden in a local test app returned HTTP 500. No running service or retained customer artifact was altered.
- Browser reproduction: use-case view + search Motor Capacity reports 1 match, 0 visible elements and a false missing-export explanation. A nonmatching search after selecting Deliver RPM & Power leaves Companion/agent selection active on the hidden element.
- Evidence screenshot: outputs/sysml-audit-search.png (workspace outputs directory, outside this repository).

## Defect register

### S01 — P1: Inspector silently omits engineering relationships

Confirmed by code: frontend/src/pages/ModelWorkbenchPage.js:461–472. Inspector uses visibleLinks and slices to 12 without a truncation indicator. Reproduce by selecting a requirement with more than 12 relationships, or selecting an element then filtering out a connected endpoint. Impact: an engineer cannot distinguish incomplete presentation from absence of traceability. Fix: show total source connections separately from current-view connections, with pagination and explicit scope/truncation. Regression: a 20-edge node exposes all 20 through paging; filtering cannot imply whole-model absence.

### S02 — P1: Graph identity enrichment gates the independent XMI viewer

Confirmed implementation dependency: ModelWorkbenchPage.js:375–388. setDataset waits for a second graph request; matching scans up to 1,600 projection nodes for every XMI node and silently leaves unmatched elements without agent identity. Reproduce with delayed graph service after a successful diagrams response; separately use a model whose projection exceeds the 1,600-node slice. Impact: slow graph service delays otherwise usable diagrams; valid published elements outside the slice cannot use contextual actions. Fix: display the XMI immediately, enrich progressively with generation guards, and resolve exact scoped source identities in batches instead of a bounded overview scan. Slow-network latency and large-model manifestation remain to be measured; the blocking sequence and fixed bound are confirmed in code.

### S03 — P2: Search result counts and empty-state explanation disagree

Confirmed in deployed browser. ModelWorkbenchPage.js:566 counts all model matches while visibleNodes restricts the canvas to the active view. SysMLDiagram.js:54 treats any filtered empty graph as missing exported members. Reproduce: choose Sugar Production Plant Use Cases; search Motor Capacity. Actual: 1 Matches, 0 visible, missing-export message. Fix: distinguish current-view results, model-wide results, filter-empty and source-empty states; offer navigation to matching views. Regression must cover a match outside the active view.

### S04 — P2: Hidden selection remains actionable after filtering

Confirmed in deployed browser. ModelWorkbenchPage.js:559 changes query without clearing or marking the selected context as hidden. Reproduce: click Deliver RPM & Power; search no-matching-element-audit. Canvas is empty but Inspector and enabled Companion/agent actions still reference that element. Impact: investigation context is easy to misunderstand. Fix: clear selection when excluded or explicitly retain it with an unmistakable hidden-selection banner and reveal action. Regression: selected context must match the visible/explicitly retained selection after search.

### S05 — P2: Malformed or missing source artifacts have incomplete API errors

Malformed XML HTTP 500 confirmed by executed route experiment. xmi_diagrams.py:17 raises XMLSyntaxError; modeling_router.py:101–108 catches only LookupError and ValueError. Missing artifact/read failures are an additional code-path risk, not a reproduced production outage. Fix: translate known parsing/artifact absence/integrity failures into sanitized structured 422/404/409 errors with request IDs; preserve server exception details in logs. Regression: malformed XML and removed/integrity-failed artifact tests, without leaking paths or secrets.

### S06 — P2: Missing exported members are excluded from validation

Confirmed by code. xmi_diagrams.py:72 returns unresolvedIds, but ModelWorkbenchPage.js:485–492 checks only returned nodes/links and missing labels. Source endpoints omitted earlier cannot appear broken at this stage. Impact: a view can show No viewer-level issues found while references are unresolved. Fix: include unresolved references, unsupported view types and incomplete source evidence in scoped viewer diagnostics; keep these separate from OWL-DL consistency. Regression: the existing missing-member fixture must surface an incomplete-view warning in the UI.

### S07 — P2: Requirement compartments prioritize technical IDs and flatten stereotypes

Confirmed in source and observed requirements UI. SysMLDiagram.js:8,15: case-insensitive Id whitelist also matches internal id; insertion order plus slice(0,5) lets internal IDs occupy slots before business content. All requirement subtypes render as requirement. xmi_diagrams.py:41 also flattens profile attributes from multiple applications into last-write-wins keys, although profile_applications preserves originals. Fix: ordered business fields (requirement number, text, units/constraints where present), technical identity in Inspector, preserve specific source stereotypes and profile ownership. Regression: multiple profiles and reordered input properties must not change displayed business text or meaning.

### S08 — P2: Named table/matrix views are generic substitutes without sufficient empty-state guidance

Confirmed implementation limitation: SysMLDiagram.js:46 renders the same element/outgoing-edge table for both requirement tables and dependency matrices. No-member matrices produce an empty tbody. The source disclaimer is useful, but this is not the vendor-defined matrix. Fix: label these as semantic fallback views, show unavailable row/column configuration explicitly and provide a clear empty state; reconstruct matrix axes only where source evidence supports them. Regression: empty matrix, requirement text table, and unsupported vendor configuration.

## Other risks and limits

- Fixed three-column generated positioning (SysMLDiagram.js:32) does not minimize crossings or reproduce original geometry. Actual use-case screenshot shows crowded connector routes. Requires layout/label QA before executive demonstrations; missing binary layout is a source limitation, not a parser failure.
- Mode/source/view live only in component state (ModelWorkbenchPage.js:333–348): refresh/back-forward cannot restore the selected named view through the URL. Confirmed design gap; no claim of persisted selection.
- Cache is bounded by eight artifacts, not bytes (xmi_diagrams.py:101). No load/concurrency benchmark was performed. Do not infer acceptable memory usage from the 25 MB file bound.
- The XMI reader enforces no-network parsing, rejects DTDs, uses immutable source artifacts and has size/member limits. Existing auth regression rejects unauthenticated reads. This is not a full security certification.
- Original MagicDraw binary drawing streams are absent. Activity/sequence/state/IBD notation coverage was not established by this sample. No complete SysML authoring claim is justified.
- Live LLM execution, agent tool completion, memory recall across conversations, multi-tab credential rotation and customer upgrade acceptance were not tested in this audit because the model remains disabled and this pass focused on the viewer.

## Correction order

1. Complete relationship visibility and progressive exact identity resolution (S01, S02).
2. Correct search/selection and diagnostic contracts (S03–S06).
3. Business-first compartments and honest matrix fallback (S07, S08).
4. Add regression cases above, rerun suites, then repeat deployed UI and delayed-service acceptance.

No application fixes, restart or Git commit were made in this audit pass.

## Remediation follow-up

The subsequent authorized implementation addresses S01–S08:

- Inspector pages all retained source-model connections and labels current-view counts separately.
- XMI loads independently. Element selection resolves a unique ontology-scoped graph identity and up to 100 adjacent associations through the read-authorized xmi-context endpoint. This replaces the 1,600-node overview lookup. Pending, failed and ambiguous contexts cannot supply imported-model agent identities.
- Search changes clear selected context; model-wide match counts identify current-view coverage, and filtered-empty states no longer imply absent exports.
- Malformed XML, absent source, source-file availability and graph-read failures have explicit 422/404/409/503 responses. Server graph-read exceptions retain diagnostic logging.
- Unresolved exported references and generic matrix/table fallbacks appear in viewer diagnostics.
- Requirement compartments prioritize source requirement identifiers/text, preserve specific stereotypes, omit internal IDs and retain primary profile values without flattening away the full profile applications.
- Empty tables/matrices identify unavailable exported rows/columns and declare their semantic fallback scope.

Added Engineering traceability in Inspector: safe recorded HTTP(S) references grouped by PLM, CAD, simulation and other source references, with supporting property/relationship evidence. No source URLs or associations are fabricated. Schema/vocabulary graph references are separated from engineering-file evidence. Source systems retain their own access controls; no revision compatibility or approval is inferred.

Verification: 15 frontend tests passed; 9 backend tests passed; production build passed. The normal local stop/build/start sequence completed, including PostgreSQL schema, graph indexes, embedded foundation, credential and endpoint checks. The backend read against the real SugarPlant graph resolved Deliver RPM & Power and three adjacent references. Browser selection enabled Companion after this lookup. Those three references are schema/vocabulary references; this sample element has no recorded PLM, CAD or simulation web URL. Link-present cases use controlled regression fixtures; no external PLM/CAD destination access was asserted.

The earlier Other risks and limits remain limitations, not claims of complete SysML coverage, persisted URL state, memory benchmarking or live LLM acceptance. No database migration, customer publication, LLM enablement, commit or push was performed by this remediation.

Final deployed browser acceptance used frontend bundle index-BLPGy-OR.js. Repeated Motor Capacity cross-view search now reports 1 model match (0 in this view) with a filter explanation; a nonmatching filter clears the Inspector and agent selection. Motor Speccifications exposes 32 retained source-model relationships across three pages, with page 2 verified. Requirement number/text and specific requirement stereotypes were observed on the canvas. Final screenshot: C:/Users/Admin/Documents/Codex/2026-10-18/in/outputs/sysml-traceability-fixed.png. No xmi-context browser error was captured during the final check.
