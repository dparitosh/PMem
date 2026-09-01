# Production deployment boundaries

`compose.services.yml` is intentionally private-network-only. Use
`compose.services.dev.yml` only for local diagnostics; it publishes the service
ports on the host.

For production, Azure API Management must be the only public ingress. Configure
each service with `AUTH_MODE=entra` and `REQUIRED_APPROVER_ROLE` (default:
`DataProduct.Approver`). APIM must validate Entra bearer tokens and inject the
standard `x-ms-client-principal` header only after validation. The backend then
uses that authenticated identity for product and mutating-agent approvals.

The current SQLite control-plane registry is appropriate for one service
replica with a persistent volume. Replace it with PostgreSQL (or another
managed transactional store) before running multiple replicas or availability
zones. Immutable binary artifacts are content-addressed under `ARTIFACT_STORAGE`;
producers return `artifact_id` values which are the only supported input to the
Data Product API.
