# Production deployment boundaries

DEPO runs directly as process-managed services; Docker Compose is not part of
the deployment model. Configure each service with `DEPO_DATABASE_URL` and
`DEPO_DATABASE_SCHEMA=semantic` for the
shared PostgreSQL database and run it through the organization’s process or
application-service manager.

For production, Azure API Management must be the only public ingress. Configure
each service with `AUTH_MODE=entra` and `REQUIRED_APPROVER_ROLE` (default:
`DataProduct.Approver`). APIM must validate Entra bearer tokens and inject the
standard `x-ms-client-principal` header only after validation. The backend then
uses that authenticated identity for product and mutating-agent approvals.

The control-plane registry uses PostgreSQL. Immutable binary artifacts are
content-addressed under `ARTIFACT_STORAGE`;
producers return `artifact_id` values which are the only supported input to the
Data Product API.

## Customer release controls

Use a dedicated PostgreSQL application role with only the permissions needed on
the `semantic` schema. Do not deploy using the PostgreSQL administrator role or
local development credentials. Schema changes are applied through the
versioned `depo_schema_migrations` table when a service starts; take and verify
a database backup before applying a new release.

All public traffic terminates at Azure API Management with TLS and Entra token
validation. DEPO services must bind only to a private interface. Configure
`ALLOWED_ORIGINS` and `OSLC_BASE_URL` with the customer HTTPS hostnames.
Run `infra/windows/test-depo-release.ps1 -Production` against the deployment
environment before handoff. Configure Neo4j with a customer-managed
least-privilege graph role and a TLS URI (`neo4j+s://` or `bolt+s://`), then
verify the target ontology database and its backup/restore procedure.
