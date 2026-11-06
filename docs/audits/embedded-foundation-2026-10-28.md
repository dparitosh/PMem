# Embedded foundation and actual OWL-DL execution — 2026-10-28

Brand: **DEPO | Semantic Intelligence**. One line: **Engineering knowledge, connected. Decisions, grounded.**

This implementation ships public PCA IDO 4.2 unchanged with attribution and an independently versioned DEPO business module. Source and module hashes are verified before use. No customer terms, instances, identities, publications or credentials are rewritten. Inclusion is not ISO certification or approval of source-to-foundation mappings.

The new Python adapter invokes a real HermiT 1.4.5.519/OWLAPI Java worker. It checks the completed OWL 2 DL profile, reports consistent/inconsistent/unsupported/unknown, distinguishes unsatisfiable classes from global inconsistency, blocks unresolved imports and never publishes graph changes. Worker execution is bounded and separate from Semantica structural/SHACL validation. Process isolation is not an OS sandbox.

Existing Governor, Steward, Inference Advisor and Graph Analyst receive scoped read tools for reference inspection and retained-ontology consistency. Other semantic agents can inspect the foundation. Companion instructions keep physical objects, designs, documents and activities distinct and require actual instance evidence. No new replacement agent was created. Live LLM generation remains disabled and its response quality is not certified by deterministic reasoning tests.

Inference Workbench now exposes foundation availability and an explicit consistency action with business-facing outcomes and a technical evidence drawer. Selection changes abort browser reads and discard stale results. Read-goal tool budgets accommodate the bounded worker deadline. The local worker persists artifact/foundation/adapter-bound evidence through the existing PostgreSQL registry.

## Executed evidence

- The broader backend selection passed 135 cases, including real Java reasoning, existing governance/industrial boundaries, tool/prompt contracts and adversarial secret/context tests for all roles. Later final engine tests separately cover added source-size/admission guards; see their exact JUnit count. These selections overlap and must not be added as unique coverage.
- 23 UI cases passed for foundation controls, stale selection, Inference Workbench, application shell and landing page.
- One release-packaging test built a disposable ZIP containing the generated worker, foundation and notices, and rejected worker tampering.
- Startup's standalone offline self-check returned ready: the complete embedded IDO + DEPO module was consistent, with no unsatisfiable named classes.

The adversarial property-punning fixture initially exposed OWLAPI repairing input before profile checking. Automatic illegal-punning repair is now disabled, ambiguous property declarations are rejected before conversion, and unparsed statements yield unsupported. OWLAPI strict streaming mode rejected valid forward references in IDO Turtle restrictions; the implementation instead verifies the completed profile and discloses guessed declaration counts. Both consistent and inconsistent fixtures execute the real reasoner. Old graph test fixtures were updated to supply current search contracts rather than bypassing ambiguity behavior. New prompt-tool schemas come from the current owning service OpenAPI, while original audit captures remain historical.

## Operational qualification limits

See [the operator guide](../EMBEDDED_SEMANTIC_FOUNDATION.md) for build, packaging, Java prerequisite, limits and offline import scope. The original public IDO is a proposal snapshot. Classification listings are bounded. External graph instances, unresolved third-party imports, automatic source alignment, minimal inconsistency explanations and standards-conformance certification are not provided by this endpoint. Existing publication approval policy is unchanged.

Release acceptance still includes dependency security/license review of the complete Maven closure, customer Java distribution testing, large-model resource testing, human review of domain mappings and live-model factual-response tests. Historical reports saying the OWL-DL adapter was unimplemented describe the earlier code snapshot, superseded by this implementation; their original test counts are retained.

Current raw evidence and deployment hashes are under `embedded-foundation-2026-10-28/`. The generated JAR is built locally and included by the release packager after verification; it is deliberately not committed as a 22 MB Git binary. Commit the new source/manifest/assets before packaging the real repository release. The fixture ZIP test does not mean the uncommitted repository has already been released or pushed.
