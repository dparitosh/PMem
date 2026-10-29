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

## Central change visibility — implementation phase 1

The OSLC service now owns the read-only cross-workspace evidence API:

- `GET /api/v1/change-control/records?source=all&limit=25&offset=0`
- `GET /api/v1/change-control/records/{source}/{identifier}`
- Negotiated OSLC representations at the equivalent `/oslc/change-control/records` paths.

Registered graph-read access is required. This API intentionally projects only allowlisted review, execution, delivery, identity and digest fields; source documents, API keys, package paths and raw exception messages are excluded. Collection reads page each selected registry namespace independently. Source failures are explicit and an all-source failure returns 503. Counts concern loaded evidence records, not distinct end-to-end change requests. The UI entry is **Change Control** (`#/change-control`). Reconnect cancels stale reads and refreshes the view.

Existing merge previews are exposed as read-only OSLC CM ChangeRequest projections. Execution and other evidence records use a DEPO extension type. This does not introduce an OSLC-standard ChangeOrder class or claim conformance certification. The existing OSLC CM graph resource interface remains separate and unchanged. Lifecycle discovery links to the new evidence query; existing lifecycle-grant rules still apply to the older `/oslc/lifecycle` resources. The new central evidence API uses the same registered read-access boundary as the source application APIs; it does not grant approval or write access.

Review/authorization, execution and delivery remain separate fields. A completed validation run or passed policy assessment is not approval. Advisory learning approval does not authorize graph publication. Applying a merge to the ontology registry does not prove publication. Retained publication receipts are shown separately from currentness; new execution must revalidate in the owning workflow.

### Remaining CR/CO enforcement work

Phase 1 is centralized visibility, not centralized decision authority. Existing approve/publish controls remain authoritative in their owning services. Do not represent historical service records as globally approved change orders.

The next phase requires a PostgreSQL change-request revision ledger and execution orders with immutable source/preview/policy digests, role-bound decisions, an append-only decision history and stale-proposal checks. Each owner service must enforce the exact authorized order before replacing its current approval controls. Governor coordinates proposals and execution; Steward records assessments; only authorized reviewers or explicitly delegated policy grant bounded authority. Cross-service execution must retain idempotent step receipts and partial-failure recovery rather than claiming one distributed database transaction. Customer authentication and recovery acceptance are required before activating centralized write control.
