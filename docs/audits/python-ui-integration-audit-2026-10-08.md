# Python–UI integration audit — 2026-10-08

> Dated audit record: use [the current audit index](README.md) for latest validation and acceptance status. Findings and test counts below belong to their recorded review; they are not a current release certificate.

Audited commit: 93ad996. Audit-only artifacts; application code was not changed.

## Coverage and evidence

All 17 navigation pages are represented in ui-python-contract-inventory.json with entry modules and recursively resolved relative JavaScript import dependencies. The deployed topology contains 10 HTTP Python services. Static route composition identified 340 route entries, including the standard health/readiness/OpenAPI paths. Of 145 endpoint defaults in frontend/src/config.js, 116 have a matching served path and 29 remain unresolved. The inventory identifies 187 direct network-call sites in 20 files; higher-level API_METHODS calls additionally appear in page/component consumers.

These counts are inventory coverage, not branch coverage or a live compatibility percentage. Factory-generated routers, dynamic paths, HTTP methods at every call site, form/body schemas and live authorization require additional checks. A path match alone does not verify the correct service, method, response shape or authentication policy.

Full frontend suite: 46 files / 198 tests passed. Selected backend boundary suites: 84 tests passed. Backend tests use controlled transports, pure functions and extracted handlers; they do not establish deployed FastAPI/database integration. The bundled Python environment lacks pytest and full backend dependencies. Live PostgreSQL, Neo4j, APIM, browser network and customer acceptance tests were not performed.

## Confirmed defects

### F1 — P1: reachable import OWL export has no deployed route

DataImportPipeline.js:1584 invokes import.exportOWL for non-registered tasks. apiClient.js:521 resolves API.import.owlExport to /api/v1/import/owl/{task_id}/export (config.js:268). The deployed ingestion app includes unified_import_router and tracked_import; neither supplies this route, and the static composition finds no service owner. The export action reaches a missing endpoint. Add an artifact-backed export contract or remove the action when a task has no ontology artifact. Do not substitute registered ontology IDs for task IDs.

### F2 — P2: download filename header is inaccessible across origins

service_runtime.py:141 does not expose Content-Disposition through CORS, while DataImportPipeline.js:1586 reads that header to choose the exported filename. Direct UI/service ports are separate origins, so successful FileResponse downloads lose the server-selected filename. Expose Content-Disposition and verify direct-service and gateway download behavior.

### F3 — P2: malformed sample-query payload can crash chat

Chatbot.js:335 checks only data.queries and its length before storing it. A response such as {queries:"prompt"} passes that check. Rendering at Chatbot.js:446 calls sampleQueries.map and throws. Arrays of non-string entries also lack validation. Require an array of non-empty strings and retain safe defaults on invalid responses.

### F4 — P2: UI timeout configuration is not validated

config.js:101–102 uses parseInt for REQUEST_TIMEOUT and CHAT_STREAM_TIMEOUT without finite positive bounds. Non-numeric values yield NaN, while negative values remain accepted. In particular, invalid chat timer values can become immediate cancellation. Validate runtime/build values using a shared bounded-number parser and report configuration errors rather than allowing inconsistent transport behavior.

### F5 — P2: retry policy extends one request into several timeout windows

apiClient.js:188–203 retries timed-out GETs twice, each with the original timeout and an uninterruptible backoff. With the default 300000 ms timeout, one logical request can consume roughly 15 minutes plus delays unless a caller supplies an independent deadline. Cancellation during backoff does not end the wait immediately. Apply a single logical deadline and an abort-aware delay before retrying; retain the no-mutation-retry policy.

### F6 — P2: Python graph exceptions leak through the UI error contract

graph_service/router.py:95,103,111,119,127 include str(exc) in HTTP error details. Neo4j and transport exceptions can contain query or infrastructure diagnostics, which the UI error helper presents to users. Return stable public error codes/messages and retain detailed diagnostics in server logs associated with X-Request-ID.

## Page integration matrix

| Page | Principal Python services | Static review status |
|---|---|---|
| Home | agentic, graph, ontology/ingestion | Shared chat/config findings F3–F5 |
| Import | ingestion, ontology, pipeline, QIF | Reachable export defect F1; download F2 |
| Data Flow | pipeline, agentic, product | Inventory and existing boundary regressions; live jobs unverified |
| Ontology Junction | ontology, ingestion, agentic, graph | Routing/dependency inventory; dynamic mapping/reasoning acceptance unverified |
| Data Catalog | catalog, product | Product-scoped queries and collection boundaries reviewed; live delivery unverified |
| Data Products | product, pipeline, ontology | Publication/revocation boundaries tested with fakes; live persistence unverified |
| Metadata Registry | ontology, ingestion | Dictionary validation regressions passed; governance integration unverified |
| Graph Explorer | graph | Public-error defect F6; live graph counts unverified |
| Code Network | agentic | Endpoint inventoried; response-contract branch coverage incomplete |
| Modeling | ontology, graph | Adapter/dependency inventory; complete write/approval acceptance unverified |
| ReqIF | ingestion, ontology, graph | Shared workbench inventory; complete instance-import acceptance unverified |
| QIF | QIF, ingestion, ontology | Upload/download regressions; cross-origin filenames F2 |
| Where Used | graph | Shared graph normalization and F6; live traversal acceptance unverified |
| Data Quality | pipeline | Run-list validation and bounded polling reviewed; live report production unverified |
| Recommendations | graph, ontology, agentic | Existing retry/readiness regressions; live recommendations unverified |
| Reports | graph, ingestion, pipeline | Shared report adapters inventoried; complete export/report acceptance unverified |
| Admin | ontology, agentic, catalog, product, graph | Shared authentication/remount boundaries reviewed; live scope/expiry tests unverified |

## Unresolved endpoint defaults

The JSON inventory lists all 29 unresolved defaults. They include retired aggregate health/schema routes, 3DXML operations, legacy data-import routes, ontology-mapper routes and embedding/webhook operations. They must not all be counted as active bugs: some adapters have no current consumer. F1 was traced to a reachable consumer. Remaining defaults need removal, explicit capability gating or a deployed contract if their feature is retained.

## Remaining acceptance gates

A 100% integration audit is not complete until every reachable UI action has a verified method/path/request/response/authentication mapping, including dynamic routes and generated contracts; every async response/error branch has coverage; all services start using the production dependency lock; migrations and concurrent/restart behavior pass on PostgreSQL/Neo4j; and all 17 pages complete authorized customer workflows through both deployed routing modes. Run read-only live contract/session preflight first, then disposable authorized workflow fixtures for writes. Do not represent mocked navigation or passing unit tests as customer-environment acceptance.

## Correction follow-up

F1–F6 were corrected locally: an authenticated retained-artifact export route is hosted by ingestion; CORS exposes Content-Disposition; chat validates sample prompt arrays; timeout settings fall back safely and display configuration warnings; GET retries share one original timeout budget with cancellable backoff; graph responses omit exception details while server logs retain them. Targeted evidence: 31 frontend tests and 12 backend tests passed. An additional deadline regression prevents a retry from sending after the original request deadline expires. Live APIM, serialization dependencies, and the remaining unresolved legacy defaults are still outside this verification. The inventory records the audited pre-fix commit and is not live OpenAPI evidence.
