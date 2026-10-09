# Catalog, data products and analytics warehouse review

## Current correction — 2026-10-09

The sections below retain the original review findings. Product publication now has a cross-process lock, request-digest/idempotency validation and immutable package verification; those statements under Further risks are historical, not unresolved defects. The approved `xml-analytics-materialize` path now creates versioned structural PostgreSQL tables, retains XML bytes, validates XSD/XML and supports explicit business views. See [the current XML analytics audit](xsd-relational-analytics-audit-2026-10-02.md). It does not complete a dimensional business warehouse. Live database, concurrency, revocation and customer acceptance tests remain required.

## What exists

- Data Catalog (8016): versioned product metadata in PostgreSQL `depo_registry`, namespace `catalog_products`; lifecycle state, ownership, classification, steward, semantic releases, manifests and latest-version pointer. Registration takes a per-product PostgreSQL advisory lock and writes the version and pointer together.
- Data Products (8017): immutable artifact packages, download manifests, approved semantic release references, catalog registration with durable retries, approval records and revocation. Records use `data_products` and `data_product_approvals` registry namespaces.
- PostgreSQL schema: configurable `DEPO_DATABASE_SCHEMA`, default `semantic`. The existing migrations provide control-plane/governance tables and the `depo_ontology_analytics` view. The view exposes ontology counts; it is not a dimensional warehouse.
- Pipeline schema-analytics job: produces an immutable analytics-profile artifact and governed product draft. Its metric series describes schema statistics and currently invokes Spark for aggregation. This path does not insert engineering facts or dimension members into warehouse tables.

## Corrected defects

1. Product publication persisted the request's approval token and returned it through product reads. New persistence excludes credential fields; read responses also redact those fields from old records. Existing stored credentials require an approved data cleanup/rotation, not merely a code deployment.
2. Product package paths used unchecked product/version input. Package creation now rejects unsafe identifiers, requires a semantic-version-shaped value and checks storage containment before writes.
3. Successful catalog registration changed a revoked product back to `published`. Success now retains `revoked` when its lifecycle state is revoked.
4. Non-object artifact entries triggered unhandled attribute errors. They now produce validation errors.

## Warehouse gaps

No dedicated analytics warehouse schema, fact tables or dimension tables were found in the versioned SQL migrations. No end-to-end warehouse loading jobs were found. Schema analytics artifacts are not populated business analytics.

A complete implementation needs explicit fact grain and metric definitions; product/part revision, requirement, characteristic, measurement, source-system, ontology-version and time dimensions; tenant/project boundaries; source and unit references; surrogate/natural keys; revision/history rules; idempotent incremental loading; reconciliation and quality evidence; and UI/report queries that consume the resulting facts. AP242/AP239/QIF mappings must be selected from validated source records rather than inferred from a filename alone. These are architecture/implementation gaps, not tables to create with guessed columns during a bug audit.

## Further risks

Product publication still needs a cross-process lock spanning packaging and durable product creation. Catalog/product namespaces currently use document storage instead of normalized warehouse relations. A reused idempotency key is not checked against a request-content digest. Reconciliation reads the namespace wholesale, and revocation retry races need integration tests. Catalog read authorization should be reviewed against customer metadata classification. Package reuse should verify the existing manifest matches the requested immutable content. The schema analytics job's Spark-only aggregation is a functional limitation when Spark is disabled.

## Validation

Package boundary tests pass, including unsafe paths and a valid manifest/archive. Python syntax validation passes. Full API tests and live PostgreSQL/catalog/warehouse queries have not been run because deployment dependencies are absent locally. No warehouse completeness or customer-release certification is claimed.
