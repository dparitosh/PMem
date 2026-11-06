# Ontology Junction functional and semantic audit — 2026-10-20

## Scope and evidence

Reviewed Taxonomy / OWL, Mapping Vocabulary, Semantic Bridge (ontology merge and instance linking), Inference Workbench, their frontend clients, retained merge matching/approval implementation, and Governor/Steward agent/tool policies. Reproduced a live vocabulary timeout hiding the complete Bridge workspace. Regression tests and release-overlay builds verify source/package behavior; the running customer installation still requires deployment and end-user acceptance testing. This audit is not an OWL-DL consistency or customer-release certification.

## Corrections

| Area | Finding | Correction |
| --- | --- | --- |
| Shared navigation | Vocabulary timeout hid independent agent workflows | Keep Bridge controls visible; show the failed vocabulary request separately; vocabulary has an explicit retry |
| Taxonomy / OWL | Same-prefix versions, non-class nodes and capped hierarchy could mislead selection/counts | Preserve ontology IDs, explicit active selection, class filtering, full class inventory and labelled 800-row hierarchy preview (existing corrections retained) |
| Vocabulary semantics | Vocabulary alignment could be mistaken for identity consolidation | Explain the distinction between SKOS alignment, OWL equivalence, identity and reviewed merge actions |
| Instance targets | Label values conflated same-labelled terms; lowercasing conflated case-sensitive IRIs | Use exact IRI/URI/term identities and preserve case; retain labels for display |
| Manual mapping | UI invented 75%/100% confidence from local approval | Missing scores stay unavailable; local mappings require validation; reset local review state when source/target inputs change |
| Import context | A different import's local mappings could remain visible or block duplicate detection | Filter by selected task and include task identity when adding/removing local rows |
| Merge proposals | Only exact labels were considered | Add bounded lexical/context scoring, typed class/property candidates, ranked alternatives, ambiguity flags and a retained matching report |
| Merge review | Scoring and domain evidence were hard to inspect | Show similarity components, domain/range/attached-property evidence, a minimum-score filter and incomplete-search notices |
| Agent review | Instance review and results were hidden in Advanced | Expose the review action and evidence; show missing-input guidance and live workflow status |
| Agent result contract | Partial/failed results could appear usable | Require matching agent/tool, a run ID and an object result; reject explicit non-completed status |
| Inference | Idle results appeared as zero; unverified response identity could be adopted | Distinguish not-run/unavailable from zero; reject malformed or wrong-ontology responses; require a selected rule; label rule and limit inputs accessibly |
| Tests | Old automatic-merge fixtures violated current SHACL requirements and omitted publication locks | Supply conforming annotations and the mock lock contract; retain actual validation and source-lock regression tests |
| Tests | Nested XSD ownership test incorrectly inspected the flattened all-table column collection | Verify columns against the owning table and verify the nested child's column remains retained |

## Domain and agent contracts

- Taxonomy and vocabulary browsing are reads, not agent approval. SKOS exactMatch is not automatically owl:sameAs or owl:equivalentClass.
- Instance linking uses Governor preview → Steward policy evaluation → Governor publication. The separate ontology agent review is advisory; model text cannot authorize a write. Held reasons and retained workflow recovery remain visible.
- Two-ontology merge scoring uses 50% normalized label/token/text similarity, 30% character trigrams, 10% comments/definitions and 10% role-aware domain/range or attached-property context. Terms must have identical declared kinds. Missing evidence contributes zero. A 55% threshold admits proposals, not approvals. Ambiguity is flagged. Scores are not calibrated probabilities and do not prove business equivalence.
- Matching considers up to 100 candidates per source, omits index buckets above 200 targets, caps comparisons at 100,000 and returns at most 200 proposals. The retained matching report identifies incomplete searches. Synonym/embedding/LLM semantic alignment is not implemented by this deterministic scorer.
- Consolidation requires explicit selection and a fresh saved preview. Conflicts block approval; source versions and artifact hashes are checked before apply. Automatic union policy continues to hold entity consolidation for human review.
- Inference is a structural preview. Domain/range entries are declarations; SWRL-style validation does not execute the expression. The UI does not offer inference publication or claim full consistency proof.

## Required deployment acceptance checks

After applying the reviewed release, verify both published and upgrade-review AP242/QIF versions in the UI. Generate a new merge preview, inspect score evidence and alternatives, change a selection and verify old approval is unavailable, and reconcile publication with the retained receipt. Test instance linking with a complete import and a known ontology version; inspect accepted and held mappings. Exercise inference with no rules, hierarchy/type rules, declarations, disjointness and a timeout. Verify keyboard navigation and layout at the customer's display sizes. No existing ontology, graph or approval is migrated by this audit.
