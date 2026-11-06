# DEPO | Semantic Intelligence

**Engineering knowledge, connected. Decisions, grounded.**

## Shipped foundation

DEPO ships the unmodified public PCA IDO core 4.2 Turtle snapshot, its source/version IRI, SHA-256 manifest and CC BY-SA attribution. It is the public FDIS-proposal artifact retrieved 2026-10-28, not a claim of published ISO certification. DEPO business core 1.0.0 separately defines physical parts, part designs, engineering documents, requirement specifications and manufacturing activities as subclasses of IDO categories. Original PCA terms are not renamed or overwritten. These are reference definitions; customer source terms are not automatically equivalent to them.

The resources live in `backend/ontology_service/resources/foundation/`. `foundation.py` verifies both snapshots and assembles them in memory without runtime network access. The source ontologies, business graph and existing approved publications remain intact. Importing IDO alone is not approved alignment. The coverage report measures explicit subclass reachability; it does not judge the meaning of a proposed mapping or establish ISO conformance.

## Build and customer installation sequence

1. Use Java 17 or higher and Maven to build the worker on the release-build machine. The local executed qualification used Microsoft OpenJDK 25.0.4; repeat acceptance on the supported customer Java distribution before release.
2. From the repository root run `powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\infra\reasoner\build.ps1`. For an explicit Maven executable add `-Maven 'C:\Tools\apache-maven\bin\mvn.cmd'`. The build obtains the pinned HermiT 1.4.5.519 and OWLAPI dependency closure from Maven repositories. It copies the assembled JAR to `backend/ontology_service/resources/reasoner/depo-owl-dl.jar` and writes its SHA-256 manifest. No system settings or customer credentials change.
3. Review the resolved dependency tree and licenses; retain `infra/reasoner/THIRD_PARTY.md`, original dependency notices, source/build recipe and PCA attribution. The generated 22 MB worker JAR is excluded from Git but deliberately included by the release packager after checksum verification. Track all new source, manifests and ontology assets before creating the release.
4. Run the test selections listed below and the normal release checks. `python infra/deployment/build-release-package.py --output <new-release.zip>` requires the complete tracked foundation sources/notices and verified generated JAR. A source checkout without the built JAR is not a complete reasoning-enabled customer package.
5. Install Java 17+ on the customer host. The service account must be able to execute `java` and write to its ordinary temporary directory. Optionally set `DEPO_REASONER_JAVA` to the absolute Java executable in root `.env.local`. No Java or Maven download occurs when the application starts. Maven is not required on the customer host when the release contains the verified worker.
6. Deploy the complete release and use the normal repository-root installer/updater. It preserves PostgreSQL, graph data, credentials and existing artifacts. Restart through `manage-depo.ps1` after changing configuration. A missing Java runtime or bad/missing JAR makes this capability unavailable; it does not make unrelated APIs falsely claim a reasoning result.
7. Reconnect browser access. In Ontology Junction → Inference Workbench inspect **Embedded semantic foundation**, select a retained ontology, then choose **Check OWL-DL consistency**. No LLM is needed. No ontology or instance publication occurs.

## Execution contract

`GET /api/v1/ontologies/foundation` reports the embedded reference and engine availability. `GET /api/v1/ontologies/{ontology_id}/consistency` checks the retained ontology plus the embedded foundation under authenticated read access. The selected file is obtained only through the owning ontology catalog; callers cannot provide process commands or arbitrary file paths.

The API validates RDF input, blocks unknown imports and flattens only approved embedded foundation imports. Other ontology imports require an approved resolved artifact workflow and currently return `unknown/unresolved_imports`; the worker never silently downloads them. The worker receives a generated local Turtle file, uses OWLAPI without illegal-punning repair, rejects unparsed statements, checks the completed OWL 2 DL profile and executes HermiT. OWLAPI's strict streaming mode is not used because it rejects valid forward references in Turtle restrictions; profile verification runs after loading, and ambiguous property declarations are rejected before conversion.

One process executes at a time per ontology API process; overlapping checks return `unknown/reasoner_busy`. Maximum input: 500,000 source triples and 64 MiB serialized input. Worker heap: 1 GiB. Default process deadline: 60 seconds; `DEPO_REASONER_TIMEOUT_SECONDS` is bounded from 5 to 180 seconds. Output is capped at 1 MiB; class lists and classification rows are bounded. Timeout kills the Java subprocess and never means success. A browser navigation cancels the UI read, but the server may finish its bounded read-only computation and retain its evidence.

Possible results are `consistent`, `inconsistent`, `unsupported` and `unknown`. `consistency_verified=true` means a consistency decision was executed for the stated scope; inspect `status` to distinguish consistent from inconsistent. A consistent ontology may still contain unsatisfiable named classes; `modeling_coherent=false` and the reported class count make that distinction explicit. Unknown results do not establish either consistency or inconsistency. Results include artifact hash, foundation bundle hash/version, engine version and check time.

Evidence is stored in the existing generic PostgreSQL registry namespace `ontology_dl_evidence_v1`; no new SQL table/migration is needed. Reuse is bound to source, foundation, worker and Python adapter digests. This is validation evidence, not a lifecycle approval. The check does not include instances stored only in the graph database, automatically materialize conclusions, remap source classes or change existing publication policy.

## Existing agents and answers

See [Semantic evidence in engineering work](SEMANTIC_DECISION_LOOP.md) for the implemented business workflow across merging, instance linking, Recommendations, Companion, Data Products and Data Flow, including the evidence boundaries.

- Governor, Steward and Inference Advisor can read the embedded foundation and request an explicit consistency check for a selected retained ontology.
- Graph Analyst has the same read tools for scoped recommendation investigations. Consistency is not an interchangeability/similarity score or change-impact completeness proof.
- Other semantic/context agents can read the reference vocabulary to distinguish designs, physical instances, documents and activities. Tool results remain untrusted evidence, not instructions or approvals.
- Companion instructions use the same conceptual distinctions while preserving instance grounding: vocabulary alone cannot establish PMI ownership, requirement satisfaction, a measured property or a missing business relationship. Model responses still require a configured LLM; deterministic reasoning works with LLMs disabled.

## Acceptance and limits

Real Java-worker tests are in `backend/tests/test_embedded_owl_dl.py`; they assert that the engine exists rather than silently skipping. Tests cover foundation integrity and coherence, contradictory instances, unsatisfiable classes, profile violations, blocked imports, timeouts, busy execution and existing-agent bindings. UI tests cover verified/unknown results, disabled engine and stale-selection cancellation. Existing structural/SHACL tests remain separate.

The integration is a functioning OWL-DL execution path, not proof of complete standards conformance, semantic correctness of customer mappings or operational qualification for every large AP242/QIF model. Reasoner process isolation is not a security sandbox; use the existing restricted service account. Customer Java compatibility, Maven dependency security/license review, realistic large-model resource qualification and business acceptance of domain alignments remain release checks. No OS sandbox, full minimal-inconsistency explanation service or automatic source-alignment approval is claimed.
