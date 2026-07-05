# Service Catalog And Code Audit

Date: 2026-06-05

Scope:
- Frontend app in `frontend/`
- Backend FastAPI app in `backend/`
- API mappings in `frontend/src/config.js` and `frontend/.env.example`
- Live backend OpenAPI surface from `http://localhost:8000/openapi.json`

## 1. Application Service Catalog

| App / service | Runtime | Entry point | Port | Purpose | Current state |
| --- | --- | --- | --- | --- | --- |
| Frontend UI | React / CRA | `frontend/src/App.js`, started by `start_frontend.bat` or `npm start` | `3000` | Main user interface: landing page, graph, table, reports, data import, semantic bridge, digital thread, recommendations | Active. Uses `frontend/src/config.js` plus `frontend/.env` / `.env.example` for backend endpoints. |
| Backend API | FastAPI / Uvicorn | `backend/main.py`, started by `start_backend.bat` | `8000` | API service surface for graph, ontology, import, admin, chat, recommendations, webhook, and traceability workflows | Active. Edited app OpenAPI reports 90 paths. |
| Neo4j database | External DB | configured by `backend/.env` | usually `7687` | Graph persistence and query execution | Required for graph, ontology, recommendations, traceability, schema cleanup. Current logs show placeholder host `your-neo4j-instance:7687`; this must be corrected in runtime env. |
| Ollama / LLM service | Optional external service | `backend/Services/ollama_service.py`, `backend/core/llm.py` | configured externally | Chat and optional import assistant functionality | Optional. Backend has health/query endpoints under import for Ollama. |

## 2. Backend API Service Groups

Live paths are grouped by user-facing service responsibility.

| Service group | Representative endpoints | Backend owner files | Frontend consumers |
| --- | --- | --- | --- |
| Health and readiness | `GET /health`, `GET /ready`, `GET /health/neo4j`, `GET /graph-metrics`, `GET /ontologies/available` | `backend/main.py`, `backend/core/graph.py` | `LandingPage.js`, `GraphHEB.js`, `apiClient.js` |
| Graph visualization and traversal | `GET /graphvis`, `GET /graphvis/by-ontology/{prefix}`, `POST /graphfilter-multi`, `GET /graphtraverse/{node_id}`, `GET /schema-graph`, `GET /instance-graph` | `backend/main.py`, `backend/core/graph.py`, `backend/chains/cypher.py` | `GraphHEB.js`, `WhereUsedView.js`, `apiClient.js` |
| Ontology graph browsing | `GET /ontology/options`, `GET /ontology/{ontology_type}`, `GET /ontology/{ontology_type}/instances`, `GET /ontology/step/parts`, `GET /ontology/step/{part_name}`, `GET /ontology/mbse-instances` | `backend/main.py` | `GraphHEB.js` |
| Ontology upload and registry | `POST /api/v1/ontology/upload`, `GET /api/v1/ontology/registered`, `POST /api/v1/ontology/merge`, `POST /api/v1/ontology/cleanup-old-xsd` | `backend/Services/unified_import_router.py`, `backend/Services/ontology_upload_manager.py` | `OntologyContext.js`, `OntologyMapper.js`, `GraphHEB.js`, `DataImportPipeline.js`, `apiClient.js` |
| Semantic bridge / ontology mapping | `GET /api/v1/ontology/{prefix}/data-dictionary`, `GET /api/v1/ontology/{prefix}/mappings/{source_format}`, `POST /api/v1/ontology/{prefix}/map-entity`, `GET /ontology-mapper/*`, `GET /ontology-mappings` | `backend/routes/ontology_routes.py`, `backend/main.py`, `backend/Services/ontology_mapper_service.py`, `backend/Services/ap239_mapper_service.py` | `OntologyMapper.js`, `OntologyMetadataForm.js`, `apiClient.js` |
| Data import pipeline | `POST /api/v1/import/upload`, `GET /api/v1/import/status/{task_id}`, `GET /api/v1/import/preview/{task_id}`, `GET /api/v1/import/pre-commit/{task_id}`, `POST /api/v1/import/commit/{task_id}`, `POST /api/v1/import/cancel/{task_id}`, `GET /api/v1/import/formats`, `GET /api/v1/import/owl/{task_id}`, `GET /api/v1/import/tasks`, legacy `/api/import/*`, `/data-import/*` | `backend/main.py`, `backend/Services/unified_data_import.py`, `backend/Services/data_import_service.py`, parsers in `backend/Services/*_parser.py` | `DataImportPipeline.js`, `apiClient.js` |
| SysML v2 API connector | `GET /api/v1/sysml-v2/status`, `GET /api/v1/sysml-v2/integration-plan` | `backend/routes/sysml_v2_routes.py`, `backend/Services/sysml_v2_connector_service.py` | Readiness only; future import source after customer SysML v2 server validation |
| Data ingestion router | `POST /api/v1/ingest-data` | `backend/data_ingestion.py` | No direct current component use found. `frontend/.env.example` maps stale `/api/v1/ingestion/ingest-data`, not the live `/api/v1/ingest-data`. |
| 3DXML extraction | `POST /api/v1/ontology/extract-3dxml`, `GET /api/v1/ontology/3dxml/status/{task_id}`, `GET /api/v1/ontology/3dxml/formats` | `backend/routes/threedxml_routes.py`, `backend/Services/threedxml_ontology_extractor.py`, `backend/Services/splm_ontology_extractor.py` | `apiClient.js` mapped; no direct component use found in current UI. |
| Admin / cleanup | `GET /api/v1/admin/health`, `POST /api/v1/admin/clean-schema`, `GET /api/v1/admin/schema-stats`, `POST /api/v1/admin/reset-database` | `backend/routes/admin_routes.py`, `backend/Services/neo4j_schema_cleaner.py` | `GraphHEB.js`, `apiClient.js` |
| Chat and sample queries | `POST /chat`, `POST /chat-stream`, `GET /chat/sample-queries` | `backend/main.py`, `backend/agent/chat.py`, `backend/agent/memory.py`, `backend/agent/sessions.py` | `Chatbot.js`, `apiClient.js` |
| Recommendations | `POST /recommendations/change-impact`, `POST /recommendations/similar-parts`, `POST /recommendations/manufacturing`, `GET /recommendations/health` | `backend/main.py`, `backend/Services/change_impact_recommender.py`, `backend/Services/similar_parts_recommender.py`, `backend/Services/manufacturing_process_recommender.py` | `RecommendationsTab.js`, `GraphHEB.js`, `apiClient.js` |
| Digital thread traceability | `POST /trace/digital-thread` | `backend/main.py`, `backend/chains/cypher.py` | `DigitalThreadTracer.jsx` |
| AP242 / schema helpers | `GET /schema`, `GET /ap242/rotor-shaft-pmi`, `POST /ap242/search` | `backend/main.py`, `backend/core/graph.py` | `SchemaContext.js`, `apiClient.js` |
| Embeddings and webhooks | `POST /embeddings/build`, `POST /api/v1/webhooks/neo4j`, `POST /api/webhooks/neo4j` | `backend/main.py`, `backend/Services/graph_embeddings.py`, `backend/Services/webhook_validator.py` | `apiClient.js` mapped; no direct component use found. |

## 3. Backend Files Outside `backend/Services`

These files are not in `backend/Services` and should be classified as API entry, shared infrastructure, test-only, diagnostic, or candidate cleanup.

### Keep As API Or Router Surface

| File | Role | Notes |
| --- | --- | --- |
| `backend/main.py` | Main FastAPI application | Large file with many route handlers. Keep as entry point, but long-term should be split into routers by service group. |
| `backend/data_ingestion.py` | FastAPI router | Included at `/api/v1`; live path is `/api/v1/ingest-data`. Frontend env currently points to `/api/v1/ingestion/ingest-data`, which is not live. |
| `backend/routes/admin_routes.py` | FastAPI admin router | Included at `/api/v1/admin/*`. UI uses schema cleanup here. |
| `backend/routes/ontology_routes.py` | FastAPI ontology router | Included at `/api/v1/ontology/*`. Core for Semantic Bridge and AP239/AP242 mapping workflows. |
| `backend/routes/threedxml_routes.py` | FastAPI 3DXML router | Included at `/api/v1/ontology/3dxml*` and `/api/v1/ontology/extract-3dxml`. |

### Keep As Shared Infrastructure

| File / folder | Role | Notes |
| --- | --- | --- |
| `backend/core/db_config.py` | Central Neo4j configuration and driver factory | Must remain shared; all DB access should route through this rather than hardcoded credentials. |
| `backend/core/graph.py` | Graph query proxy and schema helpers | Backend route handlers depend on this. |
| `backend/core/llm.py` | LLM/embedder configuration | Shared by chat/embeddings. |
| `backend/core/CustomAOI_helper.py` | Helper | No route ownership; keep only if referenced by active workflows. |
| `backend/core/DeveloperApp.py` | Helper/prototype | Needs owner decision; not part of FastAPI surface. |
| `backend/models/schema.py` | Pydantic request/response schemas | Shared by API/chat routes. |
| `backend/agent/*.py` | Chat agent implementation | Used by `/chat` and `/chat-stream`. |
| `backend/chains/cypher.py`, `backend/chains/vector.py` | Query/chain helpers | Used by graph/chat/trace workflows. |
| `backend/parsers/xmi_parser.py` | Parser utility | There is also `backend/Services/xmi_parser.py`; review for duplication and choose one canonical parser. |

### Test Or Diagnostic Only

| File / folder | Classification | Recommendation |
| --- | --- | --- |
| `backend/tests/*.py` | Tests and DB diagnostics | Keep under tests, but destructive scripts such as `clean_neo4j_schema.py` and `delete_electronicassembly_componentinstance.py` should remain wrappers around FastAPI/admin tools or clearly marked test-only. |
| `backend/Services/tests/*.py` | Service tests | Move to `backend/tests/services/` eventually for a single test tree. |
| `backend/tools/test_db_config_import.py`, `backend/tools/test_driver_connect.py` | Local diagnostics | Keep as tools if useful, but not part of app service. |
| `backend/test_ontology_pipeline.py` | Root-level test | Move under `backend/tests/` to avoid mixing tests with app entry files. |
| `backend/test_data/*` and `backend/tests/cat_test_results/*` | Test artifacts | Keep out of service packaging unless needed for fixtures. |

### Candidate Cleanup / Archive

| File | Why it is not an API service | Recommendation |
| --- | --- | --- |
| `backend/analyze_splm_structure.py` | Standalone analysis script, not imported by routes | Move to `backend/tools/` or archive after verifying no active workflow depends on it. |
| `backend/debug_excel.py`, `backend/debug_excel2.py` | Debug scripts | Move to `backend/tools/diagnostics/` or delete after confirming no needed logic. |
| `backend/package-lock.json` | Node lockfile in Python backend | Remove if no backend Node project exists. |
| `backend/spinner_datatype.csv` | Data asset | Keep only if an active route/parser reads it; otherwise move to `backend/Data/` with a clear owner. |
| `backend/SPLM_CODE_REVIEW.md`, `backend/SPLM_EXTRACTION_FIXED_SUMMARY.md`, Neo4j docs | Documentation | Move to top-level `docs/` for consistency. |

## 4. Frontend API Service Review

All UI work should use `frontend/src/config.js` and `frontend/src/services/apiClient.js` unless there is a specific streaming reason to use `fetch`.

| Frontend file | API service dependency | Current assessment |
| --- | --- | --- |
| `frontend/src/services/apiClient.js` | Central API client, grouped API wrappers | Correct centralization point. Contains wrappers for some endpoints not currently live. |
| `frontend/src/config.js` | Endpoint mapping and `REACT_APP_*` env binding | Correct source for environment mapping. Some stale/planned mappings remain. |
| `frontend/src/Components/LandingPage.js` | `healthAPI.graphMetrics`, `healthAPI.ontologiesAvailable` | Correct. Depends on `/graph-metrics` and `/ontologies/available`. |
| `frontend/src/Components/GraphHEB.js` | graph, ontology, admin, cleanup, recommendation prefill | Heavy API user. Should be split later: graph data hook, ontology controls hook, admin tools hook. Has direct `apiClient.get/post(API...)` calls; acceptable but not fully centralized through typed wrapper methods. |
| `frontend/src/Components/DataImportPipeline.js` | import upload/status/preview/pre-commit/commit/cancel | Correct workflow goes through FastAPI. Cancel route is now live. Commit uses `fetch` instead of `apiClient`; consider converting for consistent error handling. |
| `frontend/src/Components/OntologyMapper.js` | ontology mapper, ontology registry, merge | Requires mapping/data-dictionary/vocabulary/stats endpoints. Should continue using configured paths only. |
| `frontend/src/contexts/OntologyContext.js` | `API_METHODS.ontology.listRegistered` | Correct shared polling source for registered ontologies. |
| `frontend/src/Components/Chatbot.js` | chat stream and sample queries | Uses `fetch` for streaming; acceptable for SSE-like streaming, but still uses `buildUrl(API...)`. |
| `frontend/src/Components/DigitalThreadTracer.jsx` | `POST /trace/digital-thread` | Correctly goes through `apiClient` and `API.integration.digitalThreadTrace`. |
| `frontend/src/Components/RecommendationsTab.js` | recommendations service wrappers | Correct use of `API_METHODS.recommendations`. |
| `frontend/src/Components/WhereUsedView.js` | graph filter and traversal | Uses configured graph endpoints. `/graphfilter` has been restored in backend. |
| `frontend/src/SchemaContext.js` | schema endpoint | Correct. |

## 5. API Mapping Gaps

OpenAPI comparison against the edited FastAPI app found:
- Live backend paths missing from `frontend/.env.example`: `0`
- Frontend-mapped paths not live in backend: `13`

### Frontend-Mapped But Not Live In Backend

| Endpoint | Impact | Recommendation |
| --- | --- | --- |
| `/api/v1/documents/*` | `documentAPI` wrappers will fail if wired into UI | Either include `backend/Services/documents_api.py` router and fix its imports, or remove/hide document UI mappings. |
| `/api/v1/import/convert-schema`, `/parse-schema`, `/process-stages-4-7`, `/map-ontology` | Older/newer pipeline wrappers not live | Confirm whether these belong to `data_import_service.py`; expose through router or delete mappings. |
| `/reports` | Wrapped by `schemaAPI.getReports`; not live | Reports tab currently appears mostly local/graph-derived; remove wrapper or add backend route. |
| `/graphtraverse` | Base path mapping is not live | Keep `/graphtraverse/{node_id}` and remove the unused base mapping if no component needs it. |
| `/api/ontology/upload`, `/api/ontology/registered`, `/api/v1/ontology` | Legacy/stale ontology paths | Prefer `/api/v1/ontology/upload` and `/api/v1/ontology/registered`; remove unneeded legacy mappings after UI migration. |
| `/api/v1/documents/*` | Document wrappers are mapped but the document router is not mounted | Mount and fix `backend/Services/documents_api.py`, or remove document wrappers until the UI uses them. |

## 6. Recommended Cleanup Order

1. Fix environment/runtime first: ensure `backend/.env` has the real Neo4j URI/user/password and the running backend process is restarted.
2. Restore or remove remaining stale frontend API mappings:
   - Highest priority: `/api/v1/import/convert-schema`, `/api/v1/import/parse-schema`, `/api/v1/import/process-stages-4-7`, `/api/v1/import/map-ontology` if the import UI will expose those controls.
   - Medium priority: documents and `/reports`, unless they are planned features.
3. Move non-service backend scripts:
   - Move `analyze_splm_structure.py`, `debug_excel.py`, `debug_excel2.py`, `test_ontology_pipeline.py` into `backend/tools/` or `backend/tests/`.
4. Split `backend/main.py` into routers by service group:
   - `graph_routes.py`, `chat_routes.py`, `recommendation_routes.py`, `import_routes.py`, `ontology_view_routes.py`, `integration_routes.py`.
5. Normalize frontend API access:
   - Components should prefer `API_METHODS.*` wrappers.
   - Keep direct `fetch` only for streaming or special download behavior.
6. Resolve parser duplication:
   - Review `backend/parsers/xmi_parser.py` versus `backend/Services/xmi_parser.py`.
   - Choose a canonical module and update imports.

## 7. Current Service Health Notes

- SysML v2 API readiness routes are available under `/api/v1/sysml-v2/*`, but repository sync/import is not implemented yet; details are documented in `docs/sysml-v2-api-client-audit.md`.
- `GET /ontologies/available` returns 200 after the latest fix.
- Graph and traceability features still depend on Neo4j connectivity.
- The current backend logs indicate the app is trying to resolve `your-neo4j-instance:7687`, which is a placeholder. Until that runtime config is corrected, graph-backed UI tabs can render but will show empty/error states.
