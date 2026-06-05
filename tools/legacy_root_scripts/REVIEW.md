# Legacy Root Script Review

The files in this folder were restored from the old repository root so no code
was lost during cleanup. They are not active application entry points. This
review records what each script did and where the maintained version should
live.

## Admin And Neo4j

| Legacy file | Review | Disposition |
| --- | --- | --- |
| `clean_neo4j.py` | Destructive graph wipe and schema drop. It used centralized `backend.core.db_config`, but had no confirmation gate. | Superseded by `tools/admin/cleanup_neo4j.py`, which requires `--yes`, uses env config, batches deletes, and can optionally clean uploads. |
| `cleanup_all.py` | Destructive graph/schema wipe plus upload folder deletion. It mixed DB cleanup with filesystem cleanup and had no explicit confirmation gate. | Split across `tools/admin/cleanup_neo4j.py` and `tools/diagnostics/import_tasks.py`. Keep legacy only for reference. |
| `check_neo4j.py` | Non-mutating DB count/health probe using centralized config. | Superseded by `tools/diagnostics/neo4j_diagnostics.py`. |
| `review_neo4j.py` | Non-mutating graph review/report script. | Useful ideas should move into `tools/diagnostics/neo4j_diagnostics.py`; keep legacy only until merged. |
| `check_import_tasks.py` | Upload task-store inspection plus optional old-task cleanup. It contained an old machine-specific command in help text. | Superseded by `tools/diagnostics/import_tasks.py`; cleanup now requires `--yes`. |

## Backend API Smoke Tests

| Legacy file | Review | Disposition |
| --- | --- | --- |
| `_test_endpoints.py` | Manual endpoint probe for ontology dictionary, mappings, import registration, and pre-commit endpoints. | Partially superseded by `backend/tests/test_api_smoke.py`. Add any missing endpoints there as pytest cases if still needed. |
| `check_ontology_list.py` | One-off registered ontology endpoint check. | Superseded by `backend/tests/test_api_smoke.py`. |
| `test_e2e.py` | Manual upload/status/commit flow. It uses old endpoint paths mixed with current v1 paths. | Keep as reference; promote only after endpoint paths are verified against `backend/main.py` OpenAPI. |
| `test_pipeline.py` | Manual upload/status/commit flow with polling. | Same coverage family as `test_e2e.py`; merge only one canonical flow into maintained pytest. |
| `final_comprehensive_test.py` | Large broad manual suite with overlapping API checks. | Do not run as-is. Break valuable checks into focused pytest files. |
| `review_output.py` | Mixed health/API/frontend/Neo4j review. The old version could continue after failed requests with undefined variables. | Superseded by `backend/tests/test_api_smoke.py` plus `tools/diagnostics/neo4j_diagnostics.py`. |

## Chat And UI Probes

| Legacy file | Review | Disposition |
| --- | --- | --- |
| `test_chat_stream.py` | Async chat streaming probe. | Candidate for maintained `backend/tests/test_chat_smoke.py` after confirming the active chat endpoint and expected streaming format. |
| `test_detailed_http.py` | Manual health and chat-stream HTTP diagnostics. | Overlaps with `test_chat_stream.py` and `test_ui_chat.py`; merge only non-duplicate assertions. |
| `test_ui_chat.py` | Manual backend health/chat probe plus frontend instructions. | Backend checks should become pytest; frontend checks should become browser/smoke tests, not a root script. |
| `detailed_chat_test.py` | Detailed chat behavior probe. | Candidate source material for maintained chat API tests. |

## Ollama And Azure-Compatible Diagnostics

| Legacy file | Review | Disposition |
| --- | --- | --- |
| `check_azure_models.py` | Model discovery and chat probe. Previously had embedded Azure endpoint/key fallback; sanitized in legacy copy. | Superseded by `tools/diagnostics/ollama_diagnostics.py`. |
| `diagnose_azure_connection.py` | DNS, tags, chat, HEAD/GET diagnostics. Previously printed key prefix; sanitized but still not active quality. | Superseded by `tools/diagnostics/ollama_diagnostics.py`. |
| `find_correct_model.py` | Brute-force model probing. | Could become an optional mode in `tools/diagnostics/ollama_diagnostics.py`; keep legacy only until then. |
| `test_azure_ollama.py` | Azure-compatible Ollama endpoint probe. Previously embedded endpoint/key fallback; sanitized. | Superseded by `tools/diagnostics/ollama_diagnostics.py`. |
| `test_azure_ollama_correct.py` | More endpoint-shape experiments. | Superseded by `tools/diagnostics/ollama_diagnostics.py`. |
| `test_exact_endpoint.py` | Endpoint URL variant tester. | Keep legacy only; too experimental for active tests. |
| `test_ollama_services.py` | Local Ollama tags/chat/embedding probe. | Superseded by `tools/diagnostics/ollama_diagnostics.py`. |
| `test_corrected_model.py` | Model/chat verification probe. | Merge any still-valid model expectations into diagnostics only if needed. |

## Service Startup

| Legacy file | Review | Disposition |
| --- | --- | --- |
| `start_backend.py` | Starts uvicorn and installs missing packages at runtime with pip. Runtime installation is risky and hides setup problems. | Do not use as active service startup. Use `setup.bat --backend` for setup and the existing service start scripts for runtime. |

## OWL, SHACL, And Import Logic

| Legacy file | Review | Disposition |
| --- | --- | --- |
| `test_owl_shacl.py` | Focused OWL/SHACL checks. | Superseded by `backend/tests/test_owl_shacl_smoke.py`. |
| `test_detailed_http.py` | Also includes chat HTTP details; see chat section. | Split by concern before promoting. |

## Follow-Up Items

- Promote chat-stream coverage into one maintained pytest file after confirming the active endpoint contract.
- Promote one upload/status/commit path into `backend/tests/test_api_smoke.py` or a separate integration test after confirming current OpenAPI paths.
- Keep destructive scripts only under `tools/admin` and require `--yes`.
- Keep diagnostics under `tools/diagnostics`; no credentials or customer paths should be embedded.
- `backend/tests/clean_neo4j_schema.py` was converted to a guarded compatibility wrapper around `tools/admin/cleanup_neo4j.py`.
- `backend/tests/check_nodes.py` was converted to a read-only centralized-config diagnostic.
- `backend/tests/delete_electronicassembly_componentinstance.py` was converted to a guarded centralized-config cleanup utility requiring `--yes`.
- Continue reviewing existing `backend/tests` for customer machine paths and local Neo4j credentials before promoting those scripts into maintained tests.
