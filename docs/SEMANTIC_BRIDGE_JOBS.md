# Semantic Bridge review and publication

The Semantic Bridge panel in the Ontology Mapper supports saved previews, explicit mapping selection, approval, publication status, recovery, and JSON evidence downloads. PostgreSQL stores job records; the graph service writes mappings and their receipt in one Neo4j transaction. Spark/PySpark is not required for this review and publication flow.

## Automated tasks

Semantic Bridge separates **Map instance to ontology** from **Merge two ontologies**.

For instance mapping, select an import and ontology, then choose **Run automated mapping and publish**. The saved `bridge-validated-automation` workflow runs the governor, steward, and governor. `validated-only-v1` publishes only eligible, automatically validated, warning-free, unambiguous rank-one matches with confidence at least 0.9. Other candidates are held with reasons. This is deterministic policy validation, not LLM self-approval. Starting the task delegates publication using connected governed credentials; each publication retains policy evidence.

For ontology merging, select two different retained RDF ontologies and choose **Run automatic merge and create draft**. The `ontology-union-automation` workflow creates a saved union preview, evaluates it with the steward, and applies `conflict-free-union-v1` through the governor. Conflicting explicit declarations or functional literal values hold the merge. Automatic union preserves entity identities; reviewed identity consolidation is available under Advanced. The resulting registry draft retains source IDs, changes, actor, and policy provenance. It is not automatically approved or published to Neo4j, and these checks do not establish full logical consistency.

Both automation panels refresh running tasks and expose pause/resume/cancel when supported by the server. An unconfirmed submission blocks repeat execution, including after reload; recover its ID from workflow history. Credential renewal preserves workflow bookmarks, which contain no approval token. An inaccessible run cannot be cleared to bypass recovery. Manual merge actions stay disabled while automatic merging is active or unverified.

Process-mode submissions return their workflow ID after the run is persisted, before tool execution completes. Reader ownership is independent of the publication approver. Receipt reconciliation supports automatic mapping publication and automatic merge without replaying writes; merge receipts verify saved preview provenance and retained artifact bytes. Merge reporting distinguishes original RDF duplicates from statements collapsed by reviewed identity consolidation.

Production verification still requires the customer's PostgreSQL, Neo4j, service credentials, and running APIs.

## Advanced manual workflow

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
- Route `/api/v1/workflows` to the agentic service. Use API-key authentication (`AUTH_MODE=token`) for this deployment. It uses `GRAPH_READ_TOKEN` for reads and `AGENTIC_APPROVAL_TOKEN` plus the approver name for approval. The UI's bootstrap fields hold credentials only in component memory.
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
