# Customer release status — updated 2026-10-09

This is a working-tree status update against baseline `cea9484`; the latest fixes have not been committed or deployed. See [current validation](README.md) for test scope and remaining acceptance checks. Historical counts below describe the October 2 run only.

This update includes local/Azure gateway routing, runtime browser configuration, scoped API credentials, explicit Windows installation guidance, ontology registration validation, graph visualization corrections, durable worker recovery and fenced run updates, artifact persistence safety, and product packaging/revocation fixes.

Historical validation (October 2): 18 focused Python regression tests passed; browser routing and graph normalization/query handling checks passed; production API-key, runtime configuration and local/gateway PowerShell checks passed. Gateway HTTP tests were simulated. Old service/worker/migration counts are superseded by the deployment manifest and migration files in the selected revision.

Acceptance checks still required on the deployment VM: dependency installation and production build in that environment; real PostgreSQL migration/concurrency tests; Neo4j registration/publication/readiness; actual worker job execution; browser end-to-end testing; and real Azure APIM connectivity/authentication if gateway mode is enabled. Local production build has passed, but does not replace target-server acceptance.

The app provides control-plane/catalog storage, ontology analytics and an approved XSD/XML analytics materialization path. The latter validates inputs and creates a versioned structural PostgreSQL projection with source XML retention and optional explicit business views. It is not a complete dimensional business warehouse: cross-entity joins, units and history policies remain open. See [XML analytics status](xsd-relational-analytics-audit-2026-10-02.md).

Customer secrets are not included. Earlier credentials persisted in product records require customer-controlled cleanup and rotation. Deploy the complete branch and follow INSTALLATION.md rather than mixing partial file overlays.
