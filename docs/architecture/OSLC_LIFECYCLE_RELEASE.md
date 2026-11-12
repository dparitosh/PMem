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


## Functional fixes verified 12 November 2026

Exact ontology scope no longer falls back to a matching prefix on a record with another explicit ontology ID. Generated resource links bind the ontology ID; an unscoped ambiguous IRI returns a conflict rather than an arbitrary revision. TRS Base eligibility excludes staged resources and publication receipts, matching resource GET behavior. PostgreSQL Base membership is streamed into 1,000-member pages; metadata is committed last and incomplete snapshots cannot be read as complete.

TRS RDF uses explicit `trs:change`, `trs:changed`, `trs:order`, event types and cutoff-event references. This correction is not independent TRS-client conformance certification: legacy event coverage, segment/retention behavior and external-client acceptance still require qualification. Native ontology publication now persists notification intent with its control-plane receipt; the existing catalog outbox worker retries idempotent delivery. This does not claim notifications for every graph writer.

Retained remote snapshots record provider, authenticated requester and digest. Admin → Data sources selects these snapshots and approved `oslc-snapshot-ingest` workflows for the existing worker; preparation produces connector records, which can enter the existing explicit CEIM mapping workflow. Incomplete snapshots and unproven legacy provenance remain blocked. Remote catalog/query capability traversal is same-provider and bounded. No grants, credentials or external providers are automatically enabled.


## Reporting replication

Migration 018 adds reporting feeds, resource/property/relationship tables and active-generation views in the existing PostgreSQL reporting database. Existing ontology artifacts and approved analytics marts remain separate. Run the normal schema upgrade before starting this release; no reset is required.

Reports → Reporting data creates an exact-ontology-version selection draft. Approve the selection and its `trs-reporting-sync` job through existing credentials and workflow approval. The existing pipeline worker initializes a hidden generation, then atomically promotes it and consumes tracked changes. Rows and checkpoints commit together. Expired Base snapshots restart staging while the last complete generation remains readable.

Automatic refresh uses the existing supervised pipeline scheduler and an approved job schedule. `DEPO_PIPELINE_SCHEDULER_ENABLED` must already be enabled intentionally; this release does not enable unrelated schedules. PostgreSQL TRS Base snapshots default to 3600 seconds, configurable through `OSLC_TRS_SNAPSHOT_TTL_SECONDS` (60–86400). File-mode snapshots retain their existing behavior.

Reports read PostgreSQL without traversing the source graph. Freshness covers the selected tracked feed; event coverage across all source writers remains partial. Resource/type/link counts are observed metrics, not customer-approved KPI formulas. `trs-reporting-export` freezes a repeatable-read snapshot for the existing product review flow; it does not approve or publish a product. External COTS TRS provider interoperability still requires separate acceptance testing.

Verification (2026-11-12): 1,046 frontend tests passed across 167 files; 37 reporting/scheduler/upgrade backend tests and 22 subtests passed, including six isolated PostgreSQL integration tests. Migration 018 and startup schema verification passed. All ten service contracts, three workers and browser-session diagnostics passed. The Reporting data page was verified in the restarted browser. Anonymous reporting reads and writes returned 403; an authorized reporting read returned 200. No application reporting selection was approved and no data product was published during verification. External COTS/TRS provider acceptance remains outstanding.

