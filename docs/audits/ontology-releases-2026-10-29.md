# Ontology releases and recovery follow-up

## Implemented

- Immutable family/version/predecessor declarations over exact catalog artifacts.
- Existing ontology approval authorization; read credentials cannot declare releases.
- PostgreSQL namespace `ontology_releases_v1`, using existing registry tables, advisory locks and atomic multi-record persistence.
- Linear successor history, increasing semantic version and reviewer-declared change classification. Same-input retries are idempotent.
- Declared artifact checks before publication queueing and actual dispatch; mismatch prevents graph writes.
- Existing publication panel exposes release history and declaration, with cancellation on selection/access changes and duplicate-click protection.
- Legacy registrations remain explicitly unversioned. Semantica snapshots remain independent. No automatic instance remapping, compatibility proof, ontology approval, retirement or graph publication is introduced.

## Executed verification

- 68 backend tests passed across release API authorization/schema, release lineage/concurrency/failure cases, catalog, publication receipts, background jobs, release packaging and recovery regressions. `outputs/release-lineage-tests.xml` records the run.
- A further 38 adjacent publication tests passed, including deadlines, response loss, phase limits and migration. The old RDF publication fixture was corrected to execute the current ingestion workflow: drafts require approval and approved publication uses the owning ontology service, never a direct graph bypass.
- 20 frontend tests passed across release UI and existing publication controls. `outputs/ontology-release-ui.xml` records the run. Existing React test deprecation/act warnings remain.
- Production Vite build passed (3,440 transformed modules). Existing large-chunk warnings remain.
- Recovery audit verified both current ontology files and isolated copies against their content addresses, and rechecked the retained graph backup checksum. Details and remaining recovery gates are in [recovery qualification](recovery-qualification-2026-10-29.md).

Tests use isolated stores for mutations. No live ontology was assigned a version or published by the tests. Model services were not called. Customer network/session acceptance, live LLM qualification and coordinated graph/PostgreSQL/import-artifact restoration remain separate release gates.

Machine-readable test results are retained in [the evidence directory](ontology-releases-2026-10-29/): 106 backend cases and 20 frontend cases across the documented runs.

## Installed local acceptance

The tested update was applied with code backup at `D:\GenAI_Projects\Apps\PMem\logs\prompt-audit-update\20261029-075919-1b8e2e5eac23436fa06dbf8b8a92d156`. The installed frontend was rebuilt with preserved deployment configuration and serves `/assets/index-B60DxmMO.js`. Managed startup completed; all ten API readiness endpoints and the frontend returned HTTP 200.

Both existing catalog ontologies returned HTTP 200 from their release-history endpoint and remained explicitly unversioned. Anonymous reads and read-only-session declarations were denied. Changed runtime modules matched workspace hashes. [Live evidence](ontology-releases-2026-10-29/live.json) records these checks. No live declaration, graph publication or model call was made. This is API/component/build verification; it is not customer-server or visual browser acceptance.

See [operator procedure and API example](../ONTOLOGY_RELEASES.md).
