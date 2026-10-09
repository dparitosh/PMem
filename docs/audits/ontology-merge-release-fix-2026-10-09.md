# Ontology merge failure and publication review

Pre-commit verification of the accumulated working-tree fixes: all 279 frontend tests across 62 files passed; 55 affected backend tests plus 6 subtests passed; production build and whitespace checks passed. Tests ran locally with isolated/mocked dependencies, not against customer PostgreSQL, Neo4j or APIM. Live customer acceptance remains pending.

The supplied customer run failed at `ontology.merge.preview`. Its original cause cannot be recovered from the supplied trace because the old code stored only the exception class.

## Corrections

- Failed workflow steps now retain HTTP status, a stable error code and an actionable message. Known missing merge source errors are classified without retaining arbitrary upstream bodies, paths, credentials or source identifiers.
- The workflow UI displays the retained failure reason outside the raw JSON report. Older reports explicitly indicate that the reason was not retained.
- Legacy source resolution accepts an available converted semantic artifact when the original upload is absent. Missing both artifacts still fails. This is a confirmed resolver defect, but is not proven to be the cause of the customer's run.

## Publication behavior

Create ontology previously registered a source by default, leaving Neo4j unchanged unless the publication checkbox was selected. The UI now defaults that checkbox to enabled and explicitly explains both modes. Supported sources request policy/quality checks and Neo4j publication; users can still select registration only. The backend API remains opt-in for callers. Success requires a graph-publication receipt. Automatic ontology union creates a retained draft; graph publication remains separate. Existing registered sources are not retroactively published.

## Validation and customer acceptance

### RDF draft follow-up audit: release blocker remains

- **P1 (RDF product flow):** `frontend/src/services/analyticsProductDraft.js:2` accepts only schema-design-evidence and pipeline-evidence. The newly generated ontology-evidence draft is rejected before preview/publish. Reproduced against the actual module with a complete field fixture: `Select a retained product evidence draft.` Add the new kind to the supported contract and cover the real builder in the publisher tests. Earlier mocked publisher tests did not validate this integration, so their passing result did not prove RDF product publication worked.
- **P2 (lineage):** the new RDF draft has no selected ontology identity, `DataProductsPage.js:165` passes only the nested draft, and `publicationFromDraft` discards ontology references. Consequently the packaged manifest/catalog cannot identify the ontology selected by the user. Pass the selected registered identity into the draft and preserve it through the product payload and manifest. An independently entered approved semantic release is not a substitute for this source lineage.

Follow-up: both findings are fixed locally. The real builder accepts ontology-evidence. Data Products augments the selected draft with its registered ontology identity using a memoized draft, and the payload preserves both ontology and source lineage separately from the approved semantic release. Twenty frontend tests passed, including a new publisher integration test using the actual builder instead of mocking it. No live customer PostgreSQL, graph or catalog acceptance was performed.

Direct RDF follow-up: OWL/RDF/TTL normalization now retains an `ontology-evidence-data-product-v1` draft referencing the original and normalized artifacts. The engineering registration retains that draft in catalog metadata. The Create ontology UI uses this same route for register-only direct RDF with `publish=false`; schema SHACL/Both registration remains on its existing route. Data Products reuses the governed publisher and explains that this evidence package does not perform bridge mapping, merging or graph publication. Existing ontology records are not automatically backfilled. Four backend tests and twenty UI tests passed for this follow-up, including artifact resolution, registration metadata and register-only behavior. Live PostgreSQL/catalog acceptance remains pending.

14 focused backend tests passed covering diagnostics, retained semantic artifacts, merge automation and RDF publication. All 7 workflow UI tests passed, including visible error diagnostics and retained runs. All 5 import-page routing tests passed, including default publication and explicit registration-only behavior. No customer database or gateway was contacted.

Deploy the updated backend and frontend together. Connect workflow scopes, retry the failed preview as a new task, and inspect the newly retained status/reason. If a source artifact is missing, restore or re-register it. Verify Neo4j publication separately; a registered or merged draft is not a publication receipt. Live acceptance is required before declaring customer release readiness.
