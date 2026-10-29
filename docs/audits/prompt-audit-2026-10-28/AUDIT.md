# PMem application-wide prompt audit

Follow-up: [implemented fixes, final regression results and remaining qualification](REMEDIATION.md). This document preserves the original pre-fix findings.

Current [deliverable reconciliation](DELIVERABLE_STATUS.md) distinguishes baseline artifacts from the updated dependency map and current policy snapshot.

Date: 2026-10-28. Scope: the local `pmem-publish` working tree on `codex/windows-setup-audit-fixes`, including its existing uncommitted fixes. The audit is of this snapshot, not a certification of the customer VM or every future operator-supplied catalog. Existing production code and prompts were not changed. Exact hashes are in `source-inventory.json`; `source-preservation.json` verifies preservation after the audit.

## Result

Three P1 defects were reproduced: camelCase secret fields bypass redaction; tool metadata bypasses the outbound redaction path; prefix truncation removes the newest goal observations. The remaining register distinguishes active-path P2/P3 defects, two conditional legacy/standalone defects, and test-contract drift. Seven further risks are separated from the twelve findings. Citation validation establishes membership, not truth. Schema validation and system/user separation do not establish resistance to a live model jailbreak.

Discovery covered 683 executable/configuration sources (tracked application sources plus two current untracked runtime modules), 389 lexical hits and 107 raw prompt/template candidates, with no Python parse errors. Raw candidates include consumers, factories and non-prompt output variables: they are not 107 independent prompts. The curated inventory contains 28 runtime roles and 41 shared/auxiliary prompt surfaces, including dynamic construction, frontend task builders, capability probes, optional legacy chains, YAML metadata and transport schema prefixes. All 28 role prompts were captured in structured and native modes (56 model-bound fixtures).

## Deliverables

- [Agent-wise inventory and workflow bindings](INVENTORY.md); complete traces and exact role text in [inventory.json](inventory.json).
- [Prompt dependency map](dependency-map.mmd).
- Severity-ranked findings below and [machine-readable register](defects.json).
- [Unapplied replacement prompt drafts](proposed-prompts.json): 56 role/mode drafts plus shared contracts. These are proposals, not verified fixes.
- [Executable reproductions and control cases](test_prompt_audit_reproductions.py), [regression plan](REGRESSION.md), [test totals](test-results.json), and retained JUnit XML.
- [Configuration names and construction sites](configuration-names.json), source hashes, raw lexical discovery, runtime catalog, live OpenAPI contracts and synthetic model request captures.

## Executed validation and limits

The existing targeted suite recorded **141 passed, 3 failed**. The audit-specific suite recorded **81 passed**, including tests that intentionally assert defective behavior. Passing `test_repro_*` means the defect is reproducible, not repaired. The existing failures are one prompt-role naming contract mismatch and two stale extracted-router fixtures; they are not proof of runtime router NameError/AttributeError. See PA-12.

Read-only GETs to the ten running services' `/openapi.json` endpoints all returned 200. The actual proposal schema resolver resolved all 57 default tool contracts. Runtime prompt capture used those schemas and the real prompt constructors with mocked inference. Empty synthetic proposed arguments sometimes failed validation after capture; this does not demonstrate completed execution for every tool. Both structured and native requests were inspected. Representative tests exercised secret redaction, malicious retrieved text, literal braces, missing inputs, oversized observations, fabricated citations, unsupported claims, forged observation IDs, out-of-scope selections and prohibited writes.

No LLM/provider inference, approval, publication, import, database mutation or service restart was performed. Synthetic memory/graph/tool fixtures simulate adversarial stored content; no hostile material was written into customer PostgreSQL or the business graph. Live LLM services remain disabled. Actual model nondeterminism, model-specific token fit, customer concurrency/latency, cross-user deployment identity policy and vendor-hidden prompts therefore remain unqualified. No finite test set can certify every jailbreak or 100% bug absence.

## Runtime construction and ownership

### Catalog roles and proposal modes

`catalog_loader.load_catalog` loads the repository catalog or an explicit operator override, validates it, extends twelve DT roles and validates again. Sixteen roles are explicit. `proposal_instructions` combines the server-owned role with shared scope, evidence and output policy. No separate active developer-role message was found: these constraints are composed into system messages. `local_llm.suggest_tool` serializes protected task/context/attachment metadata and allowed tool contracts into user data. PA-02 identifies the unprotected tool-metadata branch.

The API resolves real owning-service OpenAPI input schemas, removes server-only approval fields from model-visible top-level inputs and validates proposals again. Retained suggestions are owner-bound. A suggestion is not execution. Mutating execution still requires the server's grant, source/revision and approval checks; no prompt grants those rights.

### Read-goal planning, memory and handoff

Goal creation bounds task/context, pins immutable scope, binds owner/submission identity and requires worker access. The server exposes only plan, eligible reads and completion. It rejects changed scope, write selections, duplicate completed reads and fabricated observation IDs. It limits decisions/deadline and plan count. PostgreSQL retains the pending observation before dispatch and the result before the next decision. Recommendation goals additionally bind the intended service, selected business object, scope and analysis policy tool.

Reflection is instruction plus retained error observations, not a separately discovered reflection model. There is no model-controlled cross-agent delegation in this default path. The six workflows bind agent IDs to tool steps deterministically. Goal prompts reuse suggestion-only policy (PA-04); memory's whole-envelope truncation can remove the latest observation (PA-03); missing-input requests have no dedicated terminal state (PA-08).

### Companion, GraphRAG and vocabulary

The Companion retrieves scoped owning-service business instances, graph relationships, vocabulary and page/document evidence. Six prior scoped PostgreSQL turns can refine follow-up retrieval; history is not an authorization source or proof of a business fact. Business evidence and ontology definitions are distinct. Optional graph memory enrichment is best effort; required turn retention precedes streaming a response. Provider generation, when enabled, receives a composed business policy and protected evidence JSON, then citation/output validation. The deterministic business result remains available when model generation fails; model interpretation is not independently verified engineering approval.

The UI renders sanitized Markdown and maps references to retained evidence. It must agree with the backend about admissible citation IDs and individual factual blocks; PA-05 through PA-07 identify gaps. Naming a schema class or finding a property definition does not establish that a particular part owns PMI or a requirement. PR-01 demonstrates that a valid observation reference alone does not prove an assertion's content.

### Ontology review, Semantic Bridge and inference

The optional ontology review model receives an artifact digest, counts, metadata keys, at most 30 terms and 20 candidates. This is a structural evidence slice, not a full reasoning proof. It cannot apply mappings or publish. The actual call supplies `REVIEW_SCHEMA`; the server checks exact supplied IRIs and output bounds. Wording can be clearer (PR-06), but the schema is not missing. Semantic Bridge proposal/validation/publication and inference tools remain owning-service operations; role names do not imply a hidden LLM at every stage. No prompt-only change should bypass Steward or service publication validation.

### Providers, MCP and optional paths

Ollama/OpenAI/Mistral/AOI transports retain caller message roles and validate response envelopes. Cloud structured mode adds schema instructions; native calls remain proposals. Literal braces in user values were not reinterpreted as template variables. Current Companion requests ask for 768 output tokens; proposals request 1024. Byte limits are not model-aware token budgets (PR-02). The largest captured default role request was about 7.4k user characters plus 3.7k system characters, before provider framing; pathological evidence remains a separate concern.

All 57 default tools are OpenAPI-bound. A Semantica MCP server descriptor exists, but there are no default MCP tool bindings. The MCP transport rejects sampling/elicitation/roots requests; no default MCP prompts/list or prompts/get prompt delegation was found. Operator-supplied catalogs and external server internals are outside this snapshot.

Modern ingestion does not mount the retired aggregate chat entry. Legacy LangGraph, vector and Cypher templates were still inspected and are explicitly marked conditional. Read-only Cypher execution guards are code controls, not prompt claims. QIF/MBSE YAML is declarative/deterministic metadata; standalone ontology YAML may be hosted separately. Its Owlready2/Java instructions are stale compatibility artifacts (PA-11), not evidence the active Semantica service uses Owlready2. AOI preserves the approved external wrapper; compiled helper internals are opaque (PR-07).

## Root-cause analysis

1. **Trust handling is not centralized at the final outbound boundary.** Individual payload fields are protected, while tool metadata and unfamiliar key spelling bypass that protection. The fix requires a single sanitized model-visible envelope plus conservative business projections, not merely stronger wording.
2. **One policy is reused for two execution models.** Suggestion-only instructions contradict an executed read loop. Separate mode-specific contracts while preserving agent domain constraints and server authorization.
3. **Memory limits prioritize serialization order rather than investigation state.** Prefix excerpts lose the most recent information and can force repeated or uninformed decisions. Budget durable state explicitly and expose omissions.
4. **Citation identity, presentation and truth are conflated.** Backend recursive IDs differ from UI references; per-item Markdown validation is incomplete; valid references cannot verify semantic entailment. Share an evidence registry, parse rendered blocks consistently and test fact-level grounding separately.
5. **Compatibility and test surfaces drift independently.** Standalone/legacy prompts and extracted test fixtures lag the active architecture. Declare supported deployment paths, retire unused bundles and test contracts at real construction boundaries.

## Severity-ranked findings

Severity: P1 = significant confidentiality/reliability issue in a reachable boundary; P2 = material correctness/design issue; P3 = smaller usability or test-contract issue. A conditional finding needs its optional host/path to be deployed. Exact sources/lines and executable reproductions follow.

### PA-01 — P1 — confirmed

Source: [backend/agentic_service/prompt_security.py:9](../../../backend/agentic_service/prompt_security.py#L9)

**Root cause:** Secret-key normalization handles snake_case/hyphens but misses camelCase aliases. Unknown external secrets do not match environment-secret substitution.

**Reproduction:** Call protect with apiKey, accessToken, refreshToken, clientSecret, subscriptionKey, connectionString and neo4jPass; capture a Companion prompt containing a synthetic apiKey.

**Observed:** All seven aliases retained the synthetic credential. The Companion model-bound user payload retained the synthetic retrieved apiKey.

**Impact:** Sensitive graph/tool/document/context values can reach the configured model or retained prompt snapshots. No real credential was used or leaked by this audit.

**Recommended fix:** Normalize key tokens including camelCase, allowlist business projections, cover connection strings and sanitize the final outbound message boundary.

**Executable case:** test_repro_unrecognized_secret_aliases_are_not_redacted; test_capture_companion_messages_and_schema_credentials

### PA-02 — P1 — confirmed

Source: [backend/agentic_service/local_llm.py:225](../../../backend/agentic_service/local_llm.py#L225)

**Root cause:** Task/context/attachment metadata are protected, but allowed_tools is serialized without protect; native mode duplicates tool metadata into function definitions.

**Reproduction:** Put a synthetic configured ADMIN_API_KEY in an allowed-tool description and in context, then capture suggest_tool.

**Observed:** The context value was redacted while the tool description retained the synthetic configured secret.

**Impact:** Tool-schema descriptions/defaults/examples can bypass redaction before inference and snapshot retention. Production schemas containing secrets were not demonstrated.

**Recommended fix:** Redact/project both user-payload and native-function schema metadata, while validating against the unchanged authoritative schema outside the prompt.

**Executable case:** test_repro_tool_schema_metadata_bypasses_known_secret_redaction

### PA-03 — P1 — confirmed

Source: [backend/agentic_service/goal_runner.py:60](../../../backend/agentic_service/goal_runner.py#L60)

**Root cause:** Whole-scratchpad prefix truncation replaces structured goal/context/plans/observations with an excerpt. Later observations occur at the end.

**Reproduction:** Build five completed observations with 31000-byte results and a unique final fact; call bounded with the drive limit of 120000 bytes.

**Observed:** The newest observation ID and fact disappeared from the model-visible scratchpad.

**Impact:** A goal can lose current evidence, fail to cite a successful read, make incorrect conclusions or exhaust its decision budget.

**Recommended fix:** Preserve controller metadata and observation IDs; budget results individually, prefer current evidence and explicitly summarize omitted older evidence.

**Executable case:** test_repro_global_scratchpad_truncation_drops_latest_observation

### PA-04 — P2 — confirmed

Source: [backend/agentic_service/goal_routes.py:247](../../../backend/agentic_service/goal_routes.py#L247)

**Root cause:** Read goals append planning/execution/completion instructions but reuse the suggestion-only policy; native mode says the dispatcher does not execute the proposal automatically.

**Reproduction:** Assemble the actual prompt_agent expression for graph-analyst, ontology-inference and ontology-steward; apply proposal_instructions(native).

**Observed:** All three prompts combine goal.plan/goal.complete with nonexecution wording. The actual goal controller executes validated reads.

**Impact:** Conflicting action semantics risk held actions, poor completion or budget exhaustion. No live-model behavior is asserted.

**Recommended fix:** Separate suggestion policy from read-goal policy; make advisory completion distinct from execution authorization and publication approval.

**Executable case:** test_repro_read_goal_uses_conflicting_proposal_only_policy

### PA-05 — P2 — confirmed

Source: [backend/agentic_service/prompt_security.py:53](../../../backend/agentic_service/prompt_security.py#L53)

**Root cause:** Citation validation splits blank paragraphs and ASCII -/* bullets, while the UI also supports numbered and Unicode lists.

**Reproduction:** Validate a numbered list with one cited item followed by an uncited factual item.

**Observed:** The uncited second item passed validation.

**Impact:** Item-level grounding instructions are not enforced consistently with the rendered output.

**Recommended fix:** Share one supported Markdown parser between citation validation and rendering; require a citation per factual item/row/paragraph.

**Executable case:** test_repro_numbered_list_can_omit_item_citation

### PA-06 — P2 — confirmed

Source: [backend/agentic_service/prompt_security.py:37](../../../backend/agentic_service/prompt_security.py#L37)

**Root cause:** Recursive evidence_ids accepts arbitrary nested id/iri/source_id/run_id values rather than an owning-service citation registry.

**Reproduction:** Put attacker-added-citation in properties.id of a verified evidence object; validate prose citing that value.

**Observed:** The nested property minted an accepted citation identifier.

**Impact:** Citations can refer to arbitrary values rather than retained evidence objects and may not resolve in the UI.

**Recommended fix:** Create explicit scoped citation targets in owning-service projections and share the exact registry with backend validation and UI rendering.

**Executable case:** test_repro_nested_graph_property_can_mint_a_citation_identifier

### PA-07 — P2 — confirmed

Source: [backend/agentic_service/prompt_security.py:50](../../../backend/agentic_service/prompt_security.py#L50)

**Root cause:** All citation IDs are alphabetically sorted and capped at 200 independently of retained evidence selection.

**Reproduction:** Supply z-owning-record plus 201 lexically earlier nested IDs.

**Observed:** The owning resource remained in evidence but was absent from allowed citations.

**Impact:** Relevant evidence can become uncitable or be replaced by less relevant child identifiers.

**Recommended fix:** Reserve primary evidence IDs first and budget evidence and citations together; expose truncation.

**Executable case:** test_repro_evidence_identifier_cap_can_drop_owning_record

### PA-08 — P2 — confirmed

Source: [backend/agentic_service/goal_runner.py:118](../../../backend/agentic_service/goal_runner.py#L118)

**Root cause:** The goal controller has plan/read/complete but no needs_input/unsupported terminal outcome; the prompt tells the model to omit missing inputs and let validation reject them.

**Reproduction:** Plan an ontology inspection without a required ontology ID; submit the incomplete allowed read twice within three decisions.

**Observed:** No read executed; the run ended budget_exhausted with repeated generic invalid_plan_action observations.

**Impact:** Underspecified requests can consume repeated model decisions without useful clarification.

**Recommended fix:** Add a controller-owned needs_input state, preflight indispensable selections and return safe field-specific validation hints. Do not weaken authorization.

**Executable case:** test_repro_missing_information_has_no_clarification_terminal_action

### PA-09 — P3 — confirmed

Source: [backend/agentic_service/companion_prompts.py:59](../../../backend/agentic_service/companion_prompts.py#L59)

**Root cause:** recommendations maps to quality, which has no PAGE_PROMPTS entry.

**Reproduction:** Call sample_queries(recommendations).

**Observed:** Home prompts are returned instead of recommendation-specific prompts.

**Impact:** Samples do not guide Change Impact, Similar Parts and Process Context use.

**Recommended fix:** Define recommendation-specific samples preserving existing aliases and requiring selected business identity/evidence.

**Executable case:** test_repro_recommendation_samples_fall_back_to_home

### PA-10 — P2 — confirmed-conditional-legacy

Source: [backend/chains/vector.py:19](../../../backend/chains/vector.py#L19)

**Root cause:** Legacy data_prompt and general_prompt embed retrieved context into a system message.

**Reproduction:** Format both real ChatPromptTemplates with an adversarial RAG string without invoking a model or database.

**Observed:** The untrusted string appears in the system message; the current Companion uses a different path.

**Impact:** If this optional legacy path is enabled, RAG data shares the policy message. Actual model exploitation remains untested.

**Recommended fix:** Retire the path or move evidence into separate untrusted messages with current scope/citation/output contracts.

**Executable case:** test_repro_legacy_vector_context_is_inserted_in_system_message

### PA-11 — P2 — confirmed-conditional-bundle

Source: [standalone/ontology_agentic_service/AgentsRegistry/Agents/ontology_review_agent.yaml:3](../../../standalone/ontology_agentic_service/AgentsRegistry/Agents/ontology_review_agent.yaml#L3)

**Root cause:** Standalone intake/review YAML still advertises Owlready2, Java and HermiT/Pellet while core migration uses Semantica/RDF structural checks.

**Reproduction:** Inspect standalone intake/review YAML and its tool bindings.

**Observed:** The older engine instructions and optional tools remain in the independently hosted compatibility bundle, not the core default catalog.

**Impact:** Customers using that bundle can receive inconsistent engine/capability promises.

**Recommended fix:** Retire or migrate tools, dependencies, capabilities and prompts together. Do not claim Semantica structural checks replace full OWL-DL reasoning.

**Executable case:** Source and binding inspection; external host qualification pending

### PA-12 — P3 — confirmed-test-drift

Source: [backend/tests/test_agent_prompt_policy.py:14](../../../backend/tests/test_agent_prompt_policy.py#L14)

**Root cause:** Three baseline tests no longer match source contracts: a literal role-ID assumption and two incomplete AST-extraction fixtures.

**Reproduction:** Run the recorded existing regression selection.

**Observed:** 141 passed, 3 failed: role-ID substring convention; missing catalog fixture in control test; missing resolve_artifact_path fixture in artifact test.

**Impact:** The baseline is not clean. These fixture failures do not prove production NameError or AttributeError bugs.

**Recommended fix:** Update tests against explicit semantic contracts with complete dependencies; preserve real endpoint/controller coverage rather than editing solely for green results.

**Executable case:** existing-tests.xml

## Risks and qualification limits

### PR-01 — P2 — confirmed-validation-limit; semantic-risk

Source: [backend/agentic_service/goal_runner.py:106](../../../backend/agentic_service/goal_runner.py#L106)

goal.complete accepted a synthetic false diameter and invented reuse approval when evidence_steps named a completed observation. Membership/citation syntax is not factual entailment. The UI labels model conclusions advisory; this is not proof of a live hallucination.

**Next action:** Separate extracted facts from interpretation; check identities/values/status claims against structured observations and run domain gold-set evaluation when models return.

### PR-02 — P2 — confirmed-byte-budget; model-fit-risk

Source: [backend/core/payload_limits.py:6](../../../backend/core/payload_limits.py#L6)

262144 bytes is a transport/storage bound, not a provider/model context budget. A 30000-word payload passed. Context-window fit and completion/tool headroom are not checked. Captured default catalog prompts were much smaller.

**Next action:** Add model-aware token budgeting or a conservative configured fit limit; rank evidence and reserve completion/tool overhead.

### PR-03 — P2 — unverified-live-model-security

Source: [backend/agentic_service/local_llm.py:130](../../../backend/agentic_service/local_llm.py#L130)

System/user separation and JSON validation do not prove resistance to indirect injection, multilingual/encoded attacks or model-specific jailbreaks. No live inference was performed.

**Next action:** Qualify each configured provider/model with synthetic canaries and adversarial gold sets; score secret disclosure, refusal, factual grounding and attempted tool actions separately.

### PR-04 — P2 — conditional-legacy-performance-risk

Source: [backend/agent/chat.py:800](../../../backend/agent/chat.py#L800)

Legacy LangGraph can call nested vector/Cypher/general-chat models and retry connections three times. It lacks the main explicit goal decision/deadline state; framework default recursion limits still apply, so this is not an unbounded-loop claim.

**Next action:** Retire or route through the current controller and enforce a shared operation deadline/cost budget.

### PR-05 — P2 — deployment-identity-risk

Source: [backend/agentic_service/sessions.py:18](../../../backend/agentic_service/sessions.py#L18)

Shared API keys intentionally share a principal. Ownership checks do not give individual-person memory isolation to users sharing a credential. Customer identity policy was not inspected.

**Next action:** Use individual/Entra principals for person-specific history and test cross-principal denial; document shared-key behavior.

### PR-06 — P3 — prompt-ambiguity-with-server-mitigation

Source: [backend/agentic_service/local_llm.py:304](../../../backend/agentic_service/local_llm.py#L304)

Ontology review wording omits explicit questions/evidence_iris/limitations shape, but the real JSON schema IS supplied via format; the cloud adapter adds schema instructions and the server validates term IRIs. Model compliance remains untested.

**Next action:** Describe the JSON contract concisely in the policy, allow zero grounded questions and retain structural-only limitations.

### PR-07 — P2 — opaque-external-dependency

Source: [backend/aoi_gateway/vendor.py:18](../../../backend/aoi_gateway/vendor.py#L18)

AOI invokes an external helper and two approved compiled .pyc assets. Hash verification and discarded console output are visible, but internal prompt transformations are opaque and were not reverse engineered.

**Next action:** Obtain vendor transformation documentation and customer boundary traces; do not modify the approved wrapper or certify its hidden prompts.

## Proposed implementation sequence

1. Close PA-01/PA-02 outbound confidentiality gaps and PA-03 durable-memory truncation; invert their reproductions into acceptance tests.
2. Separate suggestion and executed-read policy; add missing-input termination in controller code before using the corresponding draft wording.
3. Unify evidence IDs, rendered-block citation validation and primary-ID budgeting; keep factual entailment distinct from citation membership.
4. Repair the three test-contract failures, remove or explicitly gate retired/standalone bundles, then run the focused suite and controlled provider integration.
5. Qualify live model safety, token fit, customer identity isolation and AOI transformations before claiming release-wide prompt assurance.

Replacement wording alone cannot fix any redaction, memory, schema, authorization or persistence defect. Existing business role constraints, source direction, immutable identities, approval boundaries and receipt verification must remain in place.
