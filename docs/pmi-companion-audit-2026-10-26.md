# PMI and Companion follow-up audit — 2026-10-26

Scope: uncommitted PMI source-association rules, typed business retrieval, Companion provider failures, mapping upgrade compatibility and package completeness. This is not a full application or customer release certification.

## Findings corrected

| Priority | Finding | Correction |
| --- | --- | --- |
| P1 | Searching arbitrary references could use a reference from the wrong STEP attribute. | Conservative parser reads declared size/location, shape-aspect and product-shape attribute positions. Unsupported and compound layouts are held. |
| P1 | A two-feature dimension could resolve one owner and ignore its unresolved second feature. | All feature endpoints must resolve to the same product definition. |
| P1 | Undirected business reads accepted reversed semantic relationships or contradictory storage labels. | Enforce has-characteristic/has-PMI and annotates direction; explicit RDF predicate takes precedence. |
| P2 | Source-reference candidates could fill the result limit before recorded semantic associations. | Rank recorded associations first; retain bounded, stable identity ordering. |
| P2 | Trace-only results opened with an association claim. | State explicitly that only source-reference candidates were returned and ownership is unverified. |
| P2 | Valid JSON with an unexpected non-object shape could crash business-name rendering. | Reject non-object property payloads for name extraction and retain the fallback label. |
| P2 | Partial deployment could omit the new ownership helper. | Require backend/ceim/ap242_pmi.py in backend and installation package checks. |

The preceding changes also retain evidence on model failure, separate 401/403/429 recovery guidance, exclude generic quality characteristics from expanded PMI matching and version the mapping pack as ap242-core@0.4.0. The pack digest/version must be regenerated from source; old provenance must not be edited to bypass review.

## Evidence

- Strict original-record audit: 28 of the earlier 30 rotor-shaft candidates accepted. Two five-attribute TOTAL_RUNOUT_TOLERANCE records are unsupported and held, not asserted.
- Source: 000684_B_1-Rotor Shaft Machined_1 (1).stp. The source file was not modified.
- Revised production Cypher: Neo4j EXPLAIN passed with zero notifications; no graph writes were performed.
- Tests cover source/RDF provenance, wrong attribute position, unresolved second feature, same-owner two-feature dimensions, ambiguous owners, compound layouts, quoted/aggregate arguments, old mapping rejection, trace-only presentation and secret-free provider fallback.

Final verification: 87 offline regression tests passed in the combined suite. The installation package gate passed (82 PowerShell scripts, 10 services, 3 workers, 14 migrations); git diff --check passed. The gateway example had pushed INSTALLATION.md past its existing concise-guide bound; redundant spacing was removed without dropping instructions and the guide checks passed.

## Remaining acceptance limits

- No available LLM: live authentication and generated-answer acceptance remain pending. Offline transport tests do not establish provider availability.
- The complete rotor-shaft normalized batch contains 642,729 entities and exceeds the current 50,000-record publication batch limit. This change does not implement partitioned publication.
- Existing Neo4j publications are unchanged. New associations require regeneration, governed review/publication and post-publication verification.
- Five-attribute tolerance and compound/Part-28 ownership layouts require additional supported rules and tests; they are not inferred through generic graph paths.
- No restart, deployment or commit is implied by this audit.
