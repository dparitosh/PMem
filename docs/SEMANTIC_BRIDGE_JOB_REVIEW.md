# Semantic Bridge job review — 2026-09-22

Scope: current source definitions, frontend routing, workflow execution and
approval behavior. No production jobs, database writes or customer tasks were
executed during this review.

Recheck: all five findings remain in the current files. The isolated control-flow
harness additionally confirmed that an empty `approved_mappings` list still
passes an automatically selected candidate to the graph writer, and omitting
`apply_links` also invokes that writer. Preview memory/event calls and discarded
manual approval were reproduced again. All effects were captured by in-memory
stubs; no graph connection, real memory update or HTTP request was made.

## Findings

1. **P1 — graph-mutating workflow execution bypasses approval identity.**
   `backend/agentic_service/router.py:132` exposes `/api/v1/workflows/execute`
   without `Request`, an authorization dependency or `approval_identity`.
   The shared app factory adds correlation/CORS middleware, not authentication.
   `instance.link` defaults `apply_links` to true at
   `backend/Services/semantic_workflow_service.py:1200` and directly writes
   Neo4j. A caller able to reach this service can therefore invoke mutations
   without the approval checks used by the other agent execution routes.
   Require verified write identity and explicit mutation intent before dispatch.

2. **P1 — applying mappings can include mappings the user did not approve.**
   `frontend/src/Components/OntologyMapper.js:2171` sends the approved subset,
   but `semantic_workflow_service.py:1204` regenerates candidates and line 1228
   selects all automatically eligible candidates as well. An empty submitted
   approval list does not mean “apply none”; removing approval in the UI does
   not exclude an automatically selected mapping. Only return/report the current
   candidate set during preview; apply an explicit reviewed selection tied to
   that preview, or expose auto-apply as a separate authorized operation.

3. **P2 — manual approval of an existing candidate is discarded.**
   `semantic_workflow_service.py:1211–1227` deduplicates incoming approved rows
   against generated candidates by row/target/type. When the same candidate
   exists but was not automatically selected, the approved replacement is
   skipped and its `selected_for_apply` flag remains false. Users cannot apply
   that reviewed mapping through this path. Merge validated approval metadata
   into the existing candidate instead of silently discarding it.

4. **P2 — preview produces approved memory and modification notifications.**
   `semantic_workflow_service.py:1265` calls approved-mapping memory storage even
   for `apply_links=false`; line 1286 emits an OSLC Modification event regardless
   of whether links were applied. When memory is enabled, preview suggestions
   can become reusable approved facts, and downstream consumers see changes
   that did not occur. Persist review artifacts separately; update approved
   memory and emit modification events only after a successful graph mutation.

5. **P2 — workflow artifact downloads are missing from the routed service.**
   `frontend/src/config.js:152` routes `/api/v1/workflows/*` to the agentic service,
   including the artifact URL at line 279. That service has no artifact download
   route; it exists only in `backend/main.py:5020`, which the supported launcher
   does not start. Generated report/export links therefore return 404 in the
   standalone topology. Add the download contract to the owning service with
   appropriate authorization and path containment checks.

## Workflow inventory

These are direct synchronous workflows dispatched by
`SemanticWorkflowService.execute`, not scheduled Spark jobs:

| Workflow | Role |
| --- | --- |
| `instance.link` | Preview/apply instance-to-ontology mappings; writes semantic graph links when enabled |
| `ontology.merge` | Generate overlap/addition/conflict plans; actual merge application is a separate API |
| `ontology.validate` | Generate ontology validation report |
| `dictionary.generate` | Generate review dictionary artifacts |
| `taxonomy.generate` | Generate taxonomy artifacts |
| `graph.chunk` | Generate chunked graph artifacts |

The UI explicitly invokes `instance.link` for preview/application and
`ontology.merge` for planning. The CLI exposes all six workflows. Runs retain
artifact manifests but this dispatch path provides no durable asynchronous queue
or scheduler; a five-minute browser timeout is not job completion tracking.

The four seeded data-pipeline jobs are related semantic-processing utilities,
but there is no direct invocation from the Bridge handlers reviewed:
`semantic-source-validation` (`validate-semantic-batch`),
`rdf-quality-statistics`, `rdf-deduplicate-serialize`, and
`document-evidence-enrichment` (`enrich-document-evidence`). They have a separate
handler registry, execution API and approval controls. Spark provisioning alone
does not repair the Bridge workflow issues above.

## Verification

Static route/factory inspection confirms the missing approval and download
contracts. An isolated harness executed the actual `link_instances` method
extracted from the source, with graph/artifact/memory/event dependencies replaced
by in-memory stubs. It reproduced preview memory/event calls and discarded
manual approval. This checks method control flow, not real Neo4j behavior or
HTTP authorization. The complete application test suite was not run because
the application's dependencies are not installed. No Bridge code was changed.


## Remediation implementation

The saved-preview and reviewed-publication path and supporting UI are implemented. See [Semantic Bridge jobs](SEMANTIC_BRIDGE_JOBS.md) for operation, authorization, recovery, validation scope, and remaining customer release checks. Earlier findings above describe the audited behavior before this change.
