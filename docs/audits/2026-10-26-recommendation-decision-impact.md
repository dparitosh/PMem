# Engineering recommendations and change impact — implementation review

Date: 26 October 2026

## Implemented capability

The graph service and older similarity/change-impact callers now use one shared engine. The previous separate similarity and change-impact algorithms were replaced by compatibility adapters. The old radial illustration was removed; the Recommendations page renders recorded dependency paths and supports keyboard inspection of business records.

Similarity retrieves up to 200 typed parts, including differently named candidates. It excludes different business categories and compares material, dimensions, mass, tolerance, specification, revision, configuration and effectivity when those values are declared. Supported explicit units are converted to SI for numeric comparisons. Missing units, ambiguous values and missing properties remain unassessed. Name tokens and character trigrams contribute to ranking, while engineering evidence contributes most of the score. Conflicts cap the ranking and remain visible as held reuse evidence. No result automatically establishes substitution approval.

Change impact follows up to four physical hops through explicit impact predicates, typed change-relationship carriers, upward assembly structure, traceability and manufacturing dependencies. Every result retains the business path, node and relationship identities, source direction, depth and configuration/effectivity questions. Cycles, node count, edge count and execution time are bounded. Plain master references are excluded from impact propagation. A recorded dependency is a review candidate; active effectivity and severity are not inferred.

Semantica native decision policies run on each recommendation candidate and retain the result digest, policy digest and assessment evidence. PMem engineering-evidence rule extensions add maximum conflicts, minimum evidence coverage, allowed evidence states, completeness and effectivity requirements. These extensions are explicitly identified separately from the native Semantica engine. Missing policy is distinct from a passed policy. Unavailable policy or evidence storage holds the assessment. A heuristic match score is never supplied as calibrated confidence.

## Correctness and user experience

Selected node identity and ontology scope are preserved in direct and agent investigations. Editing the name clears the pinned identity. Retained agent results are rejected when identity or scope differs. Graph Inspector no longer sends an invalid node_id inside GraphScope, and late responses cannot replace a newer selection. It also displays policy assessment and conflict summaries.

Similarity rows show the score, review disposition, assessed-property count and expandable source/candidate comparisons. Impact rows show business dependency paths and configuration/effectivity findings. Missing evidence is not labelled low impact. Graph readiness checks typed business records and explains that evidence coverage and agent model availability are separate checks.

## Execution boundaries and remaining customer validation

The engine uses selected graph identities, parameterized scope, bounded candidate retrieval and frontier reads, with a publication barrier across each multi-query analysis. Read failures return an actionable 503 and retain a server error trace. Customer query plans and latency must still be measured against actual customer data; isolated tests cannot prove production performance.

Business categories derive from declared types/roles and retained ontology mappings, not object-name keywords. Arbitrary domain classes must be mapped to supported business roles before analysis. Property comparisons use declared vocabulary local names; unsupported units and undeclared equivalences require engineering review. Tolerance intervals, geometry equivalence and active configuration rules are not silently guessed. Embedding/model availability is not required for direct graph analysis. Agent planning still needs the configured model.

The installer/updater release check now requires the shared engine, comparison module and compatibility adapter. No new database migration or automatic policy/approval is introduced. Deploy the complete release and rebuild the frontend using the existing update-depo.ps1 procedure. See ../recommendation-engineering-review.md for examples and acceptance checks.

## Verification scope

Automated scenarios cover differently named reuse candidates, wrong-category exclusion, unit equivalence, material/dimension/revision/configuration/tolerance conflicts, missing units, multiple values, scope isolation, candidate limits, carrier-based impact, multi-hop assembly/process/requirement paths, direction, cycles, publication barriers, compatibility-caller parity, per-candidate policy evidence and engineering policy holds. Frontend checks cover retained identity, stale results, comparison details, keyboard graph inspection and unestablished impact.

The cross-feature suite passed 171 backend tests. A subsequent focused run passed 66 checks, overlapping that suite and covering the final provenance, scope and timeout changes. Frontend verification passed 52 tests across graph interactions, recommendation evidence, policy messaging, scope validation and authenticated reads. Production build, installation package checks and isolated updater tests passed. Existing deprecation and large-bundle warnings remain.

The cross-feature run also exposed a timing-dependent completed-publication retry bug: receipt reconciliation changed updated_at on an identical completed result. Reconciliation now preserves the completed record after receipt validation. Its regression explicitly advances the clock so success cannot depend on timer granularity.

No customer deployment, customer data, live model generation or customer approval state was changed. Customer query plans and live acceptance remain separate deployment checks.
