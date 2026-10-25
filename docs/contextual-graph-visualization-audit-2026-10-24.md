# Contextual graph visualization and agent audit — 24 October 2026

## Research findings

Reviewed current primary documentation on 24 October 2026. These are techniques to evaluate, not claims that a particular library or paper is universally best.

- Microsoft GraphRAG supports local entity neighborhoods, global community summaries, and DRIFT (local traversal with community context). DRIFT was introduced on 31 October 2024; it is not a new 2026 discovery. Useful PMem direction: start from an exact business object, retrieve bounded source-backed context, broaden only when the question requires it, and retain evidence/gaps. PMem's current selected-node investigation uses its existing read tools; it does not implement Microsoft's DRIFT indexing/query stack. Sources: https://microsoft.github.io/graphrag/ and https://www.microsoft.com/en-us/research/blog/introducing-drift-search-combining-global-and-local-search-methods-to-improve-quality-and-efficiency/
- Current Sigma documentation describes WebGL rendering, GPU text rendering and visibility/performance controls. It recommends profiling pixel overdraw, blending, edge antialiasing and picking costs. A renderer migration is an option for genuinely large views, not a prerequisite for bounded business neighborhoods. Do not apply version-specific Sigma APIs to PMem's D3 renderer. Sources: https://www.sigmajs.org/concepts/rendering/ and https://www.sigmajs.org/how-to/technical/performance/
- Neo4j's contributed GDS agent exposes graph algorithms such as centrality, community detection, paths and similarity through tools. PMem should first verify GDS availability, algorithm memory needs and tool authorization. No GDS plugin or external MCP server was installed during this change. Source: https://github.com/neo4j-contrib/gds-agent
- D3 recommends worker computation for large static force layouts. Existing incremental position reconciliation should be retained; benchmark main-thread layout before adding a worker. Source: https://d3js.org/d3-force/simulation
- Colors must have accompanying labels/shapes/patterns when conveying meaning. Source: https://www.w3.org/WAI/WCAG22/Understanding/use-of-color.html

## Audit and implemented corrections

1. Dense ontology/individual views previously enabled every node label; the generic branch's density guard was bypassed. Suppress bulk labels in dense views, keep small neighborhoods readable, and reveal exact names on hover/active focus. Dense instance relationship labels are now bounded too. Search remains bounded; no graph records are deleted or relabeled.
2. Fixed light-only legend surfaces, canvas gradient and label halos. Shared graph theme now consumes application theme tokens. Labels use neutral theme text rather than node-fill luminance guesses; label background and text no longer assume white.
3. Added a compact selected-node investigation panel that calls the existing `graph-analyst` read-goal workflow. Clicking a node passes its retained graph identity; a focused search result can also supply the context. The question carries the ontology version where applicable, visible-slice counts, read-only restrictions and explicit instructions to cite returned evidence and distinguish references, mappings and inferences. Selection is independent from search and does not trigger graph publication.
4. Search and previous layout-state behavior are preserved. Regression checks: 18 tests passed across graph display policy, search races, graph page and scoped investigation. Existing React test-utils deprecation warning remains.

## Remaining acceptance and staged improvements

- Verify live provider/tool availability and grounded agent answers. A mounted panel or passing component test is not proof of a successful model investigation.
- Validate focus label behavior and selection after expansion, reset, ontology switching and delayed responses. Dynamic diagrams need keyboard/list alternatives beyond the existing SVG image role.
- Add a validated evidence-subgraph result contract before highlighting agent-returned paths. Only highlight IDs actually returned by authorized tools; never create implied source links from prose.
- Separate source references, semantic mappings, declared axioms and inferred conclusions visually with labels and non-color cues. Do not infer provenance from a high score or line style alone.
- Introduce BOM hierarchy, process flow and traceability layouts incrementally, retaining original identities and positions. Group duplicate-looking master/revision records only in presentation, with explicit expansion.
- Benchmark 100/500/1000+ node workloads (first usable render, frame time while zooming/dragging, layout settling, heap after repeated page switches). No FPS or renderer-capacity claim was established in this pass.
- Community summaries, evidence-aware retrieval, worker layouts and WebGL remain separate evaluated enhancements. No new embedding/model/GDS dependency was installed.

Deployment backup: `D:/GenAI_Projects/Apps/PMem/logs/business-demo-backup/contextual-graph-20261024-191040`. Frontend-only deployment; backend and databases retained. Live verification is recorded in the component audit as completed, with concrete limitations.

## Live verification

- Deployed asset: `/assets/index-KUZFJwFI.js`. Search `Undesired noise` retained the focused result of 3 nodes and 4 Master Reference links and selected the change-request context for investigation.
- Small-neighborhood labels remained visible. Dark theme used light label text (`rgb(241,245,249)`) and a dark investigation surface (`rgb(31,41,51)`); original light theme was restored.
- The scoped read-only goal was accepted, then ended with `goal rate limited`, with zero recorded tool actions. End-to-end evidence retrieval and answer quality are therefore NOT verified. Resolve provider rate limits before demo acceptance; no graph writes occurred.
- Screenshot: `outputs/contextual-graph-focused.png`. Dense-policy behavior is covered by tests; comprehensive live workload/FPS benchmarks remain pending.

## Grouped overview implementation (2026-10-24)

The default all-scope overview now aggregates the current visible slice by retained ontology reference, then explicit import provenance, then an unassigned group. Entity graph remains an explicit alternative; search still opens its focused entity graph. Group selection filters the slice, directed/typed cross-group connections remain inspectable as a table, and entity selection sets the existing agent investigation context. Same-name entities and ontology versions retain separate identities. Entity rows are capped at 50 with a search field.

Live audit found 528 records with the PLMXML namespace reference rather than the registry's version ID. The UI does not equate that namespace with a version, and separately lists registered ontologies without exact-ID representation in the slice. No graph mutation or identity migration is performed. A global bounded overview can omit ontologies: group counts are explicitly slice counts. Full database-wide grouped totals, fair per-ontology sampling, cross-scope pagination and a real published two-ontology acceptance fixture remain pending. This change does not claim those backend capabilities.

Validation: 12 tests across grouping, group filtering/identity selection, search races and graph page behavior; production build. Backup: `D:/GenAI_Projects/Apps/PMem/logs/business-demo-backup/ontology-groups-20261024-223325`. Databases and backend were not restarted.

Live deployment verified with asset `index-B7BvPSlG.js`: one retained PLMXML namespace group, 528 entities and 478 internal links. Two same-name Bearing Failure Simulation records remain separately selectable by identity; selecting the reviewed record updates the investigation context. Switching to Entity graph renders 528 nodes, and switching back restores grouped mode. Screenshot: `outputs/ontology-group-overview.png`. The registered Teamcenter version is listed separately because its exact registry ID is not represented in this slice; no namespace/version equivalence was invented.
