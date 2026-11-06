# Agent architecture and use of the 26 roles

The runtime catalog contains 26 service roles, 44 allowlisted tools and four predefined workflows. These are governed LLM-assisted workflows: the model recommends an action; catalog validation and authorization determine what can execute. A role is not a continuously running model or a separate autonomous worker. The catalog and `dt_bindings.py` are the executable sources of truth.

## How roles are used

| Scenario | Handoff and evidence |
|---|---|
| Ontology onboarding | Intake inspects source evidence; structure review checks declarations; bridge planning proposes mappings; governance authorizes registration and publication. |
| Semantic merge | Entity, property and context conflict reviewers inspect merge preview and graph evidence; governance applies a reviewed merge. Candidate mappings do not prove equivalence. |
| Data profiling and quality | DT structure/property roles select an existing versioned pipeline job, request an approved run, and inspect its retained evidence. Business rules must exist in the job definition; the LLM does not invent or silently install executable rules. |
| Data products and catalog | Data-product interaction retrieves jobs and catalog versions; the governor previews and publishes an approved package. Publication and catalog registration must succeed before counts increase. |
| Graph questions | Graph analyst and DT KG interaction retrieve scoped graph evidence for answers. Missing projection or permission errors must not be interpreted as successful empty evidence. |
| Learning review | Self-learning review examines retained job evidence for human review. It does not train models, promote mappings or change policy automatically. |

The UI selects a role and requests a reviewable proposal. Execution retains the catalog allowlist and tool-specific approval checks. Approved mutating single-tool requests now use the persisted workflow executor; reads remain bounded operations. In worker mode, the recommendation UI receives a queued workflow ID and inspects workflow status. Existing service callers may wait for completion. Pausing and cancelling cannot interrupt an active tool or undo completed writes.

## Runtime role mapping

| Role | Purpose | Allowlisted tools |
|---|---|---|
| ontology-intake | Inspect retained RDF/OWL or engineering source evidence. | `engineering.inspect`, `ontology.generate`, `ontology.agent.intake` |
| ontology-structure-review | Review declared classes, properties and observable structural issues. | `ontology.agent.review` |
| semantic-bridge-planner | Prepare grounded mapping candidates and unresolved validation checks. | `ontology.agent.bridge-plan` |
| ontology-export | Export an approved ontology through its service contract. | `ontology.export` |
| ontology-orchestrator | Sequence deterministic intake, structure review and mapping planning. | `ontology.agent.orchestrate` |
| context-analyst | Search business context and update context objects after approval. | `context.upsert`, `context.search`, `context.where_used` |
| ontology-governor | Review and authorize registration, lifecycle changes, merge and mapping publication. | `ontology.register`, `ontology.transition`, `ontology.export`, `ontology.merge.preview`, `ontology.merge.apply`, `bridge.mapping.preview`, `bridge.mapping.publish`, `engineering.publish` |
| engineering-parser | Inspect engineering files and execute bounded source profiles. | `engineering.inspect`, `profile.inspect`, `profile.execute` |
| graph-analyst | Read ontology analytics, neighborhoods and graph-grounded evidence. | `graph.analytics`, `graph.neighborhood`, `context.search`, `context.where_used`, `oslc.graph_rag` |
| oslc-link-agent | Read linked resources and synchronize approved remote OSLC data. | `oslc.remote.catalog`, `oslc.remote.query`, `oslc.remote.sync` |
| schema-set-agent | Inspect schema sets and commit reviewed QIF tasks. | `schema-set.standards`, `schema-set.upload`, `qif.task.status`, `qif.task.commit` |
| data-product-governor | Preview, publish and revoke approved retained evidence packages. | `data.catalog.products`, `data.product.preview`, `data.product.publish`, `data.product.revoke` |
| ceim-mapper | Normalize supplied records against the CEIM contract. | `ceim.contract`, `ceim.normalize.batch` |
| data-quality-monitor | Inspect pipeline telemetry and request approved transformations. | `pipeline.telemetry`, `pipeline.transform` |
| dt-intake | Inspect engineering inputs, register approved ontologies and discover configured data jobs. | `engineering.inspect`, `ontology.register`, `pipeline.definitions` |
| dt-domain-identifier | Read domain contracts and business context; produce a reviewable classification. | `ceim.contract`, `context.search` |
| dt-structure-review | Select approved profiling jobs and inspect their retained evidence. | `pipeline.definitions`, `pipeline.run`, `pipeline.run.evidence` |
| dt-semantic-bridge-planner | Normalize instance evidence before reviewed semantic alignment. | `ceim.contract`, `ceim.normalize.batch` |
| dt-entity-conflict-review | Inspect merge conflicts and retained job evidence without applying a merge. | `ontology.merge.preview`, `pipeline.run.evidence` |
| dt-property-conflict-review | Request approved quality jobs and inspect property-validation evidence. | `pipeline.definitions`, `pipeline.run`, `pipeline.run.evidence` |
| dt-context-graph-conflict-review | Inspect where-used and neighborhood evidence for relationship conflicts. | `context.where_used`, `graph.neighborhood`, `pipeline.run.evidence` |
| dt-data-product-interaction | Discover job definitions and catalog versions; inspect retained run evidence. | `data.catalog.products`, `data.catalog.product`, `pipeline.definitions`, `pipeline.run`, `pipeline.run.evidence` |
| dt-kg-interaction | Retrieve graph analytics and graph-grounded context. | `graph.analytics`, `graph.neighborhood`, `oslc.graph_rag` |
| dt-export | Export ontology evidence through the existing ingestion service. | `ontology.export` |
| dt-self-learning-review | Review retained evidence; never automatically promote lessons or change models. | `pipeline.run.evidence` |
| dt-orchestrator | Discover runs, jobs and catalog evidence for supervised workflow composition. | `pipeline.definitions`, `pipeline.runs`, `pipeline.run.evidence`, `data.catalog.products` |

## Customer deployment without Entra

The current customer installation uses registered service credentials and token-based sessions. Entra is not required for the 26 local roles or the token-authorized workflow worker. Connect the registered credentials in Admin, provide the required read/workflow scopes, and configure the worker with its approved service profiles. Setting agent flags alone does not create a browser session or grant tool permissions. Entra delegated-worker support is a future deployment concern, not a blocker for this installation.

## Configuration and remaining boundaries

- `DT_AGENT_ENABLED` controls the external DT gateway integration. Local DT roles use the existing PMem data and ontology services independently of this flag.
- Ontology and companion enablement flags permit their respective entry points; they do not bypass approval or dependency checks. Ollama route configuration must match the deployed APIM OpenAPI contract. Model-list availability does not prove generation, structured output or native tool calling.
- `AGENTIC_EXECUTION_MODE=worker` uses PostgreSQL queue ownership, retained write intent and reconciliation. The worker deployment currently supports service-token authorization. Entra user execution stays in process mode; delegated identity worker execution and distributed per-user limits remain incomplete.
- Sync REST, LangChain chat and embedding callers share per-process Ollama concurrency/circuit controls. Limits are not distributed across service processes. Capacity, transient failures and admission deadlines are bounded.
- MCP proposal schemas can be discovered for explicitly configured and allowlisted bindings. Discovery does not grant execution permission. No live MCP tool binding is assumed merely because a server is registered.
- Structural review and evidence citations are not formal semantic consistency proofs. Customer-data accuracy benchmarks and live reasoner evaluation remain required before claiming semantic assurance.

All 26 roles are registered, but live readiness depends on their services, credentials, retained data and model capabilities. Do not enable every role or run all roles for every request. Select the smallest relevant workflow and keep publication subject to human approval.
