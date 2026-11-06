# Graph operation sources

GraphQL graph queries read Neo4j through the graph service. Job and product queries read their owning control-plane services.

Ontology agent bridge planning with an ontology ID defaults to `data_source: "neo4j"`. It retrieves current mapping terms through the graph service, reports a graph digest, and rejects an empty projection. It does not silently substitute an artifact when graph access fails. Explicit `data_source: "artifact"` remains available for offline draft review. RDF structure review still uses retained artifacts because the property graph is not a lossless OWL reasoning model.

The reviewed merge button requests `publish: true` through the ontology governor. The ontology service retains the merge, moves it through review and approval, and publishes through the graph service using the existing publication lock and receipt reconciliation. A failure preserves the reviewed preview for retry. The API retains draft-only compatibility when `publish` is omitted or false. Automatic union policy remains draft-only; it does not authorize graph publication.

Instance bridge candidates use retained import rows and live graph targets; publication validates the current Neo4j source and target and commits links and a receipt atomically. This remains a hybrid source boundary. Graph-only instance discovery and lossless RDF reconstruction from Neo4j are not implemented by these changes.

## Graph read performance and identity

Explorer responses use Neo4j element IDs for node and relationship identity, with semantic IRIs retained in properties. Raw RDF projections continue to use IRIs so SPARQL conversion remains compatible. Clients must treat explorer IDs as opaque identifiers and refresh snapshots after database restore or node recreation. Bare-IRI traversal is accepted only when the published root is unambiguous.

Read queries share a driver pool that closes at service shutdown. Explorer edges are restricted to selected nodes. Traversal expands one bounded hop at a time instead of enumerating all paths; each query retains its configured database timeout. Node budgets may truncate reachable neighborhoods and the response reports this possibility. The UI ranks search hits without launching separate traversal probes for every candidate.

GraphQL JSON normalizes temporal values and rejects unsupported or non-finite values. Variable validation checks UTF-8 JSON bytes and total value count. Graph Explorer distinguishes authorization failures from service unavailability. Admin OpenAPI metadata import accepts only the latest request result.
