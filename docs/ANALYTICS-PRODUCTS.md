# Analytics products and consumption

Data Catalog and Data Products include **Available analytics**. It distinguishes imported schema designs, committed analytics datasets and governed published packages. A zero published-product count does not imply that no analytics dataset exists.

## End-user sequence

1. Choose an imported schema by name. The application resolves its retained XSD reference.
2. Choose or retain XML data. Completed Data Flow run links populate retained schema and instance references automatically.
3. Load an approved XML analytics job. Define dimensions with explicit business keys, or aggregate facts/KPIs using selected entity properties. KPIs require a business purpose and unit. Review technical settings under Advanced when needed.
4. Submit validation and loading to the existing pipeline worker. Follow the retained run; do not repeat an unconfirmed submission. A failed evidence build can be reconciled without loading the data again.
5. Inspect Available analytics to see the receipt-backed operational tables and business views. Preview is read-only and bounded; load counts describe the latest load, not dataset totals.
6. Select Review for publication to reuse the completed run's retained evidence. Supply ownership/classification and select an approved semantic release through the existing publication form. Approval and catalog delivery remain separate from materialization.
7. Published product provenance includes the qualified analytics schema and defined views. Database access provisioning is separate.

## Supported scope

The ODS stores validated entity instances. Dimensions provide immutable business-key views; aggregate facts and KPI views support count, sum, average, minimum and maximum. These are explicit definitions, not inferred industry metrics. Cross-entity joins, ratios, target thresholds, slowly changing dimensions and external BI provisioning are not implemented by this change. A retained schema plan is not a materialized data mart.

## Existing deployments

Run the normal repository-root `update-depo.ps1` with the selected `.env.local`. The migration runner applies `infra/postgres/migrations/014_analytics_discovery.sql` once to add the partial discovery index. Do not reset PostgreSQL or remove credentials. Existing completed XML-analytics run receipts become discoverable without reloading their data. Only receipt-backed, registered schemas are exposed; arbitrary database tables are excluded.

The new GET endpoints are `/api/v1/pipeline/analytics`, `/{run_id}` and `/{run_id}/data?relation=...`. They require existing graph-read authorization. Previews allow only retained model relations, quote SQL identifiers, use read-only transactions, enforce a five-second statement timeout and bound rows, columns and cell sizes. They never accept SQL or expose source XML bytes. Missing ownership or physical relations must be reconciled before consumption.
