# DT agent service integration

PMem keeps its governed data services. The DT runtime owns external agent
orchestration. Do not import its runtime into PMem or give agents database credentials.

## Gateway deployment

Lifecycle read authorization is default-deny. Set `OSLC_LIFECYCLE_READ_GRANTS`
to a JSON object mapping authenticated identities to resource grants, for example
`{"token-reader":["job-runs:example-run"]}`. A `job-runs:*` grant permits listing
and reading that kind. Supported kinds are job-runs, job-definitions and products.
Bootstrap graph-token callers share the fixed identity `token-reader`; use the
trusted gateway identity profile for separate user permissions. Caller-supplied
principal headers do not select the bootstrap identity. Never put this policy or
service credentials under agent control. Resource grants do not confer write rights.

Configure the PMem agentic process with `DT_AGENT_GATEWAY_URL`, an HTTPS gateway
base ending in the equivalent of `/api/v1`, and `DT_AGENT_GATEWAY_TOKEN` from the
deployment secret store. The gateway maps `/workflow/run/` to DT's existing
`/api/v1/workflow/run/`. Never put the token in a workflow or agent prompt.

Submit `POST /api/v1/integrations/dt-requirements-design/runs` to PMem with
`execution_scope: current_plan`, `query`, `email`, and the existing agentic approval
credentials (or trusted gateway approver identity in Entra mode). Workflow IDs
are rejected: the inspected DT API uses a single stored plan and email session.
The run UUID is forwarded as `X-Correlation-ID`. Records use the PostgreSQL
`dt_agent_runs` registry. Read via the corresponding `/runs/{run_id}` endpoint
with a service bearer token in token mode, or an approved gateway identity.

`response_received` means DT returned a response, not completion or release.
`dispatch_uncertain` must be reconciled with DT before retry: the upstream API
does not provide an idempotency contract. No automatic retries are performed.

## Open integration work

PMem now exposes `/api/v1/integrations/dt-requirements-design/capabilities` and
registers 12 `dt-*` roles in its agent catalog. `/api/v1/runs` accepts their
allowlisted tools. Data-product roles can discover versioned job definitions,
execute an approved job, and inspect its evidence and catalog product versions.
For analytics use a definition of type `schema-analytics-product` with quality
profile `schema-analytics-v1`; discovery does not create or approve that definition.
Execution remains subject to both agent approval and downstream service controls.
The external OSLC-only client must be explicitly extended before it can invoke
these agentic endpoints; do not route it around its current transport policy.

- DT currently exposes read-only OSLC coded tools. It cannot yet invoke PMem
  GraphRAG, job submission, status, or approval hand-off as one workflow.
- DT requires workflow-specific selection and authenticated session ownership
  instead of the global plan/email model before multi-user production use.
- Gateway route, credential provisioning, end-to-end traces and live execution
  are not verified. No credentials or external deployment were changed.
- PMem compatibility reports assess catalog mappings only, never runtime readiness.
- External agent output remains advisory. Graph writes must pass canonical
  validation and publication approval; this bridge does not publish anything.

Verification: five focused compatibility and mocked gateway tests pass. This is
not customer acceptance or validation of every external agent/tool.
