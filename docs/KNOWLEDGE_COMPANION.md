# Knowledge Companion: answers and troubleshooting

Open **Chat** in the application header. Ask a specific question such as `What AP242 to QIF mappings are available?` or search for a class, property or instance name.

## What supplies an answer

- Graph questions retrieve bounded resources from the Graph service. An active ontology limits that search. Descriptions and definitions are included when the retained resource supplies them.
- Mapping/merge questions also query the Ontology service for the latest six matching saved reviews. Source-name terms and the selected ontology scope filter the records before the limit. Large Turtle artifacts, credentials and complete preview records are never returned to the Companion.
- Saved reviews explain proposal counts, ambiguity, selected consolidations, retained validation and missing source registrations. A saved union with zero selected pairs is not an approved semantic alignment. Historical records do not establish current Neo4j publication.
- The answer cites retained evidence identifiers. Expand **Evidence** to see the sources. The Companion does not approve mappings, publish graphs or modify data.

## Optional language-model summaries

Root `.env.local` controls `COMPANION_LLM_ENABLED` and `USE_LLM=ollama|openai|mistral|aoi`. Configure the selected provider's model and credentials using the installation guide, then restart the services. Enabling this flag does not install models or supply provider quota.

When enabled, the model summarizes retrieved evidence and must supply valid evidence citations. The UI shows its actual provider and generation status. Model failure preserves the deterministic retrieval answer. Invalid optional model settings must not prevent retrieval. With no matching evidence the Companion gives recovery guidance rather than inventing an answer. General knowledge, exhaustive ontology alignment and arbitrary analytical questions are not guaranteed by this retrieval interface.

## Diagnose an unanswered question

1. Confirm application access is connected. For `401`/`403`, revalidate access and inspect service authorization configuration; do not paste keys into chat or logs.
2. For graph questions, select the correct ontology and check its publication receipt in Ontology Junction. Source files on disk do not make their resources searchable in Neo4j.
3. For mapping questions, the read-only route is `GET /api/v1/ontologies/companion/mapping-evidence` on the configured Ontology service. It requires graph-read access and returns only a bounded projection. A failed history read is reported separately from an empty result.
4. `Model generation: disabled` means retrieval is enabled but model summaries are disabled. `rate_limited` with HTTP `429` requires checking the selected provider's quota, billing or request limits. Authentication, timeout and invalid-response failures are separate statuses.
5. `COMPANION_RETRIEVAL_TIMEOUT_SECONDS` defaults to 15 seconds per owning service, bounded to 120 seconds. The overall chat allowance includes up to five retrieval stages, the configured generation budget and five seconds of overhead. Existing response-size and prompt limits still apply.
6. Internal agent run IDs, saved-result IDs and raw model prompts remain available to diagnostics and are not rendered in conversation messages. Use agentic service logs to investigate failures. A response that stops before its completion marker is incomplete and is not presented as a successful answer.

## Code and design review: 2026-10-27

The review follows the active browser-to-service path, rather than treating legacy GraphRAG/vector tests as proof of Companion behavior. It covers `App.js`, `Chatbot.js`, graph/ontology selection owners, `chat_request.py`, `router.py`, `context_scope.py`, `companion_memory.py`, `companion.py`, `companion_context.py`, `plm_questions.py`, `plm_answers.py`, `business_context.py`, `vocabulary_evidence.py`, `business_answers.py`, `search_evidence.py`, `local_llm.py`, prompt validation and stream parsing. The Companion performs read operations; mandatory turn retention and optional memory enrichment are separate writes.

### Confirmed defects corrected

| Severity | Corrected source location | Root cause and reproduction | Correction / expected behavior |
|---|---|---|---|
| P1 | `frontend/src/Components/Chatbot.js:40` | A graph prefix was reused as an immutable ontology ID. Open Chat with a prefix-only graph scope. | Keep ontology ID and prefix separate in the browser request. |
| P1 | `frontend/src/App.js:242` | Global chat reused the last Graph Explorer dataset on unrelated pages; Ontology Junction did not provide its own selected ID. | Limit shared graph data to its owners; pass the selected ontology through an explicit callback and clear it on leaving. |
| P1 | `backend/agentic_service/router.py:333` | The selected business node was omitted from API context and history scope. Select two same-name objects or change the selected object during a conversation. | Forward a bounded node ID, reload its evidence on the server and bind history/context envelopes to that ID. Selection never grants access. |
| P1 | `backend/depo_platform/plm_questions.py:4` | Named PMI/product requests did not bind the requested object. Ask `Does Housing have PMI?` or `Show product details for Housing.` | Route common supported phrases and bind the subject or selected identity in parameterized graph queries. |
| P1 | `backend/agentic_service/companion_context.py:128` | Business response validation allowed an answer for a different intent or rows without business names and assessed links. | Reject mismatched intent, missing names, missing requirement paths, wrong selected identities and unassessed PMI association states. |
| P2 | `backend/agentic_service/companion_memory.py:6` | Follow-ups concatenated an old full question into a new subject filter. | Resolve explicit pronouns to the prior named subject within the same ontology, page and node scope. |
| P2 | `backend/graph_service/search_evidence.py:4` | Deterministic excerpts and page records could expose XML/JSON; definitions and engineering values were omitted. | Render business text, retain safe descriptions/definitions/values/units and keep credentials out of the projection. |
| P2 | `backend/agentic_service/companion.py:250` | Context expansion was restricted to the Graph page, and recorded relationships were reduced to a count. | Reuse bounded context reads on supported engineering pages and show named endpoint/relationship rows. |
| P2 | `backend/graph_service/vocabulary_evidence.py:4` | Generic contextual edges did not use scoped vocabulary labels. | Resolve retained predicate labels within the selected scope. Conflicting labels remain unresolved; labels do not prove ownership or equivalence. |
| P1 | `backend/agentic_service/companion.py:277` | Optional model output replaced typed fact tables and their uncertainty, even for empty business results. | Retain deterministic typed facts and uncertainty; append model interpretation separately. Do not call the model to invent an answer when typed business rows are empty. |
| P1 | `backend/agentic_service/router.py:379` | Answer text was emitted before mandatory turn retention; inject a PostgreSQL save failure while streaming. | Buffer the validated answer until retention succeeds; a failed save emits no answer text. |

### Execution and failure boundaries

1. The UI sends only bounded scope identifiers, a validated page hint and the question. Browser graph labels are not evidence. Changing source, page, node or principal cancels stale reads and separates conversation state.
2. The service establishes the principal/session, retrieves owned history, then selects typed PLM reads, retained mapping reviews, indexed excerpts or bounded business graph context. Each read forwards the caller's read bearer and destination-specific gateway headers.
3. Business-instance reads retain names, identities, sources, assessed PMI association states or recorded requirement paths. Schema terms, filenames and source references are not substitutes for instance ownership.
4. The response preserves bounded coverage and distinguishes unavailable retrieval from no returned evidence. Generic results show recorded context, not certified impact or compliance.
5. Optional generation receives bounded, protected evidence. XML/JSON output and invalid citations are rejected before buffered output is delivered. Valid citation identifiers alone are not a semantic entailment proof.
6. Required PostgreSQL turn retention precedes optional graph memory enrichment and answer emission. Interrupted streams and retention failures are not advertised as successful completed answers. Storage-failure injection verifies that no answer text is emitted before the required save.

### Acceptance checks and remaining limits

Regression fixtures cover question variants, prefix-only scope, same-name/selected-object context, cross-scope rejection, stale responses, session renewal, pronoun follow-ups, vocabulary conflicts, business text/units, empty evidence, rate limits, provider authentication failures, invalid model output and interrupted streams. Production build and installation package checks complement those tests; they do not replace customer-data acceptance.

`backend/tests/test_companion_contextual_regressions.py` includes an HTTP integration path through `/api/v1/chat`, the real request model, scoped retrieval, response validation, business formatting and turn retention. External services/storage are fixtures. Both a matching selected identity and a different same-name identity are exercised; the latter never becomes an answerable business fact.

Final local verification: 184 backend regression cases passed, including the storage/stream ordering fault injection and adjacent OSLC/JSON-LD contracts; 85 focused UI cases passed. Production frontend build, exact build-input receipt comparison (343 inputs), backend release-coherence check, installation package validation and `git diff --check` passed. These are overlapping focused suites, not a whole-application coverage percentage. No live model calls or customer database mutations were performed. Changes remain local until committed and deployed.

Live LLM execution remains excluded at the user's request. Customer graph completeness, cross-ontology published links, provider availability and model interpretation quality therefore remain unverified. Typed requirements/PMI/product reads are bounded capabilities, not a general analytical query planner. The active excerpt path is lexical/full-text; legacy vector-chain tests do not establish semantic/vector retrieval for this interface. With an explicit ontology scope, traversal stays in that scope. No percentage of passing tests certifies absence of every defect or guarantees arbitrary natural-language answers.

Before customer sign-off, run the same named-object questions against that deployment with generation disabled, verify the returned names/values/paths against source records, test two same-name objects and source changes, then separately qualify the configured model when it becomes available.

## Local live acceptance: 2026-10-28

Local services and browser access were started with both Companion and ontology model generation disabled. All ten service-session checks and protected ontology reads passed without rotating application credentials. This is local acceptance, not verification of the customer's deployment.

The live question `What requirements are associated with induction motor?`, restart testing and Recommendations journeys exposed five additional defects:

| Severity | Source | Reproduction and root cause | Correction and measured verification |
|---|---|---|---|
| P2 | `backend/graph_service/plm_answers.py`, `backend/agentic_service/business_answers.py` | Alternate paths to the same requirement consumed the 20-row answer allowance, repeating the same business details. | Group by immutable subject/requirement identities before limiting; retain a shortest recorded path and its path count. The live read returned three distinct pairs covering two requirement identities in 1.3 seconds. Same-name records with different identities remain separate. |
| P2 | `backend/Services/ontology_upload_manager.py` | Opening Home discovered internal CEIM records as many apparent ontology registrations. Discovery accepted every node with a prefix. Group counting also tested each neighbor against a collected node list. | Require schema/class/property evidence for graph-only discovery and count directed internal relationships without quadratic list membership. Live graph discovery returned two schema groups in 1.5 seconds. Registered metadata remains authoritative. |
| P2 | `backend/graph_service/neo4j_publisher.py` | Home graph-profile request timed out at 20 seconds. Type counts repeated correlated relationship searches five times per resource. | Expand asserted type edges once per resource and aggregate distinct declared type IRIs. Complete local counts returned in 6.7 seconds: 306,402 resources, 7,274 classes and 928,541 relationships. These timings are observations on this dataset, not latency guarantees. |
| P2 | `frontend/src/app/AppShell.js` | Reloading a working session left the header saying access was unverified until Revalidate was clicked. | Verify stored access on mount and session replacement, cancel superseded checks, and avoid redirecting the user during a background rejection. Four focused UI suites passed 52 tests, including replacement/rejection races. |
| P2 | `frontend/src/features/recommendations/AIInsightBanner.js` | Run Process Context for a scoped bearing. The summary displayed zero instances/related processes while the detail panel correctly reported those categories as not assessed. | Preserve assessment state in the banner; only sum categories actually assessed and identify a direct-only count explicitly. A regression exercises both unassessed categories and a genuinely assessed zero. |

The focused follow-up regression suite passed 75 tests. The live read evidence is retained separately from mocked unit coverage. Installation packaging must include the entire tested baseline: a change-only overlay initially missed the already-committed `frontend/src/services/recommendationScope.js` dependency, and the production build caught it before services started. Source hashes and the backend fingerprint were then checked against the complete baseline. Configuration backups use Windows DPAPI for the current account; database contents, uploads and retained workflow history were preserved.

## Historical verification on 2026-10-22

The live question `What AP242 to QIF mappings are available?` originally returned no evidence even though five retained PostgreSQL reviews existed. The Companion only searched Neo4j. The corrected read projection found all five records; the latest recorded 198 proposals, 182 ambiguous and zero selected consolidations. Both source registrations were absent. This verifies historical review retrieval, not current graph publication or a new mapping approval. Live browser acceptance after deploying the correction must verify the same distinction.

## Consistency and accuracy audit

See the [GraphRAG audit and acceptance sequence](audits/knowledge-companion-graphrag-2026-10-22.md). Follow-ups and restored history are scoped to the selected ontology. Saved answers are marked as not refreshed. Bounded selections disclose their limits. Model summaries require paragraph/list-item citations, but citation membership does not prove semantic entailment. Domain accuracy requires representative end-user questions and independent evidence review.

The Companion also accepts a validated page hint for existing catalog, product and job listings, and unscoped Semantica business-context search. See [Shared semantic services and ontology agents](SEMANTIC_AGENT_ARCHITECTURE.md) for supported pages, exact-scope restrictions and retained compatibility code.


## Sample prompts

Home offers evidence requests across products/assemblies, requirements, MBSE, quality/measurement, AP242–QIF mapping reviews and source provenance. Samples ask what is retained and what is missing; they do not assert that example data has been loaded. The sample endpoint accepts the current `page` and supplies focused examples for Catalog, Data Products, Data Flow, Ontology Junction, Modeling, ReqIF, QIF, Where Used and Data Quality. Other pages use the broad Home set. Data-product questions about analytics schemas, dimensions or KPIs request documentation evidence; they do not imply those assets were generated automatically.

The frontend reloads samples on page changes, ignores cancelled responses and retains broad engineering prompts if the sample endpoint is unavailable or malformed. Selecting a sample submits a read-only Companion question using the existing page/source scope and access. Samples neither authorize writes nor work around provider rate limits.
