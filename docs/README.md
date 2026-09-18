# Documentation map

- [Current service/API catalog](architecture/SERVICE_CATALOG.md)
- [Deployment instructions](../infra/deployment/README.md)
- [Application and plugins](APP_AND_PLUGIN_INSTALLATION.md)
- [Delivery tracker](ACCELERATED_DELIVERY_TRACKER.md)
- [Current sequence](CURRENT_ARCHITECTURE_SEQUENCE.md)
- [Semantic governance](SEMANTIC_GOVERNANCE_CONTRACT.md)
- [Lambda pipeline design](SEMANTIC_INTEGRATION_LAMBDA_PIPELINE.md)

## Repository boundaries

`backend/*_service` and `backend/qif` contain deployed API services.
`backend/depo_platform` contains shared runtime infrastructure. `backend/ceim`
and `backend/ontology_service/domain` contain canonical and ontology domain
logic respectively. Ingestion browser/export HTTP adapters live in
`backend/ingestion_service/api`. Contract tests live in `backend/tests/contracts`.
`backend/Services`, `backend/core` and
`backend/routes` remain shared dependencies of active services; they cannot be
removed until callers are migrated. `backend/tests` contains regression tests;
manual live scripts excluded by conftest are not release certification.

`plugins` contains optional MBSE packages; `standalone` contains separately
packaged tools. `infra` owns deployment and runtime scripts. `data`, `uploads`,
`ontology_uploads`, and external standards folders may hold customer evidence
or parser inputs and must not be treated as disposable source clutter.
