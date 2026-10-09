# Confirmed high-priority release defects

> Dated audit record: use [the current audit index](README.md) for latest validation and acceptance status. Findings and test counts below belong to their recorded review; they are not a current release certificate.

This review confirms ten distinct high-priority defects. It does not claim twenty P1 defects without evidence. Priority reflects the documented worker, gateway and passwordless Neo4j deployment requirements.

| # | Defect and failure trigger | Correction | Source |
|---|---|---|---|
| 1 | An expired/reassigned worker claim can overwrite a newer completion, failure or retry state. | Atomic PostgreSQL transition fences status, worker, attempt and live lease. | backend/mesh_store.py; backend/data_pipeline_service/run_records.py |
| 2 | PostgreSQL failure during polling or failure recording terminates the pipeline worker. | Retry polling and defer recovery/status writes with safe type-only logging. | backend/data_pipeline_service/worker.py |
| 3 | A single reconciliation/control-plane exception terminates the catalog outbox loop. | Preserve the worker loop and retry on the next interval. | backend/data_product_service/worker.py |
| 4 | Simultaneous writers of the same digest observe content before metadata exists. | Serialize writers with OS locks released on process exit; repair interrupted pairs. | backend/artifact_store.py |
| 5 | File ingestion copies directly to the published path and can retain partial bytes or a changing source under the wrong digest. | Copy to a temporary file, validate digest, then replace content and metadata. | backend/artifact_store.py |
| 6 | Configured passwordless Neo4j is rejected by graph health, reads and publication. | Use auth=None when NEO4J_AUTH_MODE=none. | backend/graph_service/neo4j_publisher.py |
| 7 | Supported Neo4j URL/username/password aliases are ignored by the graph publisher, selecting the wrong connection. | Honor the same aliases as deployment diagnostics. | backend/graph_service/neo4j_publisher.py |
| 8 | Read-only SPARQL accepts external FROM datasets, allowing remote fetches despite blocking SERVICE. | Reject external dataset clauses through the shared local/federated gate. | backend/graph_service/sparql_service.py |
| 9 | Graph reads have no server query deadline; expensive traversals can occupy request workers indefinitely. | Apply bounded Neo4j query timeouts; health uses a three-second query deadline. | backend/graph_service/neo4j_publisher.py |
| 10 | Speed publication marks a reconciliation published for any HTTP 200 response, even one reporting a failed/pending publication. | Require a published response before changing the durable state. | backend/data_pipeline_service/speed_router.py |

Additional hardening rejects malformed digest paths, storage escape and metadata identity mismatches. Earlier service routing/CORS and graph visualization defects are documented in their separate reviews and are not counted again here.

## Validation limits

Focused dependency-free tests exercise concurrent artifact writes on Windows, interrupted-pair recovery, metadata/path rejection, fenced SQL construction, worker outage recovery, SPARQL gating and Neo4j no-auth/alias configuration with mocked drivers. Routing/credential tests and package/script parsing also passed. Full PostgreSQL concurrency, actual RDF execution, live Neo4j query deadlines and end-to-end UI/job publication still require the deployment environment. These are code fixes, not customer release certification. No packages were installed and no commit/push was performed.
