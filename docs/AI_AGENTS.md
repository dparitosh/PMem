# PMem AI agents and orchestration reference

**Inventory date:** 23 October 2026 (Asia/Calcutta).
**Source baseline:** `codex/windows-setup-audit-fixes`, commit `1a56548674a3d401e44b3a5edc51203c23c9dd59`.

The effective application registry contains **28 registered roles: 16 platform agents and 12 DT integration roles**, with **53 registered tools** and **6 named workflows**. These are roles sharing the configured model and service infrastructure; they are not 28 independently trained models or proof of 28 running processes.

**Runtime verification:** the local agent endpoint at `http://127.0.0.1:8012/api/v1/agents` refused the connection during this inventory. The roles below are verified from the effective source registry, including dynamically added DT bindings. Their current availability, model access and downstream dependencies were not verified live. No service was started or data changed to generate this document.

## 1. Platform agents

UI contexts identify where a role is relevant or used by the application. They do not imply a dedicated visible button for every role.

| Agent ID | Display name | Business responsibility | UI / workflow context |
|---|---|---|---|
| `ontology-intake` | Ontology Intake | Inspect retained RDF/OWL or engineering source evidence. | Import / ontology preparation |
| `ontology-structure-review` | Ontology Structure Review | Review declared classes, properties and observable structural issues. | Ontology Junction: structure review |
| `semantic-bridge-planner` | Semantic Bridge Planner | Prepare grounded mapping candidates and unresolved validation checks. | Semantic Bridge: candidate preparation |
| `ontology-export` | Ontology Export | Export an approved ontology through its service contract. | Ontology export |
| `ontology-orchestrator` | Ontology Orchestrator | Sequence deterministic intake, structure review and mapping planning. | Ontology preparation workflow |
| `context-analyst` | Business Context Analyst | Search business context and update context objects after approval. | Business context / Where Used |
| `ontology-governor` | Ontology Governor | Propose registration, lifecycle changes, merge and mapping publication for server-authorized review; never grant approval. | Ontology Junction / instance linking |
| `engineering-parser` | Engineering Parser | Inspect engineering files and execute bounded source profiles. | Engineering source import |
| `graph-analyst` | Graph Analyst | Investigates graph evidence and recommendations using registered read tools; can plan a retained read-only goal and explain the Semantica policy findings. | Recommendations / Graph Explorer / guided investigations |
| `oslc-link-agent` | OSLC Link Agent | Read linked resources and synchronize approved remote OSLC data. | OSLC integrations |
| `schema-set-agent` | Engineering Schema-Set Agent | Inspect schema sets and commit reviewed QIF tasks. | QIF / schema-set import |
| `data-product-governor` | Data Product Governor | Preview, publish and revoke approved retained evidence packages. | Data Products / Catalog governance |
| `ceim-mapper` | CEIM Mapper | Normalize supplied records against the CEIM contract. | Instance normalization / data processing |
| `data-quality-monitor` | Data Quality Monitor | Inspect pipeline telemetry and request approved transformations. | Data Flow / Data Quality |
| `ontology-steward` | Ontology Steward | Evaluates the saved merge or instance-link preview; explains accepted/held decisions, validation coverage and missing evidence. | Merge and instance-link review |
| `ontology-inference` | Ontology Inference Advisor | Investigates rule-based inference previews and declared ontology structure, with evidence and limitations. | Inference Workbench |

### Platform tools and approval boundaries

Approval below follows the dispatcher: role-level approval **or** a mutating tool **or** an operation-specific approval contract triggers review. A catalog value of `approval_required=false` does not authorize writes. Automatic modes still require their configured server authorization and policy; the model cannot approve itself.

| Agent ID | Allowlisted tools | Approval boundary |
|---|---|---|
| `ontology-intake` | `engineering.inspect`, `ontology.generate`, `ontology.agent.intake` | No role-level approval; registered read contracts still apply. |
| `ontology-structure-review` | `ontology.agent.review` | No role-level approval; registered read contracts still apply. |
| `semantic-bridge-planner` | `ontology.agent.bridge-plan` | No role-level approval; registered read contracts still apply. |
| `ontology-export` | `ontology.export` | Every action through this role. |
| `ontology-orchestrator` | `ontology.agent.orchestrate` | No role-level approval; registered read contracts still apply. |
| `context-analyst` | `context.upsert`, `context.search`, `context.where_used` | Operation-specific: `context.upsert`. |
| `ontology-governor` | `ontology.register`, `ontology.transition`, `ontology.export`, `ontology.merge.preview`, `ontology.merge.apply`, `bridge.mapping.preview`, `bridge.mapping.publish`, `engineering.publish`, `bridge.mapping.publish_automatic`, `ontology.merge.apply_automatic` | Every action through this role. |
| `engineering-parser` | `engineering.inspect`, `profile.inspect`, `profile.execute` | No role-level approval; registered read contracts still apply. |
| `graph-analyst` | `graph.analytics`, `graph.neighborhood`, `context.search`, `context.where_used`, `oslc.graph_rag`, `recommendation.change_impact`, `recommendation.similar_parts`, `recommendation.manufacturing` | No role-level approval; registered read contracts still apply. |
| `oslc-link-agent` | `oslc.remote.catalog`, `oslc.remote.query`, `oslc.remote.sync` | Operation-specific: `oslc.remote.sync`. |
| `schema-set-agent` | `schema-set.standards`, `schema-set.upload`, `qif.task.status`, `qif.task.commit` | Operation-specific: `qif.task.commit`. |
| `data-product-governor` | `data.catalog.products`, `data.product.preview`, `data.product.publish`, `data.product.revoke` | Every action through this role. |
| `ceim-mapper` | `ceim.contract`, `ceim.normalize.batch` | No role-level approval; registered read contracts still apply. |
| `data-quality-monitor` | `pipeline.telemetry`, `pipeline.transform`, `pipeline.run` | Operation-specific: `pipeline.transform`, `pipeline.run`. |
| `ontology-steward` | `bridge.mapping.evaluate`, `ontology.merge.evaluate` | No role-level approval; registered read contracts still apply. |
| `ontology-inference` | `ontology.inference.preview`, `ontology.reasoning.inspect` | No role-level approval; registered read contracts still apply. |

## 2. DT integration roles

These 12 roles are added by `dt_bindings.extend_catalog`. They reuse platform service tools. Registration does not mean an external DT client is connected. The external DT gateway is controlled separately by `DT_AGENT_ENABLED`; local role execution still follows its tool-specific authorization and dependency checks.

| Role ID | Responsibility | Allowlisted tools | Approval boundary |
|---|---|---|---|
| `dt-intake` | Inspect engineering inputs, register approved ontologies and discover configured data jobs. | `engineering.inspect`, `ontology.register`, `pipeline.definitions` | Operation-specific: `ontology.register`. |
| `dt-domain-identifier` | Read domain contracts and business context; produce a reviewable classification. | `ceim.contract`, `context.search` | No role-level approval; registered read contracts still apply. |
| `dt-structure-review` | Select approved profiling jobs and inspect their retained evidence. | `pipeline.definitions`, `pipeline.run`, `pipeline.run.evidence` | Operation-specific: `pipeline.run`. |
| `dt-semantic-bridge-planner` | Normalize instance evidence before reviewed semantic alignment. | `ceim.contract`, `ceim.normalize.batch` | No role-level approval; registered read contracts still apply. |
| `dt-entity-conflict-review` | Inspect merge conflicts and retained job evidence without applying a merge. | `ontology.merge.preview`, `pipeline.run.evidence` | No role-level approval; registered read contracts still apply. |
| `dt-property-conflict-review` | Request approved quality jobs and inspect property-validation evidence. | `pipeline.definitions`, `pipeline.run`, `pipeline.run.evidence` | Operation-specific: `pipeline.run`. |
| `dt-context-graph-conflict-review` | Inspect where-used and neighborhood evidence for relationship conflicts. | `context.where_used`, `graph.neighborhood`, `pipeline.run.evidence` | No role-level approval; registered read contracts still apply. |
| `dt-data-product-interaction` | Discover job definitions and catalog versions; inspect retained run evidence. | `data.catalog.products`, `data.catalog.product`, `pipeline.definitions`, `pipeline.run`, `pipeline.run.evidence` | Operation-specific: `pipeline.run`. |
| `dt-kg-interaction` | Retrieve graph analytics and graph-grounded context. | `graph.analytics`, `graph.neighborhood`, `oslc.graph_rag` | No role-level approval; registered read contracts still apply. |
| `dt-export` | Export ontology evidence through the existing ingestion service. | `ontology.export` | No role-level approval; registered read contracts still apply. |
| `dt-self-learning-review` | Review retained evidence; never automatically promote lessons or change models. | `pipeline.run.evidence` | No role-level approval; registered read contracts still apply. |
| `dt-orchestrator` | Discover runs, jobs and catalog evidence for supervised workflow composition. | `pipeline.definitions`, `pipeline.runs`, `pipeline.run.evidence`, `data.catalog.products` | No role-level approval; registered read contracts still apply. |

The `dt-self-learning-review` role reviews retained evidence. It does not retrain a model, automatically promote lessons or change production rules. The `dt-orchestrator` binding currently discovers and reads jobs/runs/catalog evidence; its name alone does not grant permission to launch arbitrary workflows.

## 3. Registered named workflows

| Workflow ID | Purpose | Registered sequence |
|---|---|---|
| `data-product-governed-publication` | Validate and publish retained data-product evidence | `data-product-governor` / `data.product.preview` → `data-product-governor` / `data.product.publish` |
| `engineering-governed-publish` | Engineering schema to governed ontology | `ontology-intake` / `engineering.inspect` → `ontology-governor` / `engineering.publish` |
| `business-context-enrichment` | Business object context enrichment | `context-analyst` / `context.upsert` → `context-analyst` / `context.where_used` |
| `ontology-review-and-bridge-plan` | Ontology intake, structure review and Semantic Bridge planning | `ontology-intake` / `ontology.agent.intake` → `ontology-structure-review` / `ontology.agent.review` → `semantic-bridge-planner` / `ontology.agent.bridge-plan` |
| `bridge-validated-automation` | Validated instance mapping and publication | `ontology-governor` / `bridge.mapping.preview` → `ontology-steward` / `bridge.mapping.evaluate` → `ontology-governor` / `bridge.mapping.publish_automatic` |
| `ontology-union-automation` | Conflict-free ontology union draft | `ontology-governor` / `ontology.merge.preview` → `ontology-steward` / `ontology.merge.evaluate` → `ontology-governor` / `ontology.merge.apply_automatic` |

- **Governor and Steward:** the Governor prepares or submits a governed operation; the Steward evaluates the retained preview. A prepared preview, policy evaluation, draft application and verified Neo4j publication are different outcomes.
- **Read-only goals:** a model-assisted investigation is dynamically planned over registered read tools through the existing goal worker. It is not an extra agent or one of the six fixed workflow definitions.
- **Single-tool workflows:** these can be generated for an existing reviewed tool operation; they do not create another model or expand its allowlist.

## 4. What the agent actually does

| Stage | Application behavior | Evidence / limit |
|---|---|---|
| Perception | Reads retained source artifacts, ontology declarations, graph context or job evidence through the selected role’s tools. | Available sources and exact IDs constrain the task; missing data must be reported. |
| Planning | A read-goal investigation uses the configured OpenAI, Mistral or Ollama model to propose a bounded plan and allowed read actions. | Ordinary deterministic service execution is not automatically an LLM planning run. |
| Action | The controller validates the tool contract, source scope and authorization, then calls the owning service. | Tool discovery does not grant permission; writes stay behind existing approval contracts. |
| Memory and recovery | PostgreSQL retains goals, plans, observations, workflow state and task references. The agent can revise a failed read within its execution budget. | Repeated identical reads and unauthorized scope changes are rejected; uncertain writes are not silently replayed. |
| Result | The UI presents conclusions, source observations, policy findings and retained task status. | A completed task does not prove publication, semantic equivalence or engineering safety. |

## 5. Semantica, graph, memory and provenance

| Capability | Current integration | What it does not establish |
|---|---|---|
| Ontology generation and reasoning | The Ontology service wraps Semantica ontology, namespace and reasoning capabilities. | Every result is not a full OWL-DL consistency proof. |
| Decision intelligence | `semantica.ContextGraph.enforce_decision_policy` supports the shared policy assessment used by recommendations, ontology merging and instance linking. | No policy configured is different from a passed policy; a policy pass is not publication approval. |
| Context graph | Existing semantic business-context APIs use Semantica ContextGraph with retained context records. | This context store is not automatically the same as the published Neo4j graph. |
| Graph evidence | Neo4j services retrieve neighborhoods, dependencies and bounded matching candidates. | Heuristic similarity/impact scores are not calibrated confidence or exhaustive engineering analysis. |
| Agent memory | Read-goal scratchpads and workflows use PostgreSQL. The existing AgentMemoryService provides optional graph-native conversation/reasoning/approved-fact storage on other paths. | Not every agent call uses every memory backend, and there is no automatic model training. |
| Provenance and audit | Source IDs/hashes, saved preview IDs, publication receipts, policy assessments and operational telemetry. | These records are not by themselves a certified tamper-proof audit ledger. |

### Recommendations example

1. Choose Change Impact, Similar Parts or Process Context and identify an existing graph object.
2. **Agent investigation + Semantica review** uses the existing `graph-analyst` and durable read-goal worker.
3. The selected recommendation tool retrieves graph evidence and calls the shared policy adapter.
4. The controller requires citation of the selected completed, untruncated recommendation observation with recognized policy evidence before completing the goal. It pins the analysis, object, result limit and supplied source scope.
5. The UI shows the cited graph result and decision-policy findings. **Direct graph analysis** uses the same graph/policy endpoint without agent planning.

Graph readiness, the configured model, registered tools, authorization and the workflow worker must all be available. The existence of a role or endpoint does not prove successful inference for current customer data.

## 6. Additional definitions and assistants outside the default role count

The following files are present in the repository but are **not additional entries in the 28-role default control-plane registry**. Their own loader/plugin/standalone deployment determines whether they execute.

| Definition | Location | Scope |
|---|---|---|
| `MBSE_Model_Agent` | [MBSE plugin agent](../plugins/mbse_plugin/agents/mbse_agent.yaml) | Model import, graph projection, SMW and Cameo template/validation tools; governed import requirements remain. |
| `SchemaSet_Ontology` | [Schema-set definition](../backend/qif/agents/qif_ontology.yaml) | Inspects companion XSDs and builds a consolidated ontology artifact. |
| Ontology Intake Agent | [Standalone intake definition](../standalone/ontology_agentic_service/AgentsRegistry/Agents/ontology_intake_agent.yaml) | Standalone service definition, separate from default registry discovery. |
| Ontology Review Agent | [Standalone review definition](../standalone/ontology_agentic_service/AgentsRegistry/Agents/ontology_review_agent.yaml) | Standalone ontology-review capability. |
| Ontology Alignment Agent | [Standalone alignment definition](../standalone/ontology_agentic_service/AgentsRegistry/Agents/ontology_alignment_agent.yaml) | Standalone alignment preparation capability. |
| Ontology Export Agent | [Standalone export definition](../standalone/ontology_agentic_service/AgentsRegistry/Agents/ontology_export_agent.yaml) | Standalone export capability. |
| Knowledge Companion | [Companion service](../backend/agentic_service/companion.py) and [user reference](KNOWLEDGE_COMPANION.md) | Evidence-grounded conversational assistant; not another named default catalog role. |
| LangGraph chat implementation | [Chat source](../backend/agent/chat.py) | Separate graph/vector conversational implementation retained in the codebase; source presence alone does not prove use by the current Companion UI. |

The default catalog also declares a Semantica MCP server. An MCP server is a tool transport, not an agent; registration alone does not prove the process is running or that a particular role invokes it.

## 7. Operational prerequisites and current verification

- The agent service, owning domain services and durable workflow worker must be running.
- The selected provider/model and required credentials must be configured; a successful service startup is not proof of model inference.
- Selected source data and graph context must exist. Empty graph results are not evidence of no engineering impact.
- Approval identities and tokens remain server-enforced; they must not be supplied by the model.
- Role discovery is available through `/api/v1/agents`; tools through `/api/v1/tools`; fixed workflows through `/api/v1/workflows`; architecture through `/api/v1/agent-architecture` with its access checks.
- This inventory confirms registration and source boundaries. It is not an end-to-end acceptance report for all 28 roles.

## 8. Authoritative code references

- [Default agent/tool/workflow catalog](../backend/agentic_service/catalog.json)
- [Effective catalog loader](../backend/agentic_service/catalog_loader.py) and [catalog validation](../backend/agentic_service/catalog_contract.py)
- [DT role bindings](../backend/agentic_service/dt_bindings.py)
- [Agent descriptions and architecture](../backend/agentic_service/agent_usage.py)
- [Dispatcher and approval calculation](../backend/agentic_service/router.py) and [operation approval mapping](../backend/agentic_service/transport_auth.py)
- [Read-goal routes](../backend/agentic_service/goal_routes.py), [planning controller](../backend/agentic_service/goal_runner.py) and [recommendation completion contract](../backend/agentic_service/recommendation_goals.py)
- [Shared decision-policy adapter](../backend/depo_platform/decision_policy.py) and [Semantica intelligence integration](../backend/ontology_service/intelligence.py)
- [Page task profiles](../frontend/src/services/pageTasks.js)
- [Existing semantic-agent architecture reference](SEMANTIC_AGENT_ARCHITECTURE.md)

## Local permission, hook and MCP audit — 24 October 2026

This review covers PMem repository implementation, not permissions enforced by the coding assistant host. It reviews the proposed Strict Permission Guard / hook pipeline / local-tool architecture against actual code.

| Proposed capability | Verified implementation | Gap / implication |
|---|---|---|
| Interactive approval on every edit | `router.plan` derives required authorization from agent role, tool mutation classification and operation contracts. `_dispatch` checks approval before execution; `approval_identity` validates configured tokens or trusted gateway roles. `AgentProposalPanel` presents the inputs, approver and review checkbox. | This is governed application execution, not a generic per-file-edit prompt. The checkbox is client-side; possession of valid server authorization permits direct API calls. Automatic publication modes are separately authorized and governed. |
| Mandatory git diff / static lint hook pipeline | Tests and diff checks can be run in the development workflow. | No tracked `.githooks`, `.husky`, pre-commit configuration or `.github` hook pipeline was found, and no `core.hooksPath` was configured. The frontend package has no lint script. Reported manual validation is not an enforced runtime pre-write hook. |
| Built-in local patch / filesystem reader | Default registered tools are service/OpenAPI contracts. | Generic local patch and workspace file-reader tools are not registered. Artifact-backed engineering reads are not permission to read arbitrary filesystem paths. |
| Local stdio MCP servers | Operator-configured commands, restricted inherited environment, bounded request/response sizes and deadlines, initialize/discovery validation, per-operation session isolation, progress handling and process teardown. | The default catalog has one Semantica server descriptor and zero MCP-bound tools. Discovery is not proof of successful vendor execution. Child processes run as the application OS user; stdio and environment filtering do not enforce filesystem/network isolation. |
| Agents | Existing role/tool allowlists, server approval contracts and retained workflow records. | Agents do not independently authorize writes. A scoped service credential is not evidence of a fresh human decision on every operation. |

### Findings and recommended boundaries

1. If the product requirement is strict per-action human approval, bind an approval to a saved action/preview ID, canonical input digest, authenticated principal and expiry; reject modified, expired or consumed approvals at dispatch. Existing publication-specific preview/review controls should be reused. A UI confirmation alone is not a server permission boundary.
2. If local coding tools are introduced, give them a separate optional execution profile with canonical allowed roots, symlink/junction escape checks, bounded reads, atomic writes and rollback. Add OS-level isolation or a restricted service account for MCP children; restricted environment variables alone are insufficient.
3. A pre-write validation hook should run fixed allowlisted checks without executing model-provided shell commands. Retain exit codes and redacted diagnostics, and distinguish validation failure from approval. `git diff --check` checks whitespace; it is not static lint, semantic validation or authorization.
4. MCP `readOnlyHint` is advisory metadata. Current preflight rejects an explicitly mutating native hint when the catalog says read-only; absent hints are not proof of safety. Operator classification remains trusted configuration. Strict local-write profiles need fail-closed tool classification and an explicit downstream approval contract.

Validation: **9 targeted tests and 4 subtests passed** covering scoped stdio reuse/shutdown, diagnostics, progress and Bridge approval contracts. These use synthetic subprocess servers and isolated service boundaries; they do not certify a live Semantica server, OS sandbox, interactive edit guard or hook pipeline. No permission settings, credentials, server bindings or runtime execution policies were changed by this audit.
