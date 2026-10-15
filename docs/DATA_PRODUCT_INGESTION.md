# Ingestion and data-product lifecycle

Reviewed against the current checkout on 2026-10-15. This is the navigation and
implementation-status reference for heterogeneous ingestion, semantic publication
and PostgreSQL analytics. It does not certify a customer deployment.

## User journey

1. **Import:** select a supported source profile and retain its original artifact.
2. **Data Flow:** select an approved job definition, supply inputs matching its
   contract, and follow the retained run ID, validation results and rejected records.
3. **Ontology Junction / Semantic Bridge:** select the applicable ontology and
   inspect mappings or linking/merge recommendations when semantic alignment is needed.
4. **Publish semantic output:** publish an eligible accepted semantic run through
   the CEIM boundary. Graph publication and product publication are separate actions.
5. **Data Products:** select retained evidence, complete product identity, version,
   owner, steward, classification and approved semantic-release references; preview
   and publish the package.
6. **Data Catalog:** verify the governed product version and catalog-registration
   status. A catalog retry reconciles registration; it must not rerun ingestion.

A completed processing job is not automatically a published product. A registered
ontology is not proof of an RDF publication or a PostgreSQL instance load.

## Processing paths and current coverage

| Path | Existing implementation | Boundary / remaining work |
| --- | --- | --- |
| Engineering structured sources | Supported engineering parsers and CEIM mapping packs; `normalize-ceim` and `validate-semantic-batch` jobs | Select a supported source profile and mapping; an arbitrary XML or JSON shape has no automatic business meaning. |
| CSV / XLSX | Tabular ingestion parses CSV and the active XLSX worksheet | Not connected to the XSD/XML PostgreSQL materializer. An approved tabular-to-ODS mapping/loading contract remains needed. Legacy XLS is rejected. |
| Unstructured evidence | `validate-unstructured-evidence`, `enrich-document-evidence`, `normalize-unstructured-ceim`; fixed document-evidence workflow | Retained evidence and proposals enter semantic validation. This does not mean arbitrary documents, OCR inputs or formats are supported by every extractor. |
| XSD / XML ODS | `xml-analytics-materialize` validates a retained XSD closure and XML, then commits structural PostgreSQL records and a load receipt | Supported XSD projection only; unsupported constructs fail validation. This is not a universal JSON/CSV/XLSX loader. |
| Data mart | Explicit fact and immutable natural-key dimension views over the XML ODS | Requires business keys, grain and measures. Cross-entity joins, conformed surrogate dimensions and SCD policies are not implemented here. |
| RDF processing | `rdf-quality-statistics`, `rdf-deduplicate-serialize`; governed graph publication | RDF processing evidence and graph publication receipts are distinct from loading relational facts. |
| Database/API/event acquisition | Configured service adapters and a governed speed-path boundary | Generic database CDC, arbitrary REST acquisition and production streaming readiness must not be inferred from the job catalog. Each source needs a tested adapter and checkpoint policy. |

The executable job list is owned by
[`handlers.py`](../backend/data_pipeline_service/handlers.py). Not every proposed
job name in an older architecture document is an executable handler.

## Storage responsibilities

| Store | Responsibility |
| --- | --- |
| Artifact storage | Original source bytes, extracted evidence, serialized RDF, reports and immutable outputs. |
| PostgreSQL application schema (`semantic` by default) | Definitions, run manifests, approvals, catalog/product records and operational state. Registry namespaces are not separate SQL schemas. |
| PostgreSQL `depo_analytics_<digest>` or configured project prefix | One versioned schema per XSD closure and prefix: entity/link tables, `source_documents`, and configured business views. |
| Neo4j | Governed semantic graph resources, relationships and publication evidence. No SQL schema is created for RDF. |
| Product package storage | Immutable artifact package and manifest; product publication does not automatically export all ODS rows or the Neo4j database. |

Two PostgreSQL schemas is the default example for one materialized XSD model,
not a fixed deployment-wide count. More distinct XSD closures/prefixes create
additional analytics schemas. Tables can share names across different schemas.

## Product evidence and publication

| Evidence source | Product classification | What it demonstrates |
| --- | --- | --- |
| Schema conversion | `schema-design-evidence` | Retained schema, conversion and analytics profile; not populated business facts. |
| Registered ontology | `ontology-evidence` | Retained ontology evidence and lineage; verify graph publication separately. |
| Completed processing / XML load run | `pipeline-evidence` | Retained outputs, quality and source/run lineage; XML receipt identifies the committed ODS projection. |

The UI draft helpers preserve these distinctions. Existing product kinds must
not be relabeled as a complete analytical warehouse or live dataset subscription.

The existing service operations are:

- `POST /api/v1/data-products/preview` — inspect the proposed package.
- `POST /api/v1/data-products/publish` — approved, versioned package publication.
- `GET /api/v1/data-products/{product_version}/manifest` and `/download` — inspect
  retained package content.
- `POST /api/v1/data-products/{product_version}/retry-catalog` — reconcile catalog registration.
- `POST /api/v1/data-products/{product_version}/revoke` — governed revocation.

Publication requires an authenticated approval identity, applicable credentials,
retained artifacts and an approved semantic release. Agents can recommend actions;
they do not grant themselves publication authority.

## Failure and recovery

- Preserve the run ID and source identities after timeout or response loss. Inspect
  the retained outcome before retrying writes.
- XML ODS commit with `evidence_status=pending` means data was committed but
  packaging evidence is unavailable. Rebuild it through
  `POST /api/v1/pipeline/jobs/runs/{run_id}/reconcile-analytics`; do not reload XML.
- Product packaging remains blocked while evidence is pending.
- Graph publication, ODS commit, product publication and catalog registration each
  have their own retained outcome. Success at one boundary does not prove the others.
- Raw bytes, approvals and logs have different retention rules; cache cleanup is
  not permission to delete source evidence.

## Implementation sequence for remaining ingestion coverage

1. Reuse the existing artifact store, job registry, execution worker, approval,
   quality and product services; avoid a parallel ingestion framework.
2. Define a versioned tabular/JSON staging contract with source identities,
   explicit types, keys, null handling, rejects and schema revision.
3. Add adapter-specific jobs and a PostgreSQL loader using that contract, bounded
   batches, atomic commits and recoverable receipts. Preserve the XML contract.
4. Return retained evidence drafts through the existing product lifecycle.
5. Add source-specific database/API acquisition only with checkpoint, pagination,
   idempotency and failure-recovery acceptance tests.
6. Test source → retained run → optional ODS/graph output → product → catalog,
   including duplicate inputs, response loss, expired sessions and downstream outages.

Steps above describe remaining implementation, not features delivered by this document.

## Related references

- [Current sequence](CURRENT_ARCHITECTURE_SEQUENCE.md)
- [Pipeline design and historical roadmap](SEMANTIC_INTEGRATION_LAMBDA_PIPELINE.md)
- [Installation and XML analytics operation](../INSTALLATION.md)
- [PostgreSQL control-plane relations](../infra/postgres/SCHEMA.md)
- [Test evidence and release limitations](TESTING_AND_EVIDENCE.md)
