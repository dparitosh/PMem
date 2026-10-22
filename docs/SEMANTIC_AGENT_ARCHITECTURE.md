# Shared semantic services and ontology agents

## Agent responsibilities in Ontology Junction and Semantic Bridge

Both ontology merging and instance linking use the existing `ontology-governor` and `ontology-steward`. No additional replacement agents are introduced by this refactor.

| Operation | Existing agent | Responsibility |
|---|---|---|
| Prepare a merge | Governor | Run `ontology.merge.preview` and retain exact source versions, changes and evidence |
| Review the merge | Steward | Run `ontology.merge.evaluate` on that saved preview; explain policy findings and validation limits |
| Publish an approved merge | Governor | Submit `ontology.merge.apply`; reconcile publication separately from draft creation |
| Propose instance links | Governor | Run `bridge.mapping.preview` for the selected import task and target ontology |
| Evaluate instance links | Steward | Run `bridge.mapping.evaluate`; return consistent accepted/held IDs and reasons for the same preview |
| Publish eligible links | Governor | Use explicit approval or the configured validated-only automation policy; retain the publication evidence |

The browser now uses `frontend/src/services/agentToolResult.js` for both roles' result envelopes. Wrong agents, wrong tools, failed/running results, missing run identities, stale preview decisions and inconsistent accepted/held decisions are rejected. This validator replaces the duplicated Governor-specific helper and weaker Steward check. Internal diagnostics are retained outside ordinary Companion messages.

The existing intake, structure-review, bridge-planner and inference agents still have catalog/workflow callers. They provide separate preparation or read-only review capabilities; they are not duplicate Governor/Steward publication authorities and have not been deleted.

## Existing engines and stores

| Capability | Implementation | Integration boundary |
|---|---|---|
| Ontology generation, namespace handling and reasoning | Semantica `OntologyEngine`, `NamespaceManager`, `Reasoner` through `semantica_adapter.py` | Owned by the Ontology service; retained artifacts and lifecycle remain authoritative |
| Decision-policy checks | Semantica `ContextGraph.enforce_decision_policy` through `intelligence.py` | Shared scoped assessment for Recommendations, instance linking and ontology merging; ordinary chat answers do not imply policy approval |
| Business-object context | Semantica `ContextGraph` through `business_context.py`, persisted in PostgreSQL | Existing context search/traversal APIs; it is not automatically synchronized with Neo4j |
| Graph search and analytics | Neo4j projections and Semantica `GraphAnalyzer` | Graph service owns graph data and publication barriers |
| Agent memory | Existing graph-native `AgentMemoryService`, plus owned PostgreSQL chat/workflow state | Neo4j conversation/reasoning/approved bridge facts are optional; caller-owned scoped chat history supports follow-ups |
| Provenance | Source IDs/hashes, lifecycle metadata, publication receipts and Steward PROV-O evidence | A saved proposal or version is not proof of current graph publication |
| Audit trail | Existing `AgentTelemetry` and retained execution records | Operational records; not an independently certified append-only or tamper-proof audit ledger |

Configured telemetry now records the selected provider's model rather than reporting an old Ollama model when OpenAI/Mistral is selected. `model_selection_only=true` explicitly distinguishes configuration metadata from proof that a model executed a particular tool.

## Other pages and the Companion

The shared drawer now sends a validated page identifier. It is a retrieval hint, never authorization or permission to execute tools. Page changes reset the visible conversation scope; retained history and follow-up retrieval also include that scope.

- Data Catalog reads a bounded existing catalog product listing.
- Data Products reads a bounded existing retained-product listing.
- Data Flow reads a bounded existing job-run listing.
- Graph, Where Used, Modeling, Requirements, Ontology Junction and QIF can retrieve business objects through the existing Semantica ContextGraph search when no exact ontology scope is selected.
- The ContextGraph API currently has no qualified ontology-ID filter. The Companion does **not** drop an exact selected scope to perform an unscoped context search. Scoped Neo4j and saved mapping evidence remain separate.
- Other pages retain graph/mapping retrieval; no unsupported dedicated connector is invented. Bounded page listings provide status/context, not exhaustive semantic search or automatic analytics/KPI calculation.

All page reads use owning-service APIs, the caller's read bearer and destination-specific gateway headers. A single bounded JSON transport replaces duplicated mapping-read transport. Only small allowlisted record fields enter answers; execution payloads, credentials and arbitrary metadata are discarded. Data is retrieved, not approved or published. Failure of a context service is reported separately from an empty listing. Business-context search requires persistence so it cannot silently serve stale cached state after a registry failure.

## Removed code and retained compatibility

Removed after checking repository references:

- `governorResult` and the duplicated envelope validator in `ontologyMergeAgent.js`; callers now use the shared role-aware validator.
- The separate weak Steward envelope check in `bridgeApi.js`.
- Unused `mapping_question` in `ontology_service/companion_evidence.py`.
- Unused `_save_policies` in `ontology_service/intelligence.py`.
- Unreachable exception-policy bookkeeping after the existing explicit rejection of caller-supplied policy exceptions.
- Redundant Companion header initialization and the obsolete 900-node setting where the actual service bound is 200.
- Duplicated context-read HTTP/authentication logic.

Retained deliberately: `backend/agent/chat.py`, `backend/chains/vector.py`, `backend/chains/cypher.py` and the legacy `backend/main.py` compatibility routes. `backend/main.py` still imports/calls those modules. Removing them without migrating that entry point would break a supported path. No existing database, schema files, credentials or retained memory are deleted by this source cleanup.

## Verification and deployment

Tests cover shared Governor/Steward envelopes, stale-preview and contradictory-decision rejection, existing merge/bridge workflows, business-context persistence, page routing, read credential forwarding, scoped memory and provider-correct telemetry. The installed Semantica `ContextGraph.query` contract was inspected and exercised using an in-memory probe so the Companion adapter uses the real result shape. This is not a live business-data acceptance test.

Apply the verified existing updater from the normal Windows administrator session, then retest the selected ontology versions and import tasks in the browser. Agent-process inspection remains unavailable in the automation session; no process-identity guard is bypassed. The [Companion audit](audits/knowledge-companion-graphrag-2026-10-22.md) describes the remaining model-accuracy and source-data acceptance limits.


## Shared decision policy integration

`backend/depo_platform/decision_policy.py` calls the existing Ontology service policy API over authenticated, bounded HTTP. That service owns `SemanticIntelligence`, the native Semantica evaluator and the central PostgreSQL registry. Ontology-owned merge checks evaluate locally rather than making a self-request. Other service runtimes do not import the ontology engine to assess a policy. It introduces no new agent or policy language. The modern Graph-service Recommendations endpoints, retained monolith endpoints and legacy recommendation tools now assess their graph-derived advice. Instance Bridge evaluates a batch from its saved preview; both manual and automatic publication recheck current policy after receipt reconciliation. Ontology merges assess the saved artifact and recheck before catalog registration. Existing identity, ambiguity, source-snapshot, lifecycle, SHACL and OWL-RL gates remain mandatory.

Policies in `ontology_semantic_policies` declare `operations`: `recommendations`, `instance_bridge`, `ontology_merge`, `ontology_import`, or `*`. Legacy policies without this field remain global. No applicable active policy returns `not_configured`, `compliant: null`; it does not fabricate approval or disable existing gates. Policy/evidence-store failures return `unavailable` and hold writes. Supported native rules are only minimum confidence, permitted outcomes, required metadata fields and reasoning length. Unknown/empty rules fail instead of being silently ignored. At most 32 active policies and 2000 candidate decisions are assessed in one bounded batch.

All proposed decisions use outcome `flagged`; neither the evaluator nor the UI pretends they are already approved. Instance mappings carry their recorded matching score, explicitly marked as a heuristic. Ontology unions and recommendation advice have no calibrated decision confidence: the adapter records zero and `confidence_basis: not_established`. Impact scores and similarity ranks are not substituted for that missing evidence. A minimum-confidence policy can therefore hold these operations; configure its scope deliberately. The native engine checks metadata presence, not its semantic truth, and does not prove engineering equivalence or full OWL-DL consistency.

Assessments in `semantic_decision_assessments` retain the decision content, decision/policy digests, native findings and evaluation time. Reports embedded in agent/workflow results and the UI carry the assessment identity. These are operational PostgreSQL records, not a certified immutable ledger. Repeated identical assessments reuse their content-derived identity; changed decisions or policies produce different identities. UI findings are limited to 200 rows while the persisted assessment includes all checks. No credentials are copied to decision evidence.

The active Recommendations similarity score now uses token Jaccard (75%) and graph-type overlap (25%) across at most 50 lexical candidates. Sorting or renaming query result positions cannot manufacture a higher score. This bounded heuristic does not establish equivalence, and legacy rich engineering recommenders retain their own documented scoring features.


Import clients accept explicit `not_configured` without confusing it with a policy rejection, while retaining quality and lifecycle gates. During rolling upgrades an older compliance-only response is accepted only when `compliant` is the boolean `true` and no supplied check contradicts it. New peer responses bind the requested operation and decision digest, reject malformed evidence, and expose absence separately from a pass. Ingestion submits flagged import evidence without manufacturing confidence or a lifecycle approval. These contracts are shared by engineering-file and source-profile ingestion.


## Page task workspace

`PageTaskWorkspace` supplies compact guidance across the 17 navigation pages. It reuses the existing AgentProposalPanel, durable read-goal runner and workflow engine. Domain-specific writes continue through their existing tool, approval and publication contracts. No agent or execution engine is added.

The Agentic `GET /api/v1/page-tasks?page=<page>` view reads the existing goal, workflow and telemetry registries. New executions retain a whitelisted page/source binding and an owner-derived page key. The server derives ownership from authenticated identity and checks it again before details are returned. Each request reads at most 50 records per kind (default 20) with per-kind pagination; list statuses are retained snapshots and detail reads reconcile native workflow/goal status. Tool telemetry details are explicitly whitelisted. Native import/pipeline/domain histories and untagged older tasks remain in their original views.

Read goals accept an optional canonical UUID `submission_id`. A deterministic owner-bound goal identity and protected intent digest are checked under the queue advisory lock. Repeated identical submissions return the original task; changed intent with the same submission identity returns 409. This recovers uncertain read-goal submission without creating duplicates. It does not add automatic retry to write execution.

TaskProgress distinguishes planned steps, observed actions, evidence-based conclusions, review holds and uncertain outcomes. Workflow controls come from the native server's allowed actions. Clearing credentials aborts reads and clears visible state; selecting a different source separates browser bookmarks. The task panel never interprets a completed agent run as proof of publication.
