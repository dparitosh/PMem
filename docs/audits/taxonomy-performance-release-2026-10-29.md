# Taxonomy performance and release-blocker work — 2026-10-29

## Confirmed bottleneck

The installed AP242 taxonomy request returned 10,000 nodes and 8,391,840 bytes in 2.522 / 2.461 seconds before browser model/rendering work. Browsing copied the full cached inventory before trimming, and the frontend requested the large default. The UI rendered false zero/empty states during the initial load. Alignment/inference waited for all semantic responses before committing taxonomy.

## Changes

- Taxonomy HTTP endpoint supports bounded limit/offset/query, validated by FastAPI. Existing callers retain the default contract; Ontology Junction explicitly requests 500 terms.
- Search matches retained label, term identity, IRI and definition; stable ordering and continuation offset keep remaining retained terms accessible. Returned relationships have both endpoints in the slice. Page totals distinguish matched retained terms from returned rows and full inventory totals.
- The browser path projects cached inventory before defensive copying. Full inventory consumers retain their independent complete copy.
- Ontology Junction has Previous/Next terms controls, debounced server search, slice-scope explanation, cancelled-request protection, and early taxonomy display independent of parallel reasoning.
- Empty browser panels do not mount before taxonomy arrives. No change to validation, publication authorization, ontology files or database records.

## Automated checks

11 backend taxonomy/scope/runtime tests and nine frontend ontology regression tests passed. A separate 42-case recovery/publication/persistence/retention suite passed. These totals cover distinct suites. Production build passed; existing chunk-size warning remains.

## Release limits

Customer reboot/restore qualification and live LLM answer acceptance cannot be established by local mocks. LLM remains disabled by user instruction. The earlier navigation redirect has not been reproduced in a fresh tab; route/history regression tests and live navigation passed, but no root cause is claimed. Independent prior database restore evidence does not establish a coordinated customer restore point. Production acceptance remains gated on the target deployment evidence in infra/deployment/CUSTOMER_RELEASE.md.

## Measured installed results

Before: 10,000 nodes, 8,391,840-byte response, 2.522 / 2.461 seconds on the already-running service.

After paging: first retained AP242 request after restart took 34.894 seconds to build the in-memory inventory; subsequent page/search requests took 0.155–0.162 seconds. Initial response was 275,533 bytes (500 nodes), approximately 97% smaller. The next page had distinct term IDs; all returned relationships had both endpoints in the page. Search found 908 matching retained terms for Product; an excessive limit returned 422 and a request without credentials returned 403. All ten readiness endpoints passed.

Cold-start follow-up: added disposable content/version-keyed gzip taxonomy caching beside retained RDF. Two independent processes measured 35.695 seconds to build and 1.198 seconds to reuse the same retained 71,041-term inventory. The cache preserves complete inventory for existing consumers and is never a reasoning/publication authority. Missing, corrupt, unsupported or stale caches rebuild; unavailable writes do not block browsing. Cache tests validate artifact/metadata invalidation and corrupt input recovery. Fourteen taxonomy/cache/scope tests and six release-fingerprint tests passed. Release preflight now requires the cache module. INSTALLATION.md documents deployment and cache behavior.

Final frontend integration also requests a property-only retained slice when Properties is selected, avoiding a false empty property list on a class-first page. Switching ontology resets the browser's local selection. Search is applied once on the server for paged responses, including label/identity/definition matches. The retained ontology selection and merge-workspace regression suites passed: 22 frontend cases. Separate backend checks comprise 14 taxonomy/cache/runtime/scope cases, six release-completeness cases, and 42 recovery/persistence/retention cases (62 distinct backend cases).

After persistent-cache deployment and managed restart, the HTTP first page completed in 0.992 seconds; repeat page 0.247 seconds, next page 0.128 seconds, search 0.156 seconds. The initial response remained 275,533 bytes. See outputs/taxonomy-performance-live-20261029.json for measured local results. These are local measurements, not customer latency guarantees.

Final typed-page build: `/assets/index-PrRHxjWT.js`; all ten APIs and all three workers completed managed startup. Latest HTTP checks measured first page 1.195 seconds, repeat page 0.154 seconds, next page 0.708 seconds, search 0.187 seconds, property-only page 0.064 seconds. Property filtering reported 17,827 retained properties and returned 500, preserving access beyond the class-first slice. Query/authorization and page-integrity checks remained passing.

The paged browser explicitly reports unresolved parent/domain/range as outside the slice or undeclared; it does not infer absence from a page boundary. Taxonomy summaries remain slice counts. Customer acceptance still must include full-artifact validation and authorized publication; bounded browsing is not logical validation.
Final frontend after slice-safe labels: `/assets/index-CHbYpsF_.js`; build and browser authentication/ontology read checks passed. No LLM calls, schema reset, graph publication or credential rotation were performed.

Boundary semantics refinement: each returned term now carries compact declared parent/domain/range references and child count from the full cached retained inventory. The browser uses these declarations even when the referenced class is outside the returned node page. It does not fabricate in-slice graph edges. This preserves semantic usefulness while retaining the small browser payload. A dedicated frontend test verifies out-of-page domain and range labels, and backend coverage verifies declarations without boundary-edge invention. Final ontology frontend regression suite: 23 passing cases.

Final semantics-preserving measurements supersede the earlier payload-only measurements above: first post-restart request 1.321 seconds, warm 0.217 seconds, next page 0.225 seconds, search 0.273 seconds, properties 0.159 seconds. The initial 500-term page is 336,914 bytes including parent/domain/range/child-count metadata, approximately 96% smaller than the original 8,391,840-byte payload. Page identity, in-slice endpoint integrity, 422 invalid-limit and 403 missing-credential checks passed. All ten APIs were ready. Final frontend asset: `/assets/index-DZmvqaUM.js`. Properties and Axioms use the full table workspace rather than an empty class-hierarchy panel.

Final acceptance build: `/assets/index-BSoVjqNL.js`. Boundary domain/range axiom counts use complete retained declarations, rather than only graph edges in the current node page; the dedicated regression passes. Startup verified browser authentication and ontology reads. The earlier frontend asset identifiers in this chronological record are superseded by this final build.
