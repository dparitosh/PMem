# Agentic service installation and API-key integration

This deployment uses `AUTH_MODE=token` (API keys). Entra is not required. The
Knowledge Companion retrieves and formats graph evidence; no LLM provider is
called by this implementation. Semantica MCP remains a separately registered
client process, not an HTTP tool executor.

## Install and configure

Use the root installer in [deployment instructions](../infra/deployment/README.md).
It creates `backend/.dt_venv`, installs `backend/requirements.txt`, imports the
agentic application and generates its OpenAPI document as a smoke check. Use
`-Development` to include the test dependencies. Root `.env.local` holds server
settings; frontend environment files must contain public URLs only.

Required for agentic operations: PostgreSQL (`DEPO_DATABASE_URL` and schema),
Neo4j connection settings, and the peer URLs injected by the Windows launcher.
The launcher includes `AGENTIC_SERVICE_URL=http://127.0.0.1:8012/api/v1` for
self-dispatched tools. Override each service URL for a distributed deployment.
Agentic configuration is validated before processes start. `/healthz` reports
process liveness; `/readyz` fails when configuration or shared dependencies are
missing/unavailable. Optional DT and remote OSLC are disabled by default; set
`DT_AGENT_ENABLED=true` or `OSLC_REMOTE_ENABLED=true` and configure the associated
URL/key fields to enable them. Timeouts and upload limits must be positive.

## API keys and approval

- Read requests use `GRAPH_READ_TOKEN` via `X-API-Key` or `Authorization: Bearer`.
  This protects chat, SSE, saved evidence, read-tool execution, workflow status,
  code-audit results, and OSLC retrieval.
- Approval uses `AGENTIC_APPROVAL_TOKEN` through either header, with
  `approved_by` in the request body. The existing `approval_token` body field is
  also accepted for compatibility. Reader keys cannot approve publication.
- Destination-specific approval credentials are selected server-side for
  ontology transitions, product publication, and pipeline execution. Clients
  cannot override the authenticated approver or inject a downstream token.
- Workflow approval is checked before persisting or dispatching any steps.
  The chat UI's API-key field retains the key only in component memory and
  sends it in a request header. Streaming responses use real SSE delimiters.

Keep keys in the server secret store, use distinct keys for each role/service,
terminate HTTPS at the customer reverse proxy, and redact credential headers
and approval fields from logs. Production validation accepts API-key mode and
requires at least 32-character keys. Token-mode `approved_by` is an audit label
supplied by the key holder, not an independently verified personal identity.

If an existing deployment uses optional Entra mode, downstream URLs must point
to HTTPS gateway API bases; the validated caller bearer token is preserved for
gateway revalidation. Raw identity headers are never forwarded by the dispatcher.

## Verification and remaining environment work

Run the agentic tests plus `infra/deployment/test-api-key-production.ps1`,
`infra/deployment/test-config-generation.ps1`, and the Windows prerequisite
checks. Run the installer and live release preflight on the target machine.
Focused tests use mocked peer services; they do not replace live PostgreSQL,
publication, or customer proxy acceptance tests. This workspace has not had a
complete `backend/.dt_venv` installation or PostgreSQL provisioning performed.
