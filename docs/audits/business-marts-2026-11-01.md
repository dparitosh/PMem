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
