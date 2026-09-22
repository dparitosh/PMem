# Semantic Bridge review and publication

The Semantic Bridge panel in the Ontology Mapper supports saved previews, explicit mapping selection, approval, publication status, recovery, and JSON evidence downloads. PostgreSQL stores job records; the graph service writes mappings and their receipt in one Neo4j transaction. Spark/PySpark is not required for this review and publication flow.

## Operator workflow

1. Select the imported instance and target ontology in Ontology Mapper.
2. In **Preview → review → publish**, choose **Create preview**. No mappings are selected automatically. Preview does not publish mappings, memory facts, or modification events.
3. Review source, target, confidence, and validation messages. Select eligible mappings and confirm that you reviewed them.
4. Choose **Publish approved mappings** using an authorized approver identity.
5. Read the publication status and download evidence. The publication receipt records the applied count and approver.

Save the preview ID for recovery. The browser remembers that ID for the selected inputs in session storage; it does not store credentials. **Load preview** restores the saved preview and any existing publication selection. After a timeout, use **Refresh publication status** or **Retry same publication**. The backend checks the graph receipt before republishing. A publication's candidate selection cannot be changed; create a new preview for a different selection. A stale source or ontology requires a new preview and review.

Manual mapping drafts in the older mapper controls are not submitted by this panel. Only selected candidate IDs from its saved preview are published. Direct `instance.link` requests with `apply_links=true` are rejected.

## Deployment requirements

- Use the root installation and runtime configuration described in [customer release instructions](../infra/deployment/CUSTOMER_RELEASE.md).
- Agentic service needs the configured PostgreSQL registry and access to imported artifacts, ontology metadata, and graph reads. Job namespace: `semantic_bridge_jobs_v1`.
- Set `GRAPH_SERVICE_URL` and a server-only `GRAPH_PUBLICATION_TOKEN` shared by agentic and graph services. Never compile this token into frontend environment variables. Restrict graph publication endpoints to the service network.
- Graph service requires `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASS`, and `NEO4J_DATABASE`. Its database identity must be able to create the unique `DepoBridgePublication.publication_id` constraint and write mappings, receipts, and change records.
- Route `/api/v1/workflows` to the agentic service. Use the configured trusted gateway reader/approver identity in production. Bootstrap token mode uses `GRAPH_READ_TOKEN` for reads and `AGENTIC_APPROVAL_TOKEN` plus the approver name for approval. The UI's bootstrap fields hold credentials only in component memory.
- Use TLS for browser and service traffic. Approval credentials must be excluded from proxy/body logs.

## Behavior and release limits

Requests currently execute synchronously with durable job records; this is not a background queue or Spark pipeline. Previews are limited to 2,000 candidates. Publication serializes each stable publication ID using a PostgreSQL advisory lock and reconciles a durable graph receipt after response loss.

Source and ontology snapshots are checked before publication. The graph transaction checks source/target cardinality and rolls back if the number of written rows differs. Full isolation against concurrent external graph/schema writers is not established; customer acceptance must exercise their mutation paths and concurrency behavior.

The graph transaction records a `DepoBridgeChange` event with the receipt. An OSLC TRS delivery consumer is not implemented by this change. Optional agent memory facts are written only during publication when `AGENT_MEMORY_ENABLED=true`.

Job read access follows the configured reader role, not per-user ownership. There is no automated retention policy. Define access, backup, retention, and OSLC delivery requirements before customer rollout.

## Bug-fix verification (2026-09-22)

- Structured API validation errors now display a safe message instead of crashing React or echoing submitted input. Wrong-source previews display a specific recovery instruction.
- Loading a preview keeps candidate selection locked until publication status is recovered. A confirmed missing publication unlocks a fresh review; connection failures do not.
- Snapshot comparisons normalize unordered ontology lookup collections, preventing false stale-preview errors when graph query results arrive in a different order. Changes to target metadata still invalidate the snapshot. Previews created before this normalization may need to be recreated.
- Candidates missing source identifiers or using unsupported target types cannot be approved. Reconciliation requires both the saved request digest and the matching publication ID, preventing incomplete or unrelated receipts from marking a job published.

Verification: 34 backend tests and 8 UI tests passed. These tests cover the cases above plus existing semantic workflow behavior; they do not certify live graph publication or the full application.

Focused unit/API tests use an in-memory registry and graph fakes. Live PostgreSQL/Neo4j integration, trusted-gateway identity, graph concurrency, and a deployed browser acceptance run remain required. Dependency installation also reported 11 frontend vulnerabilities (4 moderate, 7 high); assess and remediate the dependency audit before release.
