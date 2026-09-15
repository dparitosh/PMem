# OSLC lifecycle development checkpoint

The OSLC service exposes `/oslc/lifecycle` with read-only job definitions,
job-run summaries and catalog product versions. Resource reads support JSON,
Turtle, RDF/XML and JSON-LD, conditional ETags and allowlisted summary fields.
Collection identifiers are paged in PostgreSQL. These are PMem extension
resources, not a certified standardized domain implementation.

Configure `OSLC_LIFECYCLE_READ_GRANTS` as an identity-to-grants JSON object:
`{"token-reader":["job-runs:example-run"]}`. Collection access requires a
kind-wide grant such as `job-runs:*`. No grants means access denied. Bootstrap
token readers share `token-reader`; use gateway identities for distinct users.
Entra deployments also require `DEPO_TRUSTED_GATEWAY_IPS` and gateway-enforced
identity validation. Keep grants deployment-owned, not agent-controlled.

Verified locally with focused OSLC and gateway tests. Still pending: lifecycle
TRS, governed writes, external DT client bindings, full content negotiation,
and customer authentication/install/restart/recovery acceptance. This checkpoint
is not authorization for production release. Existing endpoints outside this
extension retain their existing contracts.
