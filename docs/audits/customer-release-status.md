# Customer release status — 2026-10-02

This update includes local/Azure gateway routing, runtime browser configuration, scoped API credentials, explicit Windows installation guidance, ontology registration validation, graph visualization corrections, durable worker recovery and fenced run updates, artifact persistence safety, and product packaging/revocation fixes.

Validation: 18 focused Python regression tests passed; browser routing and graph normalization/query handling checks passed; production API-key, runtime configuration and local/gateway PowerShell checks passed; package integrity validated 46 PowerShell scripts, ten services, two workers and seven SQL migration files. Gateway HTTP tests were simulated.

Acceptance checks still required on the deployment VM: complete dependency installation and production frontend build; real PostgreSQL migration/concurrency tests; Neo4j registration/publication/readiness; actual worker job execution; browser end-to-end testing; and real Azure APIM connectivity/authentication if gateway mode is enabled. This commit is not evidence that those checks passed.

The app currently provides control-plane/catalog storage and an ontology analytics view. Dedicated dimensional analytics fact/dimension tables and warehouse loading jobs remain unimplemented. See the catalog/product/analytics audit.

Customer secrets are not included. Earlier credentials persisted in product records require customer-controlled cleanup and rotation. Deploy the complete branch and follow INSTALLATION.md rather than mixing partial file overlays.
