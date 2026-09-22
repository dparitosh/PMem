# Deployment runbook

The maintained customer installation procedure is [infra/deployment/README.md](../infra/deployment/README.md).
Use that single sequence for configuration, frontend/backend installation,
database initialization, startup and validation.

- [PostgreSQL provisioning](../infra/postgres/README.md) and [tables/columns](../infra/postgres/SCHEMA.md)
- [Neo4j on-premises, hosted and Aura](../infra/neo4j/README.md)
- [Spark and PySpark](../infra/spark/README.md)
- [Windows operations](../infra/windows/README.md)
- [Customer acceptance and remaining release gates](../infra/deployment/CUSTOMER_RELEASE.md)

Before upgrade, retain the release artifact, configuration and tested database
backup. Stop application processes, install the selected release, initialize its
schema and run validation before reopening traffic. Restore only through the
customer's rehearsed database recovery procedure; migrations have no automatic
reverse operation. Record logs and acceptance evidence with the release identity.
API keys are the supported configuration for this delivery. Azure API Management
is optional; its scripts are indexed in the canonical guide.
