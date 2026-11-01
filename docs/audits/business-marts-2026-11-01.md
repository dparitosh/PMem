# Business reporting models, marts and published snapshots — 1 November 2026

## Implemented

- Immutable named, semantically versioned analytics definitions pinned to a prepared dataset. Metadata-authoring scope creates drafts; data-job approval scope approves the exact version. Different content under an existing name/version is rejected. Model identity is verified before execution.
- Separate approved native write workflows: `semantic-business-mart` and `graph-source-snapshot`. Existing read-only analysis approval does not authorize either operation.
- Migration 016 adds seven physical PostgreSQL tables plus four role views: model versions, mart receipts, entity dimensions, operational property values, relationship facts, normalized per-record measures and aggregate KPI facts. Columns, keys and indexes are checked by the updater. Vanilla reset uses dependency order; updates preserve records.
- Fixed deployment-owned KPI formulas with explicit per-record unit conversions. Missing/repeated numeric values or units reject the complete load. Reviewed expected BOM pairs permit bounded completeness; unknown expectations remain unknown. A scope statement describes rather than filters an immutable dataset; no revision/effectivity or master-data equivalence is inferred.
- Set-based materialization and COPY in one fenced PostgreSQL transaction. Model-identity advisory lock makes retries reconcile to one mart. Stable mart-scoped SQL tables and paginated read API support consumption; the product draft retains model/scope/table endpoints for existing publication.
- Active published RDF projection export under the publication barrier, bounded by resource/triple/byte limits. Staging and retained-identity nodes are excluded. Publication version is pinned; a changed publication is rejected. Worker retains deterministic RDF and registers a named metadata source without changing the graph or granting product approval.
- Data Products model selectors, vocabulary property pickers, unit conversion rows, expected BOM part selectors, separate review/approval and retained worker results. Data Flow displays table counts and a paginated table browser.

## Tests before local deployment

- Actual disposable PostgreSQL schema: model draft rejection, approved model execution, seven dimensions, three normalized measures totaling 3.5 kg, one matched of two expected BOM pairs (50%), seven recorded typed relationship facts, retry identity, wrong-dataset rejection, missing-unit rollback and lost-lease rollback.
- Graph source tests: publication-change rejection before registry writes, deterministic retry content, retained publication provenance and read-only analysis rejection of write operations.
- Frontend: separate model approval, pinned publication selection, rapid-click guard and existing session/reconnect tests.
- Schema/upgrade/reset regressions: 61 passed. No production database cleanup was performed.

## Acceptance boundary

This delivers dataset-pinned snapshot ODS/reporting marts and explicit model governance. It does not claim a cross-source SCD warehouse, inferred business semantics, unreviewed KPI accuracy, requirement satisfaction, certified manufacturing readiness or customer acceptance. Publication still uses the existing semantic release and data-product approval workflow. Large graph sources must be partitioned; there is no silent truncation.

## Live acceptance and defects caught during execution

- Browser-selected a local synthetic snapshot, mapped all four roles/relationships, saved `LOCAL TEST — portfolio reporting mart` 1.0.0, explicitly approved it, and submitted the separate approved native mart workflow. Run `9e4566fc-60f0-4a5b-b530-6fea55ea1491` completed: 7 dimension records, 17 ODS facts, 7 typed relationship facts and 11 KPI facts. The browser table selector displayed the actual dimension rows. No numeric measure was defined for this particular source, so its measure table has zero rows; numeric/unit acceptance is the separate real PostgreSQL 3.5-kg fixture.
- Browser submitted the published `ceim-ap242` graph snapshot. Run `a421a216-8b4f-420f-a2c1-bbff80b794b9` completed and the new named source appeared in Registered source. Live export contained 6,644 triples. No graph publication was modified and the source remained a draft.
- Live graph export initially exposed a driver API mismatch: explicit transactions require query strings, not `Query` wrappers. Corrected and regression-tested the actual exporter, including typed literal reconstruction. Repeated graph names are now distinguishable in source selectors.
- A real mart replay reused the same physical mart, but its result viewer rejected a deduplicated output owned originally by another run. Corrected result verification to use immutable, run-specific artifact-usage receipts; older retained manifests derive and verify their exact server-owned receipt. A regression proves replay succeeds while substituting another run's usage still returns 409. The content metadata is never overwritten to claim ownership.
- Standard updater applied migration 016, verified 18 relations / 102 columns / 29 constraints / 15 indexes and all ten browser-session scopes. Existing credentials, graph publications and prior marts were preserved. Final customer acceptance remains deferred.
