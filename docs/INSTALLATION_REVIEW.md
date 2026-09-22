# Installation audit — 2026-09-22

The supported customer procedure is [deployment/README](../infra/deployment/README.md).
Competing backend, Windows and deployment runbook recipes were replaced with
references to this sequence. Historical audits are records, not install instructions.

## Fixed

- One server configuration parser rejects duplicates before importing settings;
  deployment validation, baseline provisioning and database checks share it.
- PostgreSQL has an explicit migration/check command and a reference for all
  eight tables, one view and forty columns. Startup fails on missing or
  incompatible column types or migration history.
- Neo4j production checks consistently require verified TLS and support routing
  and direct Bolt URIs. The guide covers on-premises, hosted and Aura deployment.
  Connection verification no longer counts/scans the customer graph.
- Spark enabled through environment flags now receives the same runtime checks
  as CLI flags; connector/scheduler cannot run with Spark disabled. Explicit false
  switch values survive the lifecycle wrapper. Connector smoke testing has a
  supported launcher using the installed Python environment.
- Wildcard bind addresses are translated to loopback for local requests; IPv6
  request addresses are bracketed. Schema startup works outside the repository cwd.
- Removed a duplicate Spark template setting and machine-specific Zeppelin paths.
  API keys remain the delivery authentication mode; Entra is not required.

## Verification and limits

Seven database contract tests pass in an isolated test environment. PowerShell
runtime/configuration, production API-key, installer prerequisite and configuration
generation checks pass. These exercise invalid columns/history, read-only mode,
duplicate settings, TLS schemes, Spark flag precedence and prerequisite failures.
All infrastructure PowerShell files parse successfully.

No live PostgreSQL migration, full dependency installation, Spark execution,
Neo4j server provisioning or customer browser acceptance was performed in this
audit. The schema verifier does not inspect every constraint/index or privilege.
The [customer acceptance record](../infra/deployment/CUSTOMER_RELEASE.md) remains
the release gate, including dependency pinning, backups, supervision and live tests.
