# Agent-wise prompt inventory

Audit date: 2026-10-28. Production prompts are unchanged. `inventory.json` contains each source, variables, context/memory, model, tools, handoff, output and consumer. `source-inventory.json` preserves exact source hashes and raw discovery candidates.

## Default runtime agents

| Agent | Source | Allowed tools |
|---|---|---|
| ontology-intake | [backend/agentic_service/catalog.json:12](../../../backend/agentic_service/catalog.json#L12) | engineering.inspect, ontology.generate, ontology.agent.intake |
| ontology-structure-review | [backend/agentic_service/catalog.json:21](../../../backend/agentic_service/catalog.json#L21) | ontology.agent.review |
| semantic-bridge-planner | [backend/agentic_service/catalog.json:30](../../../backend/agentic_service/catalog.json#L30) | ontology.agent.bridge-plan |
| ontology-export | [backend/agentic_service/catalog.json:39](../../../backend/agentic_service/catalog.json#L39) | ontology.export |
| ontology-orchestrator | [backend/agentic_service/catalog.json:48](../../../backend/agentic_service/catalog.json#L48) | ontology.agent.orchestrate |
| context-analyst | [backend/agentic_service/catalog.json:59](../../../backend/agentic_service/catalog.json#L59) | context.upsert, context.search, context.where_used |
| ontology-governor | [backend/agentic_service/catalog.json:77](../../../backend/agentic_service/catalog.json#L77) | ontology.register, ontology.transition, ontology.export, ontology.merge.preview, ontology.merge.apply, bridge.mapping.preview, bridge.mapping.publish, engineering.publish, bridge.mapping.publish_automatic, ontology.merge.apply_automatic |
| engineering-parser | [backend/agentic_service/catalog.json:88](../../../backend/agentic_service/catalog.json#L88) | engineering.inspect, profile.inspect, profile.execute |
| graph-analyst | [backend/agentic_service/catalog.json:108](../../../backend/agentic_service/catalog.json#L108) | graph.analytics, graph.neighborhood, context.search, context.where_used, oslc.graph_rag, recommendation.change_impact, recommendation.similar_parts, recommendation.manufacturing, graph.search, graph.business_context, graph.document_evidence, graph.business_answer |
| oslc-link-agent | [backend/agentic_service/catalog.json:119](../../../backend/agentic_service/catalog.json#L119) | oslc.remote.catalog, oslc.remote.query, oslc.remote.sync |
| schema-set-agent | [backend/agentic_service/catalog.json:131](../../../backend/agentic_service/catalog.json#L131) | schema-set.standards, schema-set.upload, qif.task.status, qif.task.commit |
| data-product-governor | [backend/agentic_service/catalog.json:143](../../../backend/agentic_service/catalog.json#L143) | data.catalog.products, data.product.preview, data.product.publish, data.product.revoke |
| ceim-mapper | [backend/agentic_service/catalog.json:153](../../../backend/agentic_service/catalog.json#L153) | ceim.contract, ceim.normalize.batch |
| data-quality-monitor | [backend/agentic_service/catalog.json:164](../../../backend/agentic_service/catalog.json#L164) | pipeline.telemetry, pipeline.transform, pipeline.run |
| ontology-steward | [backend/agentic_service/catalog.json:174](../../../backend/agentic_service/catalog.json#L174) | bridge.mapping.evaluate, ontology.merge.evaluate |
| ontology-inference | [backend/agentic_service/catalog.json:184](../../../backend/agentic_service/catalog.json#L184) | ontology.inference.preview, ontology.reasoning.inspect |
| dt-intake | [backend/agentic_service/prompt_policy.py:7](../../../backend/agentic_service/prompt_policy.py#L7) | engineering.inspect, ontology.register, pipeline.definitions |
| dt-domain-identifier | [backend/agentic_service/prompt_policy.py:7](../../../backend/agentic_service/prompt_policy.py#L7) | ceim.contract, context.search |
| dt-structure-review | [backend/agentic_service/prompt_policy.py:7](../../../backend/agentic_service/prompt_policy.py#L7) | pipeline.definitions, pipeline.run, pipeline.run.evidence |
| dt-semantic-bridge-planner | [backend/agentic_service/prompt_policy.py:7](../../../backend/agentic_service/prompt_policy.py#L7) | ceim.contract, ceim.normalize.batch |
| dt-entity-conflict-review | [backend/agentic_service/prompt_policy.py:7](../../../backend/agentic_service/prompt_policy.py#L7) | ontology.merge.preview, pipeline.run.evidence |
| dt-property-conflict-review | [backend/agentic_service/prompt_policy.py:7](../../../backend/agentic_service/prompt_policy.py#L7) | pipeline.definitions, pipeline.run, pipeline.run.evidence |
| dt-context-graph-conflict-review | [backend/agentic_service/prompt_policy.py:7](../../../backend/agentic_service/prompt_policy.py#L7) | context.where_used, graph.neighborhood, pipeline.run.evidence |
| dt-data-product-interaction | [backend/agentic_service/prompt_policy.py:7](../../../backend/agentic_service/prompt_policy.py#L7) | data.catalog.products, data.catalog.product, pipeline.definitions, pipeline.run, pipeline.run.evidence |
| dt-kg-interaction | [backend/agentic_service/prompt_policy.py:7](../../../backend/agentic_service/prompt_policy.py#L7) | graph.analytics, graph.neighborhood, oslc.graph_rag |
| dt-export | [backend/agentic_service/prompt_policy.py:7](../../../backend/agentic_service/prompt_policy.py#L7) | ontology.export |
| dt-self-learning-review | [backend/agentic_service/prompt_policy.py:7](../../../backend/agentic_service/prompt_policy.py#L7) | pipeline.run.evidence |
| dt-orchestrator | [backend/agentic_service/prompt_policy.py:7](../../../backend/agentic_service/prompt_policy.py#L7) | pipeline.definitions, pipeline.runs, pipeline.run.evidence, data.catalog.products |

All 28 roles were captured through the actual suggestion builder in both structured and native modes (56 captures), with real service input schemas and mocked inference. Capturing a schema-bound request is not successful execution of the proposed tool. Some empty synthetic arguments were rejected after capture.

## Shared and auxiliary surfaces

| ID | Surface / source | Variables | Consumer / boundary |
|---|---|---|---|
| S01 | Companion composed system policy — [backend/agentic_service/local_llm.py:130](../../../backend/agentic_service/local_llm.py#L130) | question;  business evidence;  vocabulary;  citation IDs | validate_summary -> companion.py -> required turn retention -> Chatbot. PLM/MBSE language, business tables, no XML/JSON, no invented ownership or approval; system += fragments at 132/137. |
| S02 | Companion evidence user message — [backend/agentic_service/local_llm.py:138](../../../backend/agentic_service/local_llm.py#L138) | protected question;  protected evidence;  citation identifiers | KnowledgeCompanion.ask. Scoped owning-service retrieval precedes generation; six scoped PostgreSQL prior turns refine retrieval. |
| S03 | Shared role and proposal policy — [backend/agentic_service/prompt_policy.py:16](../../../backend/agentic_service/prompt_policy.py#L16) | catalog role;  role fallback;  structured/native mode | local_llm.suggest_tool. Server-owned role/policy; PA-04 documents incorrect reuse in executed read-goal mode. |
| S04 | Proposal user payload and tool metadata — [backend/agentic_service/local_llm.py:225](../../../backend/agentic_service/local_llm.py#L225) | task;  context;  attachment metadata;  allowed_tools | suggest_agent_tool -> RecommendationStore -> AgentProposalPanel. Uses all 57 real OpenAPI schemas as appropriate per role; tool metadata bypasses protect. |
| S05 | Read-goal planning and completion suffix — [backend/agentic_service/goal_routes.py:247](../../../backend/agentic_service/goal_routes.py#L247) | role;  user goal;  exact scope | goal_runner.drive. Plan first, read evidence, revise after failures, complete with observations; conflicts with suggestion suffix. |
| S06 | Goal scratchpad and failure reflection input — [backend/agentic_service/goal_runner.py:140](../../../backend/agentic_service/goal_runner.py#L140) | goal;  context;  plans;  observations;  decisions;  max_decisions | goal_routes.propose -> suggest_tool. Per-observation 32000-byte budget and whole-state 120000-byte budget; whole-state prefix truncation loses recent results. |
| S07 | Ontology review policy, evidence and JSON schema — [backend/agentic_service/local_llm.py:304](../../../backend/agentic_service/local_llm.py#L304) | terms <=30;  candidates <=20;  artifact digest;  counts;  metadata keys | validate_review -> ontology_orchestrator._llm_suggestion -> review UI. Up to three grounded questions, exact supplied term IRIs, explicit limitations; no semantic consistency/publication proof. |
| S08 | Generation capability probe — [backend/agentic_service/local_llm.py:268](../../../backend/agentic_service/local_llm.py#L268) | configured provider/model;  route | Admin model diagnostics. Reply OK verifies nonempty generation only, not factual quality. |
| S09 | Structured-output capability probe — [backend/agentic_service/local_llm.py:271](../../../backend/agentic_service/local_llm.py#L271) | configured provider/model;  ok:true schema | Admin model diagnostics. Return JSON with ok true; exact schema checked after response. |
| S10 | Native-tool capability probe — [backend/agentic_service/local_llm.py:272](../../../backend/agentic_service/local_llm.py#L272) | capability_check definition;  ok:true schema | Admin model diagnostics. Advertised capability function is validated but never executed. |
| S11 | Cloud JSON-schema system prefix — [backend/core/llm_providers.py:105](../../../backend/core/llm_providers.py#L105) | body.format;  original messages | post_cloud_chat -> local_llm. Schema text is inserted as a system message; JSON object mode is not full constrained schema decoding; application validates output. |
| S12 | AOI JSON-only system prefix — [backend/aoi_gateway/app.py:146](../../../backend/aoi_gateway/app.py#L146) | messages;  response_format | isolated AOI worker -> adapter -> application. Adds JSON-object instruction; no native tools or streaming; opaque compiled wrapper internals not certified. |
| S13 | Literal system/user message factory — [backend/core/ollama_runnable.py:59](../../../backend/core/ollama_runnable.py#L59) | system;  user | summarize / suggest_tool / review_ontology_evidence. Formats {policy}/{evidence} placeholders so braces inside values remain literal. |
| S14 | Home sample-query family — [backend/agentic_service/companion_prompts.py:2](../../../backend/agentic_service/companion_prompts.py#L2) | six sample choices | companion_sample_queries -> Chatbot. Samples request evidence and do not establish its existence. |
| S15 | Page sample-query families — [backend/agentic_service/companion_prompts.py:10](../../../backend/agentic_service/companion_prompts.py#L10) | page key;  PAGE_PROMPTS variants | Chatbot. Page-specific questions; recommendations maps to missing quality entry and falls back to Home. |
| S16 | Recommendation task template — [frontend/src/utils/recommendationGoal.js:13](../../../frontend/src/utils/recommendationGoal.js#L13) | service;  JSON-quoted business name;  top_n;  separate exact node/scope | RecommendationsWorkspace -> useReadGoal -> goal_routes. Must call selected recommendation tool and cite its policy-assessed observation; never approve reuse/publication. |
| S17 | Graph investigation editable/default task — [frontend/src/features/graph/GraphInvestigation.js:6](../../../frontend/src/features/graph/GraphInvestigation.js#L6) | question <=2000 chars;  node ID;  display name;  visible counts;  ontology selection | ReadGoalPanel -> graph investigation. Bounded graph slice; distinguish source reference, semantic mapping and inference; no writes. |
| S18 | Inference editable/default question — [frontend/src/Components/ontology/OntologyInferenceWorkbench.js:34](../../../frontend/src/Components/ontology/OntologyInferenceWorkbench.js#L34) | question <=8000 chars;  selected ontology;  rules;  limit | ReadGoalPanel -> ontology-inference. Structural preview and explanation; no SWRL execution or materialization claim. |
| S19 | Page workspace freeform goal input — [frontend/src/Components/PageTaskWorkspace.js:80](../../../frontend/src/Components/PageTaskWorkspace.js#L80) | user question;  selected catalog role;  optional ontology;  page | ReadGoalPanel / AgentProposalPanel. Page profiles guide work; retained owner/page task state does not create a second execution engine. |
| S20 | Freeform suggestion task/context — [frontend/src/Components/AgentProposalPanel.js:59](../../../frontend/src/Components/AgentProposalPanel.js#L59) | task <=8000 chars;  context;  optional attachment metadata | agents/{id}/suggest -> retained proposal UI. Source file content is bound server-side; model sees attachment metadata, not the full upload. |
| S21 | Legacy senior engineering/tool-selection policy — [backend/agent/chat.py:723](../../../backend/agent/chat.py#L723) | question;  live tools;  history;  graph context | retired aggregate chat -> LangGraph -> ToolNode. Trust boundary exists; operation-sequence/style assumptions and nested model calls differ from current Companion. |
| S22 | Legacy graph snapshot augmentation — [backend/agent/chat.py:216](../../../backend/agent/chat.py#L216) | browser snapshot;  node properties;  relationships | legacy call_model. Bounded normalized untrusted HumanMessage block; browser graph is not authorization. |
| S23 | Legacy durable-memory augmentation — [backend/agent/chat.py:317](../../../backend/agent/chat.py#L317) | session ID;  six recent memory messages | legacy call_model. 700 characters/message, marked prior untrusted data; session ownership depends on endpoint/principal. |
| S24 | Legacy general-chat subagent — [backend/agent/chat.py:347](../../../backend/agent/chat.py#L347) | query | ToolNode -> outer agent. System is a general PLM expert; outer policy says greetings only, tool docstring says general questions; nested model call. |
| S25 | Legacy graph-vector summary policy — [backend/chains/vector.py:30](../../../backend/chains/vector.py#L30) | retrieved graph documents;  input | general_qa_chain -> vector tool -> outer agent. Untrusted context is interpolated into a system message; no current mandatory citation contract. |
| S26 | Legacy document-vector summary policy — [backend/chains/vector.py:19](../../../backend/chains/vector.py#L19) | datasheet chunks;  input | data_qa_chain -> vector tool -> outer agent. Same system-context issue; current Companion does not call this path. |
| S27 | Legacy Cypher generation template — [backend/chains/cypher.py:13](../../../backend/chains/cypher.py#L13) | graph.get_schema;  user question | SafeCypherQA -> legacy graph tool. Code checks generated query via assert_read_only_cypher and timed gateway; prompt wording alone is not the guard. |
| S28 | Legacy Ollama knowledge-context wrapper — [backend/Services/ollama_service.py:118](../../../backend/Services/ollama_service.py#L118) | context;  prompt | compatibility query / aggregate fallback. Single user message mixes context and task; no shared citation validation or prompt_security boundary. |
| S29 | Legacy import guidance template — [backend/Services/ollama_service.py:155](../../../backend/Services/ollama_service.py#L155) | file_type;  schema counts | generate_guidance caller. 2-3 encouraging sentences, temperature .5; feature promises require actual readiness evidence. |
| S30 | Legacy import completion template — [backend/Services/ollama_service.py:168](../../../backend/Services/ollama_service.py#L168) | entity / derived / inverse counts | generate_completion_message caller. 3-4 enthusiastic sentences assumes success and advertises search/recommendations/impact; no publication receipt input. |
| S31 | Legacy aggregate fallback assembly — [backend/main.py:261](../../../backend/main.py#L261) | message;  UI/live graph context first3500 characters | _load_chat_generators response/stream fallback. Uncited generation when legacy imports fail; not current SPA chat routing. |
| S32 | Semantic Bridge CLI task — [infra/windows/semantic-bridge/semantic-bridge-integration.ps1:369](../../../infra/windows/semantic-bridge/semantic-bridge-integration.ps1#L369) | TaskPrompt;  source ID;  target ontology ID;  scenario | ontology-governor suggest -> retained test report. Operator test can retain previews/proposals; automation requires explicit switch. It was not run by this audit. |
| S33 | CLI generation/chat probe — [infra/windows/test-depo-ollama.ps1:133](../../../infra/windows/test-depo-ollama.ps1#L133) | model;  route;  explicit probe switch | operator readiness report. Small Reply OK prompt; protocol test only. |
| S34 | CLI structured proposal probe — [infra/windows/test-depo-ollama.ps1:196](../../../infra/windows/test-depo-ollama.ps1#L196) | model;  diagnostic-noop schema | operator readiness report. Proposal only, no tool execution. |
| S35 | CLI streaming probe — [infra/windows/test-depo-ollama.ps1:209](../../../infra/windows/test-depo-ollama.ps1#L209) | model;  native NDJSON route | operator readiness report. Reply OK; complete marker validation, not semantic quality or incremental latency certification. |
| S36 | SchemaSet_Ontology metadata prompt — [backend/qif/agents/qif_ontology.yaml:3](../../../backend/qif/agents/qif_ontology.yaml#L3) | XSD sources;  provenance;  resolver inputs | QifAgentRegistry -> deterministic tools. Registry resolves tools without sending system_prompt to a model; one ontology per schema set, no invented unresolved terms. |
| S37 | MBSE_Model_Agent metadata prompt — [plugins/mbse_plugin/agents/mbse_agent.yaml:3](../../../plugins/mbse_plugin/agents/mbse_agent.yaml#L3) | model source;  governed job;  tool inputs | optional external registry host. Registers tools, not a core model instance; empty can_handoff_to. |
| S38 | Standalone Ontology Intake Agent — [standalone/ontology_agentic_service/AgentsRegistry/Agents/ontology_intake_agent.yaml:3](../../../standalone/ontology_agentic_service/AgentsRegistry/Agents/ontology_intake_agent.yaml#L3) | source path;  requested reasoning;  external registry selection | separate standalone host. Still references Owlready2; empty can_handoff_to; not default core catalog. |
| S39 | Standalone Ontology Review Agent — [standalone/ontology_agentic_service/AgentsRegistry/Agents/ontology_review_agent.yaml:3](../../../standalone/ontology_agentic_service/AgentsRegistry/Agents/ontology_review_agent.yaml#L3) | source path;  profile;  optional reasoner | separate standalone host. RDF asserted evidence separated from reasoning, but old engine/dependency claims remain. |
| S40 | Standalone Ontology Alignment Agent — [standalone/ontology_agentic_service/AgentsRegistry/Agents/ontology_alignment_agent.yaml:3](../../../standalone/ontology_agentic_service/AgentsRegistry/Agents/ontology_alignment_agent.yaml#L3) | source metadata;  ontology;  optional external/MCP inputs | separate standalone host. Draft planning; no mutation unless host workflow requests an allowed write; connector safety remains required. |
| S41 | Standalone Ontology Export Agent — [standalone/ontology_agentic_service/AgentsRegistry/Agents/ontology_export_agent.yaml:3](../../../standalone/ontology_agentic_service/AgentsRegistry/Agents/ontology_export_agent.yaml#L3) | source path;  destination;  format | separate standalone host. Creates exported copy without overwriting source; empty can_handoff_to. |

## Deterministic workflow bindings

These are server-defined sequences, not autonomous model-to-model delegation. Tool names containing agents do not imply an additional LLM call.

### data-product-governed-publication

1. `data-product-governor` → `data.product.preview`; bindings `{}`.
2. `data-product-governor` → `data.product.publish`; bindings `{}`.

### engineering-governed-publish

1. `ontology-intake` → `engineering.inspect`; bindings `{}`.
2. `ontology-governor` → `engineering.publish`; bindings `{}`.

### business-context-enrichment

1. `context-analyst` → `context.upsert`; bindings `{}`.
2. `context-analyst` → `context.where_used`; bindings `{}`.

### ontology-review-and-bridge-plan

1. `ontology-intake` → `ontology.agent.intake`; bindings `{}`.
2. `ontology-structure-review` → `ontology.agent.review`; bindings `{"artifact_digest": "$steps.1.result.artifact_digest"}`.
3. `semantic-bridge-planner` → `ontology.agent.bridge-plan`; bindings `{"artifact_digest": "$steps.1.result.artifact_digest"}`.

### bridge-validated-automation

1. `ontology-governor` → `bridge.mapping.preview`; bindings `{}`.
2. `ontology-steward` → `bridge.mapping.evaluate`; bindings `{"preview_id": "$steps.1.result.job_id"}`.
3. `ontology-governor` → `bridge.mapping.publish_automatic`; bindings `{"preview_id": "$steps.1.result.job_id"}`.

### ontology-union-automation

1. `ontology-governor` → `ontology.merge.preview`; bindings `{}`.
2. `ontology-steward` → `ontology.merge.evaluate`; bindings `{"preview_id": "$steps.1.result.preview_id"}`.
3. `ontology-governor` → `ontology.merge.apply_automatic`; bindings `{"preview_id": "$steps.1.result.preview_id"}`.
