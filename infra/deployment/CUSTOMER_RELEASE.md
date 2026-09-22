# Customer setup and release acceptance

This is the release handoff record. Do not mark a delivery accepted until its
checks have run on the target Windows server. Repository syntax tests and
configuration mocks are not production certification.

## Installation order

1. Record the Windows version, service account, approved Python/Node/npm versions,
   network endpoints, storage locations and API-key access design.
2. Provision [PostgreSQL](../postgres/README.md) and [Neo4j](../neo4j/README.md). Record database owners,
   TLS trust, app-role privileges, backup and restore evidence.
3. If Spark is part of this delivery, provision the approved Spark/JDK/Hadoop
   runtime using the [Spark guide](../spark/README.md). PySpark comes from that
   Spark distribution; do not install a second unrelated PySpark version.
4. Follow the [application installation guide](README.md): configure server and
   browser settings, run prerequisite checks, install/build, then validate.
5. Run Spark smoke testing when enabled. Start with `-EnableSpark`; add the
   scheduler/Neo4j connector switches only when their features are required.
6. Configure the customer's process supervisor for ten APIs and the outbox
   worker in `services.json`. Demonstrate recovery after a process failure and
   server reboot. The supplied direct-process launcher is not a Windows service
   manager and does not by itself provide those guarantees.
7. Serve `frontend/dist` through the customer's HTTPS web server/gateway. Run
   Production endpoint validation, ReleasePreflight and an authorized browser
   workflow. Record a rollback point before opening access.

## Acceptance evidence

| Evidence | Required result |
| --- | --- |
| Release identity | Application archive hash/version and exact approved dependency inventory |
| Runtime supply chain | PostgreSQL/Spark/JDK/helper package sources, versions, signatures or approved hashes |
| Application install | Successful installer log, Python dependency resolution and frontend build |
| Automated tests | Local backend and frontend suites pass on the release build |
| Data stores | PostgreSQL/Neo4j live checks and backup/restore drill pass |
| Spark when included | Smoke job returns four expected records; enabled service reports configured runtime |
| API readiness | All ten service readiness/OpenAPI/OData checks pass |
| Authentication | Valid API keys permit authorized operations; missing/invalid keys are denied |
| Browser | Correct customer URLs and representative governed import/publication workflow |
| Operations | Reboot/crash recovery, log rotation, disk capacity/retention and monitoring exercised |
| Rollback | Previous build/configuration available; database recovery approved and rehearsed |

## Current release blockers

The repository does not yet contain a certified, fully pinned Python dependency
lock for this release. Generate and validate that lock on the target platform,
retain the matching package artifacts, and perform the dependency/license review
before packaging. Do not treat broad requirements ranges as a reproducible build.

Target-server provisioning, full installed-runtime integration tests, Spark execution, gateway and
supervisor recovery have not been performed in this workspace. Customer-specific
endpoints, approved binaries, credentials and host administration are required.
The legacy destructive cleanup utility also retains the configuration-precedence
finding in `docs/REPOSITORY_AUDIT.md`; do not include it as a supported customer
maintenance entry point until that issue is fixed and tested.
