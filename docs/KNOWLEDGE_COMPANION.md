# Knowledge Companion: answers and troubleshooting

Open **Chat** in the application header. Ask a specific question such as `What AP242 to QIF mappings are available?` or search for a class, property or instance name.

## What supplies an answer

- Graph questions retrieve bounded resources from the Graph service. An active ontology limits that search. Descriptions and definitions are included when the retained resource supplies them.
- Mapping/merge questions also query the Ontology service for the latest six matching saved reviews. Source-name terms and the selected ontology scope filter the records before the limit. Large Turtle artifacts, credentials and complete preview records are never returned to the Companion.
- Saved reviews explain proposal counts, ambiguity, selected consolidations, retained validation and missing source registrations. A saved union with zero selected pairs is not an approved semantic alignment. Historical records do not establish current Neo4j publication.
- The answer cites retained evidence identifiers. Expand **Evidence** to see the sources. The Companion does not approve mappings, publish graphs or modify data.

## Optional language-model summaries

Root `.env.local` controls `COMPANION_LLM_ENABLED` and `USE_LLM=ollama|openai|mistral`. Configure the selected provider's model and credentials using the installation guide, then restart the services. Enabling this flag does not install models or supply provider quota.

When enabled, the model summarizes retrieved evidence and must supply valid evidence citations. The UI shows its actual provider and generation status. Model failure preserves the deterministic retrieval answer. Invalid optional model settings must not prevent retrieval. With no matching evidence the Companion gives recovery guidance rather than inventing an answer. General knowledge, exhaustive ontology alignment and arbitrary analytical questions are not guaranteed by this retrieval interface.

## Diagnose an unanswered question

1. Confirm application access is connected. For `401`/`403`, revalidate access and inspect service authorization configuration; do not paste keys into chat or logs.
2. For graph questions, select the correct ontology and check its publication receipt in Ontology Junction. Source files on disk do not make their resources searchable in Neo4j.
3. For mapping questions, the read-only route is `GET /api/v1/ontologies/companion/mapping-evidence` on the configured Ontology service. It requires graph-read access and returns only a bounded projection. A failed history read is reported separately from an empty result.
4. `Model generation: disabled` means retrieval is enabled but model summaries are disabled. `rate_limited` with HTTP `429` requires checking the selected provider's quota, billing or request limits. Authentication, timeout and invalid-response failures are separate statuses.
5. `COMPANION_RETRIEVAL_TIMEOUT_SECONDS` defaults to 15 seconds per owning service, bounded to 120 seconds. The overall chat allowance includes up to three retrieval stages, the configured generation budget and five seconds of overhead. Existing response-size and prompt limits still apply.
6. Internal agent run IDs, saved-result IDs and raw model prompts remain available to diagnostics and are not rendered in conversation messages. Use agentic service logs to investigate failures. A response that stops before its completion marker is incomplete and is not presented as a successful answer.

## Verification on 2026-10-22

The live question `What AP242 to QIF mappings are available?` originally returned no evidence even though five retained PostgreSQL reviews existed. The Companion only searched Neo4j. The corrected read projection found all five records; the latest recorded 198 proposals, 182 ambiguous and zero selected consolidations. Both source registrations were absent. This verifies historical review retrieval, not current graph publication or a new mapping approval. Live browser acceptance after deploying the correction must verify the same distinction.

## Consistency and accuracy audit

See the [GraphRAG audit and acceptance sequence](audits/knowledge-companion-graphrag-2026-10-22.md). Follow-ups and restored history are scoped to the selected ontology. Saved answers are marked as not refreshed. Bounded selections disclose their limits. Model summaries require paragraph/list-item citations, but citation membership does not prove semantic entailment. Domain accuracy requires representative end-user questions and independent evidence review.

The Companion also accepts a validated page hint for existing catalog, product and job listings, and unscoped Semantica business-context search. See [Shared semantic services and ontology agents](SEMANTIC_AGENT_ARCHITECTURE.md) for supported pages, exact-scope restrictions and retained compatibility code.


## Sample prompts

Home offers evidence requests across products/assemblies, requirements, MBSE, quality/measurement, AP242–QIF mapping reviews and source provenance. Samples ask what is retained and what is missing; they do not assert that example data has been loaded. The sample endpoint accepts the current `page` and supplies focused examples for Catalog, Data Products, Data Flow, Ontology Junction, Modeling, ReqIF, QIF, Where Used and Data Quality. Other pages use the broad Home set. Data-product questions about analytics schemas, dimensions or KPIs request documentation evidence; they do not imply those assets were generated automatically.

The frontend reloads samples on page changes, ignores cancelled responses and retains broad engineering prompts if the sample endpoint is unavailable or malformed. Selecting a sample submits a read-only Companion question using the existing page/source scope and access. Samples neither authorize writes nor work around provider rate limits.
