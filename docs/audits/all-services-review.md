# All-service integration review

Reviewed the ten HTTP services and two workers declared in `infra/deployment/services.json`: schema-sets, ontology, agentic, graph, ingestion, OSLC, catalog, data-products, CEIM, data-pipeline, catalog-outbox worker and pipeline worker.

## Corrected defects

- Shared CORS now accepts the APIM subscription header used by browser requests.
- Neo4j readiness checks the selected database, honors URI and credential aliases, bounds query time and disables transaction retries for the probe.
- Production readiness reports missing owned dependency configuration instead of silently reporting ready.
- Shared service URL lookup validates HTTP/HTTPS URLs and rejects embedded credentials, placeholders, malformed ports, query strings and traversal paths. All supported production environment aliases and gateway mode prohibit silent loopback defaults.
- Pipeline publication uses CEIM's approval credential and scoped APIM subscription header. Recovery checks use the graph-read credential and the graph gateway scope.
- Speed-path publication supplies CEIM service authentication and a stable reconciliation publication ID for retry recovery.
- Governed ingestion supplies the scoped APIM subscription header when dispatching pipeline jobs.

## Verification and remaining release checks

Seven dependency-free routing/credential regression tests passed. PowerShell package validation passed for 46 scripts, ten services, two workers and seven SQL migrations. Local/gateway routing and browser runtime configuration tests passed. A simulated gateway contract test exercised all ten health/readiness/OpenAPI and preflight routes plus a protected graph read. Mocked readiness checks verified missing production configuration and the selected Neo4j database. Backend Python syntax was checked.

These checks do not certify live services. FastAPI/RDF/frontend dependencies are absent from this workstation following cleanup. A production frontend build, actual OpenAPI imports, PostgreSQL/Neo4j integration, worker execution and real Azure APIM network/authentication checks remain required on the deployment VM. Run the installation preflight, start backend services and frontend, then run the full diagnostic; gateway mode additionally requires the documented gateway diagnostic. No live customer configuration was changed.
