# Analytics products review — 2026-10-31

## Verdict

The analytics changes are **not ready for customer release**. Four confirmed defects remain. No production code was modified during this audit; executable reproductions and this report were added. Changes under review are uncommitted and not deployed to the running application.

## Scope and execution

Reviewed inventory/preview API, generated SQL and registry ownership, migration 014, XML materialization, source selection, session invalidation, KPI construction, product-draft lineage and existing publication consumers. Executed real FastAPI routes with isolated authorization/registry doubles, backend materialization and lineage tests, and React component timing/failure simulations. No LLM, customer deployment, destructive maintenance or live publication was used.

- Backend: **30 passed, 2 strict expected failures, 12 subtests passed**. Command: `python -m pytest backend/tests/test_analytics_audit.py backend/tests/test_analytics_catalog.py backend/tests/test_xml_analytics_materialization.py backend/tests/test_lineage_projection_fixes.py --basetemp=outputs/analytics-audit-api-temp -q -rx`.
- Frontend: Vitest reported **36 passed**, but this includes **2 `test.fails` reproductions**. Therefore the meaningful split is **34 ordinary passing tests and 2 confirmed expected failures**, not 36 acceptance passes. Files: AnalyticsAudit, AvailableAnalytics, AnalyticsViewBuilder, XmlAnalyticsLoader and DataProductsPage tests.
- The previous production build passed; this audit changed only tests and documentation. Existing React test-utils deprecation and bundle-size warnings remain.

## Confirmed defect register

| ID / severity | Location | Root cause | Reproduction and impact | Recommended correction |
|---|---|---|---|---|
| AUD-01 / High | `frontend/src/Components/XmlAnalyticsLoader.js:21`, `:68`, `:72` | Parent schema changes update only the displayed source ID. They neither invalidate the request generation nor clear the bound schema artifact/dependencies. Generation changes currently cover credentials, not source identity. | Start schema A resolution, change selectedSchemaId to B before A returns, then resolve A. The selector shows B while the retained artifact is A. A later submission can use the wrong schema; server XML validation may reject it, but compatible XML does not make the provenance correct. Reproduced by strict expected-failure React test. | Bind requests to both generation and source identity; increment on source changes, abort pending resolution and clear artifact, business definitions and dependencies together. Preserve uncertain write recovery separately. |
| AUD-02 / Medium | `frontend/src/Components/AvailableAnalytics.js:44`, `:47` | Empty-page rows are treated as an empty database without checking total or offset. | Open page 2 while 21 datasets exist; refresh response after removals has total 1 and zero rows at offset 20. UI says no materialized datasets exist even though one does. Reproduced by React test. | Reset/clamp offset when total shrinks; show an out-of-range-page message and return to the first page. Show global empty only when total is zero. |
| AUD-03 / Medium | `backend/data_pipeline_service/analytics_catalog.py:15`, `:31` | Inventory accepts completed legacy receipts without validating required summary fields. Count excludes a NULL schema but DISTINCT selection still includes it; summary then indexes receipt['schema']. | Supply a completed legacy run without a schema. Inventory raises KeyError and becomes a server error rather than returning healthy records. Reproduced against inventory with a database cursor double. | Validate receipt shape/schema/run identity before enumeration and summary; exclude invalid records consistently from both count and page, with a bounded diagnostic instead of hiding corruption. |
| AUD-04 / Medium | `backend/data_pipeline_service/analytics_catalog.py:55` | Relation discovery includes entity tables and business views but not the generated relationship/link tables. | Compile a model containing a child relationship. The materializer creates a link table using the same deterministic sql_name as the schema planner, but discovery never lists it. Consumers cannot inspect complete ODS relationships through this workflow. Reproduced with the shared name generator. | Include server-generated relationship table definitions and grain/key metadata in the same ownership allowlist; expose bounded previews without permitting arbitrary tables. |

## Verified boundaries

- Unauthenticated/unauthorized inventory requests return 403 before registry access. Authorized requests enforce query limits; invalid page sizes/offsets return 422.
- Database unavailability returns 503, not a successful empty collection.
- Unknown preview relations are rejected before opening the data connection. SQL identifiers are quoted; no client SQL execution exists.
- Preview uses a read-only transaction, bounded columns/rows/cells and statement timeout; the source XML document table is excluded.
- Existing ownership/schema-digest checks reject missing or mismatched retained schema records.
- Credential/session replacement prevents late dataset-detail rendering in the tested component path.
- KPI definitions require explicit purpose/unit and supported aggregates; they do not invent business rules.
- Successful loading is not represented as publication approval. Typed artifact/run references feed the existing publication lineage path.

## Risks and acceptance not yet established

1. **Real PostgreSQL acceptance:** new discovery SQL, migration/index usage and previews have not been exercised against an isolated real database in this audit. Mocks do not prove query planning, lock behaviour or transaction isolation. Run materialization + discovery + preview + rollback and EXPLAIN on representative large registry volumes before release.
2. **Data authorization policy:** all new reads use existing global graph-read authorization. There is no dataset-specific classification/owner filter here. If deployment policy requires finer access than Graph.Reader, this is a security design gap requiring an explicit policy; no unauthorized live access was attempted.
3. **Preview contract:** only the first 30 readable columns are returned without a separate column-truncation indicator. Add that indicator and verify schema/run identity in frontend responses as well as relation name.
4. **Publication acceptance:** no live CR/CO approval, semantic-release publication or catalog outbox delivery was executed. Unit-level lineage checks do not certify an end-to-end governed release.
5. **UI acceptance:** source workspace React tests execute the new UI, but the currently running installation contains the older release. Browser screenshots of it would not validate these new changes. Responsive layout, keyboard navigation, dark theme and two-tab recovery remain deployment acceptance work.
6. **Functional scope:** this implements ODS/entity tables and single-entity aggregate views with explicit immutable dimensions/KPIs. Cross-entity marts, ratios, SCD history, target rules and BI access provisioning remain outside the implementation. Do not market this as a complete analytics warehouse.

## Required release gate

Fix AUD-01 first, then AUD-02–04; convert all four strict expected failures into ordinary passing regressions. Run isolated PostgreSQL migration/materialization/discovery acceptance, build and deploy with backups, and perform browser-session plus governed publication acceptance. Keep imported schemas, loaded datasets and published products distinct throughout.


## Remediation and local database verification

The four confirmed defects above have now been corrected in source:

- AUD-01: schema handoffs invalidate request generation, abort schema resolution, and clear schema/dependency/business bindings; write recovery remains retained separately.
- AUD-02: shrinking totals reset an out-of-range offset to the first page; global empty state requires total zero.
- AUD-03: count and page queries share receipt/schema/run-identity eligibility filters. Defensive summary filtering logs excluded malformed receipts. The real database test includes a malformed legacy record.
- AUD-04: discovery derives relationship-table names using the existing schema planner's shared name function, and exposes parent/child grain and keys through the same preview allowlist.

All four reproductions have been converted to ordinary passing regressions. **36 frontend tests pass**, including both prior expected failures. The backend focused suite passes **20 tests and 12 subtests** (including both prior expected failures).

**Real PostgreSQL acceptance now executed:** `depo_acceptance_test` was explicitly selected and verified by database name. Two integration tests passed: existing materialization retry/rollback verification, plus migration 014 creation, committed materialization, healthy inventory despite a malformed historical receipt, physical relationship discovery, bounded read-only relationship preview and removal of all disposable schemas. This used unique test schemas and did not target the deployed application's database. This proves functional SQL execution on the local PostgreSQL installation; it is not a large-volume performance benchmark or customer upgrade acceptance.

The prior release verdict is superseded for AUD-01–04 only. Deployment/browser acceptance, live governed publication, classification policy requirements and broader analytics functionality remain as described above. Changes remain undeployed and uncommitted at this point.
