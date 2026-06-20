# 150-Bug Audit Tracker

Date: 2026-06-20

This tracker is a release-oriented audit backlog for the current codebase.
It spans backend API, Neo4j graph behavior, import/export services, frontend rendering, parsers, and ontology expressivity.

Status legend:
- `Open` = still needs implementation or validation
- `Patched` = already addressed in this branch, but kept here for release traceability

## Backend API
1. `API-01` CORS origin handling can drift from the active frontend host when the app is moved off `localhost`. Status: Patched.
2. `API-02` Several routes still import service classes inside handlers instead of using shared router/service wiring.
3. `API-03` The API surface still mixes v1 routes with deprecated compatibility routes, which complicates release hardening.
4. `API-04` Some error handlers return generic 500 responses without enough structured context for the UI.
5. `API-05` `/api/v1/ontology/{ontology_id}/reason` previously routed through the taxonomy facade instead of the canonical reasoning service. Status: Patched.
6. `API-06` `/api/v1/ontology/{ontology_id}/taxonomy` and `/reason` are still two separate flows that need clearer contract boundaries.
7. `API-07` API timeout settings are duplicated across frontend and backend instead of being negotiated from one source of truth.
8. `API-08` Several endpoints still accept loosely shaped payloads that can hide bad input until downstream code fails.
9. `API-09` Some responses return deeply nested status objects without a stable schema for client rendering.
10. `API-10` Import endpoints still expose both task state and artifact state in a way that can be confused by the client.
11. `API-11` Route naming still reflects legacy workflow language in places that should now be semantic-bridge first.
12. `API-12` Some handlers still rely on inline local imports instead of central dependency injection or shared adapters.
13. `API-13` Sample-query fallback logic can mask backend data issues by returning placeholder examples.
14. `API-14` Health/readiness endpoints can report partial readiness without enough detail for UI decisions.
15. `API-15` API-level pagination and limit defaults are inconsistent across graph, ontology, and reports routes.
16. `API-16` Some endpoints still return `JSONResponse` for content that should be downloadable as artifact files.
17. `API-17` `openapi.json` and UI-facing documentation are not yet aligned with the full export/download surface.
18. `API-18` The API layer still exposes legacy compatibility endpoints that should be hidden from normal users.
19. `API-19` Error logging is not always paired with structured response detail, making frontend diagnosis harder.
20. `API-20` Some routes do not distinguish between “no data” and “service unavailable”.
21. `API-21` File/path parameters are not consistently validated for safe artifact access.
22. `API-22` Some endpoints need explicit response models to reduce client-side guesswork.
23. `API-23` Cross-origin behavior for LAN IP hosts should be tested with both browser and API clients.
24. `API-24` The API surface still has too many one-off routes for the same underlying ontology life cycle.
25. `API-25` Some workflow endpoints still return results without clearly separating metadata, report, and export payloads.

## Neo4j Graph
26. `NEO-01` Graph projections can mix ontology schema nodes with instance data if the query scope is not explicit.
27. `NEO-02` Some graph views still depend on broad default limits that can over-fetch and obscure the current context.
28. `NEO-03` Relationship label normalization is needed so raw edge codes do not leak into the canvas.
29. `NEO-04` Node labels can still collapse to technical IDs instead of business-readable names.
30. `NEO-05` Metadata wrapper nodes can pollute graph context if the filter is not strict enough.
31. `NEO-06` Some graph traversals still assume one-hop expansion always produces a connected slice.
32. `NEO-07` Duplicate node merge safety depends on stable element IDs and consistent labels.
33. `NEO-08` Some graph routes still use legacy fallback endpoints when the primary data shape is missing.
34. `NEO-09` Graph search can be too broad and show a traversal slice instead of the matching nodes first.
35. `NEO-10` Contextual graph selection can drift when search, expand, and collapse all modify the same graph state.
36. `NEO-11` Some graph projections do not consistently preserve label, domain, and range metadata for ontology nodes.
37. `NEO-12` Graph connection state is still vulnerable to stale cache or stale closure effects on the client.
38. `NEO-13` Graph query results should validate that every visible edge has both endpoints in the visible slice.
39. `NEO-14` Some contexts can render orphan nodes, which makes the layout look broken even when the database is healthy.
40. `NEO-15` Search on very common terms can return too many matches without a clear relevance ordering.
41. `NEO-16` Some nodes represent XML tags rather than domain instances and need explicit filtering rules.
42. `NEO-17` Graph view nodes should highlight the root context consistently after any expansion.
43. `NEO-18` Expand/collapse needs stronger bookkeeping so a node can be toggled multiple times reliably.
44. `NEO-19` Graph view state should distinguish full graph, ontology graph, and contextual instance graph more strongly.
45. `NEO-20` `WHERE USED` style ancestry graph logic should not share the same state path as general graph search.
46. `NEO-21` Relationship thickness and arrow size need to be bounded by a consistent visual token system.
47. `NEO-22` Graph tooltip actions should only show when the selected node is truly actionable.
48. `NEO-23` Graph metrics endpoints should not be treated as a substitute for actual graph data.
49. `NEO-24` Graph queries should avoid returning disconnected clusters unless the user explicitly requests a global view.
50. `NEO-25` Graph rendering should preserve user focus and zoom state while new data is loading.

## Import Services
51. `IMP-01` Import workflows still overlap conceptually between structural upload, ontology creation, and semantic linking.
52. `IMP-02` `instance.link` depends on retained artifacts, so stale import state can leak into bridge generation.
53. `IMP-03` Some files still use legacy fallback parsing paths when the unified import service should be canonical.
54. `IMP-04` Large-file commits can hit gateway timeouts if progress is reported only at the end.
55. `IMP-05` Import stage labels do not always match the actual backend execution order.
56. `IMP-06` Progress can appear to hover at 92-94 percent while relationships are still being written.
57. `IMP-07` Some ontology selection fields appear multiple times in the UI, which confuses the user about which one is active.
58. `IMP-08` File metadata capture and semantic mapping are still too tightly coupled in some import flows.
59. `IMP-09` The same file can be treated as both a source document and an ontology source if the workflow is ambiguous.
60. `IMP-10` Import tasks should expose a clear retry path that preserves parsed state after timeout.
61. `IMP-11` Batch commit logic needs stronger backpressure signaling for very large relationship sets.
62. `IMP-12` Some import steps do not make the difference between preview, verify, and load explicit enough.
63. `IMP-13` Persisted jobs can be resumed in the frontend without a freshness check against the backend snapshot.
64. `IMP-14` Commit error handling should not overwrite the useful parsing state from earlier stages.
65. `IMP-15` Import workflow recommendations can suggest incompatible flows if file-type inference is too coarse.
66. `IMP-16` Some generated TTL files are created during import but not surfaced as first-class artifacts.
67. `IMP-17` Ontology creation workflows need clearer namespace and prefix capture rules.
68. `IMP-18` Some file-type branches still fall back to generic parsing when a specialized parser should be used.
69. `IMP-19` Import state does not always separate ontology creation from instance ingestion.
70. `IMP-20` Structural import can still create metadata-like nodes that later pollute contextual graph search.
71. `IMP-21` Relationship batches should be written with indexed merge keys only.
72. `IMP-22` The import UI can suggest a workflow before the user has enough context to know if it is valid.
73. `IMP-23` Some import timeouts are still handled as hard failures instead of resumable background jobs.
74. `IMP-24` The import preview and commit flows still use different state labels for related progress.
75. `IMP-25` Import result summaries need a cleaner separation between parsed rows, generated ontology, and committed graph counts.

## Export Services
76. `EXP-01` Ontology export was historically only available as an API payload, not a user-facing download. Status: Patched.
77. `EXP-02` Export currently depends on generated Turtle and RDFLib serialization, so source integrity must be validated before converting.
78. `EXP-03` `.owl`, `.rdf`, `.ttl`, and `.jsonld` exports need a single consistent naming and artifact scheme.
79. `EXP-04` Export downloads should not force expensive regeneration at click time for large ontologies. Status: Patched.
80. `EXP-05` Merge outputs need retained artifacts so users can download merged ontologies after the workflow finishes. Status: Patched.
81. `EXP-06` Semantic Bridge mapping exports should be available after link generation, not only after manual API calls. Status: Patched.
82. `EXP-07` Export errors should be logged without breaking the successful workflow result.
83. `EXP-08` Export artifact links should be surfaced consistently in the UI across import, merge, and semantic bridge flows. Status: Patched.
84. `EXP-09` JSON-LD export should preserve enough semantic bridge metadata to reconstruct the mapping review.
85. `EXP-10` RDF/XML export should be validated against the generated Turtle before download.
86. `EXP-11` OWL/XML export should not assume every Turtle graph serializes cleanly without RDFLib fallback.
87. `EXP-12` Export helpers should not overwrite or duplicate the user’s source file names.
88. `EXP-13` Artifact manifests should clearly distinguish reports from downloadable ontology files.
89. `EXP-14` Export endpoints need explicit timeout and content-disposition behavior for large files.
90. `EXP-15` Ontology merge export should be pre-generated in the background to avoid browser wait states.
91. `EXP-16` Semantic Bridge exports should be skipped cleanly when there are no candidate mappings.
92. `EXP-17` Exported merged ontologies should preserve source ontology context metadata.
93. `EXP-18` UI export controls should stay compact and not dominate the file action row.
94. `EXP-19` Export types need a single contract in frontend config, API client, and backend route naming.
95. `EXP-20` Some export artifacts are still report-shaped instead of file-shaped.
96. `EXP-21` Workflow artifact browsing should not require the user to know task internals.
97. `EXP-22` Long-running export or serialization should fail soft and create an error artifact rather than blocking the workflow.
98. `EXP-23` Export of merged ontology should support both ontology file and bridge mapping file sets.
99. `EXP-24` Export flows should be accessible from both Data Import and Semantic Bridge pages.
100. `EXP-25` Export responses should have consistent MIME types and filenames across browsers.

## Frontend
101. `FE-01` Graph Explorer is still the most visually fragile part of the app.
102. `FE-02` Search can still be mistaken for a graph dump if results and canvas are not clearly separated.
103. `FE-03` Contextual instance search needs a strict one-root, one-hop render contract.
104. `FE-04` Expand/collapse affordances can look active when they are not actually actionable.
105. `FE-05` Some graph toolbars are too wide and can overflow the screen on smaller viewports.
106. `FE-06` Toolbar buttons and icons need a consistent miniature size system.
107. `FE-07` Graph labels can overlap in dense canvases and make the page unreadable.
108. `FE-08` Search reset and chat refresh actions can flicker when state updates race.
109. `FE-09` Search results should be highlighted in the canvas, not only in a side list.
110. `FE-10` Search should be case-insensitive and should handle wildcard patterns predictably.
111. `FE-11` Some graph nodes still show technical IDs instead of domain labels.
112. `FE-12` Search input can be non-editable or appear blocked if the wrong overlay state is active.
113. `FE-13` Full graph, ontology graph, and contextual instance graph need distinct display rules.
114. `FE-14` Node tooltips can become blank if event handlers hold stale state.
115. `FE-15` Graph layout stability can degrade after repeated zoom, pan, and node click operations.
116. `FE-16` The page should not auto-refresh the graph while the user is exploring a search result.
117. `FE-17` Some view labels and helper text are redundant and reduce confidence.
118. `FE-18` Recommendation panels can use large alerts or oversized icons that feel unprofessional.
119. `FE-19` The frontend still has legacy/compatibility wording that should be reduced in visible labels.
120. `FE-20` Tab transitions can appear to lose selection state even when backend data is present.
121. `FE-21` The import pipeline UI can hide important workflow conditions behind too much explanatory copy.
122. `FE-22` Export controls should be visible after successful workflow completion, not buried in a separate page.
123. `FE-23` The ontology browser layout can overlap text and pagination if container sizes are not constrained.
124. `FE-24` Some action buttons rely on browser defaults rather than explicit compact UI styling.
125. `FE-25` The app needs stronger visual separation between review, search, and destructive admin operations.

## Parsers
126. `PAR-01` The OWL/RDF extractor path was previously advertised but not implemented. Status: Patched.
127. `PAR-02` OWL/RDF parsing needs an Owlready2-first, RDFLib-fallback strategy for sparse or unusual files. Status: Patched.
128. `PAR-03` The parser stack still has a TODO for a dedicated OWL/RDF extractor in the legacy abstraction layer. Status: Patched.
129. `PAR-04` XML parsing should distinguish true instance elements from XML wrapper metadata.
130. `PAR-05` PLMXML parsing should preserve id, uid, xmi:id, href, instanceRefs, and relatedRefs as stable references.
131. `PAR-06` Parser output should clearly track unresolved cross-references instead of silently dropping them.
132. `PAR-07` Some parsers still use regex-based extraction where streaming or tree-aware parsing would be safer.
133. `PAR-08` Parser fallback behavior should be logged with enough detail to support customer support.
134. `PAR-09` XSD-to-OWL conversion needs strict namespace preservation from the source schema header.
135. `PAR-10` XML parser outputs can create metadata nodes that should not be treated as domain instances.
136. `PAR-11` Large PLMXML files need streaming parse logic to avoid memory spikes.
137. `PAR-12` Duplicate IDs should be reported separately from duplicate labels.
138. `PAR-13` Parser-generated ontology classes should preserve source comments and annotations where possible.
139. `PAR-14` Parser-generated object properties should retain domain and range semantics instead of flattening to generic edges.
140. `PAR-15` Parser-generated TTL needs validation before it is committed or exported.
141. `PAR-16` Some parser modules still describe `legacy` or `fallback` behavior in a way that confuses release readiness.
142. `PAR-17` XMI parsing should preserve member-end and reference semantics consistently across exports.
143. `PAR-18` CSV and Excel parsers should clearly distinguish entity rows from attribute rows.
144. `PAR-19` Parser error handling should preserve partial output for review when full conversion fails.
145. `PAR-20` Generated ontology files should be immediately reproducible from the same input and metadata.
146. `PAR-21` Parsers should mark data-property candidates versus object-property candidates before merge time.
147. `PAR-22` The model should retain a provenance trail from parsed source element to ontology term.
148. `PAR-23` Parser output must keep semantic bridge metadata separate from core ontology semantics.
149. `PAR-24` Some parser adapters are still too coupled to specific file names and source directory assumptions.
150. `PAR-25` Ontology expressivity handling should not degrade complex OWL constructs into plain labels only.

## Ontology Expressivity
- `OWL-01` Class hierarchy should preserve `rdfs:subClassOf` and not collapse complex inheritance into a flat list.
- `OWL-02` Object properties should retain domain and range in both reasoning output and visual render paths.
- `OWL-03` Datatype properties should preserve datatype ranges instead of generic string fallback.
- `OWL-04` Annotation properties should be represented explicitly, not hidden inside generic metadata.
- `OWL-05` Individuals should be distinguishable from classes in both graph views and export artifacts.
- `OWL-06` Restriction constructs such as min/max cardinality should not be lost during conversion.
- `OWL-07` Equivalent-class and disjoint-class semantics need explicit handling.
- `OWL-08` Ontology expressivity should keep labels, comments, and synonyms for search and display.
- `OWL-09` Cross-ontology imports should not silently drop imported semantic terms.
- `OWL-10` SHACL validation should reflect OWL domain/range constraints as actual checks.

## Release Notes
- The highest-risk areas remain Graph Explorer, import timeout handling, ontology bridge clarity, and parser fidelity.
- The current branch already includes several Patched items; the rest are the remaining backlog for closure and hardening.
- For release, the next practical step is to turn this tracker into a working backlog board and close the `Open` items in Pareto order.
