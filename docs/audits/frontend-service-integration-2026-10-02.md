# Frontend and all-service integration audit — 2026-10-02

> Dated audit record: use [the current audit index](README.md) for latest validation and acceptance status. Findings and test counts below belong to their recorded review; they are not a current release certificate.

Scope: frontend URL ownership, shared and dedicated client authentication, source imports, service manifest, release configuration and simulated gateway diagnostics.

## Confirmed defects corrected

- Chat streaming `/api/v1/chat-stream` had no frontend service owner and fell back to the aggregate/frontend origin. It now routes to agentic.
- Governed imports and SysML v2 commit imports were missing ingestion ownership. They now resolve to ingestion in both local and gateway modes.
- Catalog artifact retention paths had no catalog ownership. They now resolve to catalog.
- Agentic client health defaulted to `/health`, which its standalone app does not expose. It now uses `/healthz`.
- The dedicated Semantic Bridge client called credential scoping without an endpoint and omitted APIM subscription headers. Its interceptor now scopes subscription headers to the resolved gateway URL and preserves explicit Authorization.
- Governed instance uploads now use DATA_JOB_EXECUTION_TOKEN. Legacy imports and document submission/cancellation use INGESTION_WRITE_TOKEN. Read credentials do not grant these write permissions.
- Related pending fixes validate graph access in the shell, distinguish registered sources from published graphs, expose restored failure messages and connect explicit XSD/XMI publication to the engineering workflow.

## Service coverage

| Service | Frontend boundary reviewed | Local evidence |
|---|---|---|
| Schema sets, 8010 | QIF schema/task client; separate write options | URL routing and simulated gateway contracts |
| Ontology, 8011 | Workbench, registry and metadata paths | URL routing and simulated gateway contracts |
| Agentic, 8012 | Chat/stream, Bridge, agents, observability | Streaming ownership and Bridge authentication regression checks |
| Graph, 8013 | Overview, projections, GraphQL, traversal | Routing, graph normalization and rejected-key handler checks |
| Ingestion, 8014 | XSD, governed/legacy instance and document imports | Actual upload/publication handlers with mocked transports |
| OSLC, 8015 | Local and remote API prefix | URL routing and simulated gateway contracts |
| Catalog, 8016 | Product discovery and artifact retention | Product/retention URL ownership |
| Data products, 8017 | Published product read and approval APIs | URL routing; existing package boundary regression checks |
| CEIM, 8018 | Normalization/publication boundary | Routing; provenance and source-scoped identity regression checks |
| Data pipeline, 8019 | Job runs, approval/execution and worker boundary | Routing; persistence and worker recovery regression checks |

## Verification and limits

21 Python regression tests passed. Browser local/gateway ownership, scoped credentials, Bridge authentication, graph normalization and actual shell/XSD handlers passed dependency-free Node checks. PowerShell release package validation passed (46 scripts, 10 services, 2 workers, 7 migration files); frontend configuration validation and simulated gateway contracts passed. These are source-level and mocked checks, not live customer acceptance.

Frontend dependencies and FastAPI/RDF dependencies remain absent after the requested workstation cleanup. A production frontend build, live OpenAPI imports, browser CORS and write workflows against PostgreSQL/Neo4j, real APIM policies and worker execution have not been verified here. Legacy aggregate-only endpoints remain in config; callers using those need migration or an explicitly configured aggregate backend. Health and read success alone do not certify publishing or jobs.

## OpenAPI-driven mapping feasibility

Each service exposes `/openapi.json`. The shared schema describes Bearer/API-key security and some operation approval metadata; the agentic catalog has server-side OpenAPI drift validation. The frontend still maps owners explicitly and does not dynamically import all contracts to select credentials. Existing metadata does not consistently identify the exact configured token name per operation. Add explicit non-secret credential-profile metadata and service identity before relying on automatic token-profile selection. Never export token values through OpenAPI or browser runtime configuration.


## Follow-up: implemented OpenAPI discovery

The shared OpenAPI contract now publishes non-secret credential-profile names
from authorization functions and dependencies, including method/path-sensitive
QIF and ingestion requirements. The API access dialog imports all configured
service contracts with bounded requests and per-service results. Imported paths
supplement frontend routing; runtime profile credentials are selected per
operation while explicit workflow headers retain precedence. Administrator
profiles use X-API-Key. Unresolved and ambiguous protected profiles do not receive
a guessed read credential. Contract servers never override configured roots.

New dependency-free tests cover published profile names, ingestion/QIF method
selection, parameterized routes, local/gateway profile selection, unresolved and
ambiguous requirements, administrator headers and credential clearing. Full
browser build and live service acceptance remain outstanding.


## Discovery audit follow-up

Three additional defects were corrected: rejected graph-key validation now restores
previous read/subscription credentials without deleting other profile keys;
operation security inherits the document's security declaration unless explicitly
overridden; and refreshing a service contract removes its previous mapping before
fetching so a failed refresh cannot retain stale credential metadata. Regression
cases cover inherited security and failed-refresh removal. All 24 dependency-free
Python tests and Node routing, credential, discovery, graph and handler checks pass.
Browser rendering/build and live customer connectivity remain unverified. Changes
are local and have not been committed or pushed.


## Dependency-backed frontend verification

The production Vite build passed on 2026-10-02. Six shell/import workflow tests
and three new SysML repository UI tests passed with the installed frontend
runtime. Tests cover validated read access, separate ontology upload credentials,
execution authorization, durable run feedback, stale readiness after a failed
refresh and rejection of responses without a run ID. Existing test expectations
were updated for the changed authentication contract. Vite reported large chunks
and the test library reported a React act deprecation; neither failed verification.
Temporary npm/runtime dependency files were removed after verification. The built
frontend output was retained locally. Live customer services, actual repository
requests, database/graph publication and worker execution remain unverified.
