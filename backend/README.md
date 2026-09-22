# DEPO backend

Install the frontend and backend together using the [canonical installation guide](../infra/deployment/README.md).
It owns `backend/.dt_venv`; no separate backend environment is required.
The supported runtime is the ten HTTP services and outbox worker listed in
[services.json](../infra/deployment/services.json).

- [PostgreSQL](../infra/postgres/README.md), [schema/tables/columns](../infra/postgres/SCHEMA.md)
- [Neo4j on-premises and off-premises](../infra/neo4j/README.md)
- [Spark/PySpark](../infra/spark/README.md)
- [Windows operations](../infra/windows/README.md)

Use root `.env.local` for server settings and API keys. Do not place server
credentials in frontend settings. Install with `-Development` for test dependencies.
`backend/main.py` is a compatibility host; see [legacy migration notes](legacy/README.md).
It is not the customer deployment entry point.
