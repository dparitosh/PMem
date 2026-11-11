# Workflow engine and workspace responsibilities

PMem uses the existing durable job and agent runtimes. The browser selects scope, submits an authorized intent and follows retained execution; it does not own execution. This contract covers Change Control, Data Flow, Ontology Junction, Data Catalog, Data Products and Metadata Registry.

## Execution ownership

| Layer | Responsibility | Existing implementation |
| --- | --- | --- |
| Definition | Versioned job/workflow and input contract | `backend/data_pipeline_service/job_definitions.py`, `backend/agentic_service/durable_workflows.py` |
| Acceptance | Authorization, immutable input, run identity and duplicate protection | `backend/data_pipeline_service/run_records.py`, `backend/data_pipeline_service/rest_submissions.py` |
| Execution | PostgreSQL lease, heartbeat, original deadline and fenced writes | `backend/data_pipeline_service/worker.py`, `backend/agentic_service/worker.py` |
| Agent and tools | Retained proposal, evidence and tool-boundary controls | `backend/agentic_service/workflow_control.py`, existing Governor and Steward workflows |
| Evidence | Content-addressed artifacts, run outputs and owning-service receipts | `backend/artifact_store.py`, pipeline result APIs and product outbox |
| Presentation | Scoped history, guarded reads, explicit control requests and receipt links | `frontend/src/Components/PageTaskWorkspace.js`, `frontend/src/workflows/workspaceContracts.js` |

Domain imports retain their own workflow histories. The page task list is scoped agent history, not an aggregate of every import, job and product publication. Existing Import tasks are not silently migrated into another queue.

## State and authority

Execution progresses from accepted/queued to running and then completed, failed, timed out or cancelled. A pause/cancel request is acknowledged at a safe tool boundary; it is not proof that an in-flight write stopped. Interrupted writes require receipt reconciliation. A browser timeout or lost acknowledgement does not authorize a replay. Approval and delivery are separate dimensions; completed execution never creates approval by implication.

The server owns allowed control actions. Reconnect, access expiry, page change and task selection invalidate browser evidence. Late responses cannot restore controls or confirm an action for an earlier selection. A generation guard protects control acknowledgements, while request aborts protect reads. A synchronous control lock prevents duplicate local submissions. Aborted history requests cannot schedule another polling loop. Access rejection stops periodic reads until verification or manual refresh; transient read failures use bounded backoff. Hidden workspaces stop polling and refresh on return. Controls inside collapsed investigation sections do not initialize agent configuration.

## Workspace handoffs

| Workspace | User operation | Authoritative next evidence |
| --- | --- | --- |
| Change Control | Inspect authorization, execution and delivery | Owning workflow, not an inferred end-to-end approval |
| Data Flow | Choose approved job, execute retained input, review output | Run result, publication receipt and product draft |
| Ontology Junction | Governor proposes, Steward assesses, authorized user releases | Selected ontology/mapping version and publication receipt |
| Data Catalog | Discover sources and released product versions | Exact product version, lineage and catalog delivery |
| Data Products | Select retained evidence, validate and publish | Immutable package and independent catalog delivery |
| Metadata Registry | Govern source definitions and semantic release versions | Lifecycle evidence; separate from dataset preparation |

Shared guidance uses these handoffs across all six workspaces. It does not add an alternative approval form or bypass the owning service. Page collections and domain panels remain capability-specific.

## Persistence and recovery

PostgreSQL owns job definitions, durable runs, leases, submission receipts, control-plane metadata and analytics tables. Immutable source/output bytes are referenced by artifact identity. The graph contains published semantic projections; graph presence does not replace a run manifest or an approval record.

REST acquisition is a bounded, read-only child process. Shared deployments use the shared Python runtime. Isolated deployments reuse the already installed ontology dependency runtime for Semantica; the pipeline API and worker remain lean. The child neither persists records nor publishes them. Its parent retains the acquisition result and owns the job lease and subsequent writes. The absolute timeout and child watchdog still apply.

## Acceptance boundaries

Tests cover reconnect, late responses, polling cancellation, selected-task scope, worker/control behavior and the six workspace contracts. Customer-origin acceptance, real external connector credentials, production load and business-specific semantic conformance are separate checks. No external LLM is required for the shared workflow controls or REST acquisition.
