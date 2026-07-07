# Python Script Classification

This audit separates API entrypoints from standalone scripts and diagnostics. It is intended for release packaging and customer handoff.

## Summary

- `backend/main.py` is the primary FastAPI application entrypoint.
- `backend/data_ingestion.py` is a mounted FastAPI router module.
- root `main.py` is not a server by itself; it re-exports `backend.main.app` for compatibility/tests.
- top-level `scripts/*.py` are standalone conversion, loading, migration, or cleanup utilities. They are not API endpoints.
- `backend/scripts/*.py` are supported backend fallback CLI tools.
- `tools/diagnostics/*.py` are supported diagnostics.
- `tools/import/*.py` are supported import support utilities.
- `tools/tests/*.py` are developer/test helpers, not APIs.
- `tools/legacy_root_scripts/` has been removed from the active tree; historical debug scripts should stay out of customer releases.
- Removed root-level backend diagnostics/tests (`debug_excel*.py`, `analyze_splm_structure.py`, `test_ontology_pipeline.py`) from the active API tree.

## API Entrypoints

| File | Type | Status | Notes |
| --- | --- | --- | --- |
| `backend/main.py` | FastAPI app | Active API | Main Uvicorn target: `backend.main:app`. Contains the registered app surface and mounted routers. |
| `backend/data_ingestion.py` | FastAPI router | Active router | Mounted under backend API; not run directly. |
| `backend/routes/admin_routes.py` | FastAPI router | Active router | Admin/cleanup API surface. |
| `backend/routes/ontology_routes.py` | FastAPI router | Active router | Ontology/Semantic Bridge API surface. |
| `backend/routes/threedxml_routes.py` | FastAPI router | Active router | 3DXML extraction API surface. |
| `main.py` | Compatibility shim | Import-only | Re-exports `backend.main.app`; not the customer startup target. |

## Supported Standalone CLI / Fallback Scripts

| File | Type | Status | Purpose |
| --- | --- | --- | --- |
| `backend/scripts/import_file.py` | CLI | Supported fallback | Backend-side file import when UI upload/commit is unsuitable for large files or browser timeout recovery. |
| `backend/scripts/run_semantic_workflow.py` | CLI | Supported fallback | Runs semantic workflows such as `instance-link`, ontology validation, dictionary/taxonomy generation, and ontology merge from command line. |
| `tools/admin/cleanup_neo4j.py` | CLI | Supported admin tool | Destructive cleanup utility; use carefully and prefer Admin UI/API where possible. |
| `tools/diagnostics/neo4j_diagnostics.py` | CLI | Supported diagnostic | Checks Neo4j/public service health without mutating data. |
| `tools/diagnostics/ollama_diagnostics.py` | CLI | Supported diagnostic | Checks Ollama-compatible endpoints. |
| `tools/diagnostics/import_tasks.py` | CLI | Supported diagnostic | Inspects persisted import tasks. |

## Top-Level `scripts/` Utilities

These are standalone scripts. They are not APIs and are not imported as active FastAPI routes.

| File | Type | Release classification | Notes |
| --- | --- | --- | --- |
| `scripts/build_3dx_ontology_from_xls.py` | Standalone converter/loader | Utility | Builds 3DXML ontology from XLS source; direct Neo4j usage detected. |
| `scripts/convert_3dx_schema.py` | Standalone converter | Utility | Converts 3DXML schema assets. |
| `scripts/convert_xpdmxml.py` | Standalone converter | Utility | Converts XPDMXML assets. |
| `scripts/load_mbse_xmi_instances.py` | Standalone loader | Utility | Loads MBSE/XMI instances; direct Neo4j usage detected. |
| `scripts/load_ontology_to_neo4j.py` | Standalone loader | Utility | Loads ontology into Neo4j; direct Neo4j usage detected. |
| `scripts/load_xpdmxml_instances.py` | Standalone loader | Utility | Loads XPDMXML instances; direct Neo4j usage detected. |
| `scripts/_cleanup_neo4j.py` | Standalone cleanup | Legacy/admin utility | Cleanup helper; keep out of normal customer workflow unless documented as admin-only. |

## Root / Backend-Root Python Files

| File | Type | Release classification | Notes |
| --- | --- | --- | --- |
| `main.py` | Import shim | Keep | Compatibility import for tests/tools. |
| `backend/main.py` | API app | Keep | Primary backend service. |
| `backend/data_ingestion.py` | API router | Keep | Mounted router. |
| `backend/analyze_splm_structure.py` | Removed diagnostic | Removed | Local SPLM analysis helper was not an API. |
| `backend/debug_excel.py` | Removed diagnostic | Removed | Local Excel debug helper was not an API. |
| `backend/debug_excel2.py` | Removed diagnostic | Removed | Local Excel debug helper was not an API. |
| `backend/test_ontology_pipeline.py` | Removed root-level test | Removed | Root-level test file was not an API entrypoint. |

## `tools/` Utility Classification

| Area | Type | Release classification | Notes |
| --- | --- | --- | --- |
| `tools/import/*.py` | Import support utilities | Keep | Upload, poll, commit, parse, and snapshot helpers for support workflows. |
| `tools/tests/*.py` | Developer/test helpers | Keep out of customer runtime docs | Manual SHACL/API probes; not API entrypoints. |
| `tools/diagnostics/*.py` | Diagnostics | Keep | Safe customer-support diagnostics when documented. |
| `tools/admin/*.py` | Admin/destructive tools | Keep with warning | Should require explicit approval and clear docs. |
| `tools/legacy_root_scripts/` | Removed legacy diagnostics/tests | Removed from active tree | Historical debug scripts are not part of customer workflow. |

## Packaging Recommendation

For customer release, expose these as official surfaces only:

1. `start_backend.bat` and `start_frontend.bat` for service startup.
2. FastAPI OpenAPI docs from `/docs` and `/openapi.json`.
3. `backend/scripts/import_file.py` for backend import fallback.
4. `backend/scripts/run_semantic_workflow.py` for Semantic Bridge / ontology fallback.
5. `tools/diagnostics/*` for support diagnostics.
6. `tools/import/*` for import support workflows.
7. `tools/admin/cleanup_neo4j.py` only as an admin/destructive tool.

Keep `tools/tests/*` developer-only. Do not describe top-level `scripts/*.py` as APIs.