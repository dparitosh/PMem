# Registry namespace ownership

The current deployment shares one PostgreSQL control-plane schema. The table below records literal registry namespaces and their code owners; dynamically constructed namespaces require manual inspection. These boundaries are code ownership conventions, not database permission isolation.

Changes to `backend/mesh_store.py` affect every consumer. Preserve atomic create, lease ownership, conditional updates, and migration compatibility when changing the registry. Run persistence and worker regression checks before deployment. Separate service credentials and database grants would require a further architecture change.

| Namespace | Consumer modules |
| --- | --- |
| `agentic_companion_jobs` | `backend/agentic_service/router.py` |
| `agentic_observability` | `backend/agentic_service/telemetry.py` |
| `agentic_sessions` | `backend/agentic_service/sessions.py` |
| `agentic_workflow_runs` | `backend/agentic_service/router.py` |
| `artifact_retention` | `backend/data_catalog_service/artifact_retention.py` |
| `catalog_products` | `backend/data_catalog_service/router.py` |
| `ceim_entity_resolution_cases` | `backend/ceim/resolution.py` |
| `data_job_definitions` | `backend/data_pipeline_service/job_definitions.py` |
| `data_job_runs` | `backend/data_pipeline_service/run_records.py` |
| `data_pipeline_workers` | `backend/data_pipeline_service/worker_status.py` |
| `data_product_approvals` | `backend/data_product_service/router.py` |
| `data_products` | `backend/data_product_service/router.py` |
| `dt_agent_runs` | `backend/agentic_service/router.py` |
| `ingestion_source_profiles` | `backend/ingestion_service/profiles.py` |
| `metadata` | `backend/depo_platform/metadata_repository.py` |
| `ontology_business_context` | `backend/ontology_service/business_context.py` |
| `ontology_catalog` | `backend/ontology_service/catalog.py` |
| `ontology_semantic_policies` | `backend/ontology_service/intelligence.py` |
| `ontology_semantic_workspace` | `backend/ontology_service/semantica_adapter.py` |
| `oslc_trs` | `backend/Services/oslc_trs_service.py` |
| `semantic_bridge_jobs_v1` | `backend/agentic_service/bridge_jobs.py` |
| `skos_vocabulary_releases` | `backend/ontology_service/vocabulary_service.py` |
| `sparql_federation_peers` | `backend/graph_service/federation_service.py` |
| `speed_path_events` | `backend/data_pipeline_service/speed_path.py` |
| `speed_path_reconciliations` | `backend/data_pipeline_service/speed_path.py` |
| `speed_path_sources` | `backend/data_pipeline_service/speed_path.py` |
