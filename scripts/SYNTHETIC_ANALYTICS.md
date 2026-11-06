# Schema-driven synthetic analytics tests

`synthetic_analytics.py` is a standalone PostgreSQL test harness. `Test-SyntheticAnalytics.ps1` is its Windows launcher. It uses psycopg and optionally python-dotenv, already supplied by the app runtime. No LLM, running API or source-table data is required.

It reads base-table columns, types and foreign keys from PostgreSQL metadata. Execute mode creates a **new `nexus_test_*` schema**, generates reproducible rows, remaps foreign keys, profiles columns and creates queryable KPI views. A JSON report and `synthetic_test_receipt` table label the results as synthetic. It does not publish a customer data product or register invented engineering facts in the application.

## Inspect first

From the repository root or use an absolute script path:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\Test-SyntheticAnalytics.ps1 -SourceSchema semantic -Output .\outputs\schema-inventory.json
```

Review that inventory and choose an existing analytics/source schema. The `semantic` application schema contains operational records and generic JSON registries, not necessarily business tables. Random JSON cannot satisfy their business contracts.

## Generate rows, analytics and default KPIs

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\Test-SyntheticAnalytics.ps1 -SourceSchema YOUR_ANALYTICS_SCHEMA -TargetSchema nexus_test_demo_01 -Rows 100 -Seed 42 -Execute -Output .\outputs\synthetic-demo.json
```

The destination must not already exist. Source tables remain unchanged. Check/not-null/unique constraints are copied, but defaults and source sequences are excluded. Foreign keys reference generated test tables only. All database writes commit together or roll back on failure. Nothing is dropped or overwritten.

Without a KPI file, each table gets an observed synthetic row-count KPI view. Numeric-column profiles include minimum, maximum, average and sum. These statistics do not imply valid engineering aggregation or business meaning.

## Explicit business dimensions and measures

Copy and edit `synthetic-kpis.example.json` to match table/column names in the inventory. Supported aggregates: `count`, `sum`, `avg`, `min`, `max`. Every KPI requires its name and unit. `count(column)` counts non-null values. Dimensions are existing columns, never inferred engineering classifications.

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\Test-SyntheticAnalytics.ps1 -SourceSchema YOUR_ANALYTICS_SCHEMA -TargetSchema nexus_test_demo_02 -Rows 100 -Kpis .\scripts\my-kpis.json -Execute -Output .\outputs\synthetic-kpis.json
```

Inspect the physical tables and `synthetic_kpi_1`, etc., in the new schema using pgAdmin or a reporting tool. The receipt records formulas, units, dimensions, seed and observed results. Cross-table business formulas, BOM effectivity, requirement satisfaction and approval semantics need reviewed domain fixtures; they are not invented from SQL names.

## Connection and limits

Connection precedence: `DEPO_TEST_DATABASE_URL`, then `DEPO_DATABASE_URL`, then `DATABASE_URL`. Existing process settings override the optional env file. Keep credentials in the environment, not arguments or reports. Prefer an isolated test database/user; a new schema provides namespace separation, not resource isolation.

Bounds: 100 tables, 10,000 rows/table, 20 explicit KPIs, statement timeout 30 seconds and lock timeout 5 seconds. Parent tables generate before children, including composite foreign keys. Cyclic/self/external-schema relationships, inaccessible parents, custom/domain/array types and unsupported constraints fail without partial committed tables. Complex CHECK constraints can reject generated values; supply a reviewed fixture rather than relaxing production constraints. This is not a universal generator for arbitrary schemas.

No cleanup runs automatically. Keep the test schema for inspection and remove it only through your normal disposable-test-data maintenance process. No install migration or new database permission is introduced by these scripts.

Execute mode requires CREATE on the selected database and SELECT on the source metadata/tables, with permission to use their types. The application runtime role intentionally may not have database CREATE. Use a separately provisioned disposable test database/role through `DEPO_TEST_DATABASE_URL`; do not expand production runtime privileges for this script.

Validation on 2026-11-04: unit tests passed. Metadata inspection against the local `semantic` schema is supported. The PostgreSQL fixture test could not create its first test schema because the local application role lacks database CREATE; it stopped without writing source data. Full materialization acceptance therefore still requires the isolated test connection described above.
