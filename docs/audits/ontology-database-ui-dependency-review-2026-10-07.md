# Ontology, database and UI dependency audit â€” 2026-10-07

## Confirmed gaps and fixes

| Boundary | Gap | Correction |
|---|---|---|
| Graph â†’ mapping service | Property targets from ingestion and RDF projections did not resolve to graph IDs through the mapping lookup. | Scoped lookup includes classes, object, datatype and annotation properties; retains domain/range edges and bounds results at 10,000. |
| Manual draft â†’ preview | RDF-only identifiers could be treated as graph IDs; graph class merging could discard target metadata. | Require graph provenance, merge server-owned metadata and preserve distinct target kinds. |
| Graph publication â†’ agent memory | New publication facts lacked the scope required by memory reads and used a different fact ID contract. | Reuse the existing memory fact constructor and write scope in the publication transaction. |
| Publication request â†’ database | Non-object mapping rows caused an attribute error. | Validate row shape before opening a graph session. |
| Session â†’ Bridge UI | Credential expiry/clear left recommendations and pending responses active. | Invalidate preview state and pending response generations on credential events. |
| Session â†’ merge UI | Governed merge results could survive credential changes and late responses after navigation. | Invalidate merge/inference generations and clear merge state on credential changes; invalidate merge on unmount. |
| Saved preview â†’ UI | Incomplete candidates could crash the recommendation table. | Reject incomplete previews with a recoverable message. |

## Dependency contracts reviewed

- PostgreSQL registry selects the configured, provisioned application schema. Preview records use `semantic_bridge_jobs_v1`; registry writes and related product/evidence writes retain their existing transaction boundaries. No new database migration is required for JSON recommendation records.
- Agentic service owns Bridge preview, recovery and evidence endpoints. Ontology Governor dispatches the existing durable Bridge implementation locally; approval is validated before dispatch.
- Graph service owns private mapping publication and receipts under `/api/v1/graph/bridge`. It verifies `GRAPH_PUBLICATION_TOKEN`, requires the provisioned publication constraint and commits links, receipt, event and optional scoped memory together.
- Ontology service owns merge preview/apply. Merge and reasoning still require retained ontology artifacts; graph records alone support mapping lookup, not RDF reasoning.
- UI uses `AGENTIC_APPROVAL_TOKEN` for governor execution and `GRAPH_READ_TOKEN` for saved evidence/recovery. Actual mappings require user selection and review confirmation. Agent execution uses the configured Agentic service URL.
- PostgreSQL and Neo4j readiness, service URL/auth configuration, OpenAPI authorization metadata and frontend session handling were inspected. Ollama generation remains an independent REST dependency; an absent APIM model-list route cannot verify generation.

## Verification and limits

- 24 backend unit tests passed: durable Bridge jobs, server-resolved manual recommendations, bounded graph lookup, scoped publication memory, malformed request handling and registry transaction rollback.
- 28 frontend tests passed: Bridge review/recovery/session invalidation, governor dispatch, agent request handling, service read credentials and API session rejection.
- Production frontend build passed; existing bundle-size and React test-library deprecation warnings remain.
- Backend tests use isolated/fake storage or transactions; they do not prove connectivity, migrations, Cypher execution, credentials or permissions on the installation VM.
- Live PostgreSQL, Neo4j, APIM and full FastAPI route integration remain unverified here. The local Python runtime lacks FastAPI/httpx; no packages were installed and no live database records were changed.
- Existing memory facts written without scope are not automatically assigned to a tenant/project. Their ownership must be established before any backfill.

## Data-layer alignment follow-up

The workflow layer no longer executes the mapping-term Cypher query. Graph
service owns that query in `query_repository.MAPPING_TERMS`, executes it through
its existing publisher data adapter, and exposes the private authenticated
`GET /api/v1/graph/mapping-terms?scope=...` operation. Both semantic mapping and
UnifiedDataImport class lookup call the reusable GraphDataClient adapter.
This peer read uses server-owned GRAPH_PUBLICATION_TOKEN, independent of browser
Entra/token authentication, and scoped APIM subscription headers when configured.
Responses and query counts are bounded; HTTP errors are not converted to empty
results. Deploy Graph service alongside its consumers to provide the new route.

Preview persistence continues through PostgresRegistry; mapping publication
continues through GraphBridgeClient and the Graph service transaction/receipt.
Imported task restoration continues through the existing UnifiedDataImportService
retained-task data layer. This follow-up does not migrate every legacy import
write or artifact reader to a remote microservice.
