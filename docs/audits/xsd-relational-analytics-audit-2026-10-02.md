# XSD serialization → relational analytics audit — 2026-10-02

> Dated audit record: use [the current audit index](README.md) for latest validation and acceptance status. Findings and test counts below belong to their recorded review; they are not a current release certificate.

## Implementation update — 2026-10-09

Follow-up regression fixes: schemas without a target namespace now match XML
roots correctly. Present empty scalar elements use their XSD default; absent
and explicitly nil elements remain null. Complex nillable roots, including the
XSD boolean spelling `1`, are blocked before database writes until explicit
nil-state storage is implemented. Editing XML load dependencies, business views,
job selection or uploaded artifact invalidates the old UI receipt. Live
PostgreSQL verification and the specialized mappings listed below remain open.

An opt-in database regression test is available at
`backend/tests/test_xml_analytics_postgres.py`. Configure `DEPO_TEST_DATABASE_URL`
through your test environment to an isolated PostgreSQL database whose test role
can create schemas, then run:

```powershell
python -m pytest backend/tests/test_xml_analytics_postgres.py -q
```

The test uses unique schema names inside an outer transaction and rolls back
all fixtures. It checks persisted XML bytes, row counts, retry idempotency and
rollback after loss of execution authorization. It never falls back to the
application database URL. A skipped result means database verification has not
been performed; it is not a passing live database check.

The historical findings below describe the earlier implementation. A supported
XML materialization path is now registered as `xml-analytics-materialize` in the
existing approved Data Flow job registry, with quality profile
`schema-analytics-v1`. Conversion remains a design operation; publication never
executes DDL implicitly.

The Data Products page includes **Load validated XML into PostgreSQL analytics**.
Retain an XML instance through that panel, select an approved job, supply the
retained root XSD artifact and dependency references, then submit the load.
Root XSD and dependencies must already be retained by schema inspection.

Example job definition for `POST /api/v1/pipeline/jobs/definitions`:

```json
{
  "job_id": "xml-analytics-load",
  "name": "Validated XML analytics load",
  "version": "1.0.0",
  "owner": "data-engineering",
  "job_type": "xml-analytics-materialize",
  "quality_profile": "schema-analytics-v1"
}
```

Approve that definition through the existing job approval operation. Execution
uses `DATA_JOB_EXECUTION_TOKEN`; retaining XML uses `INGESTION_WRITE_TOKEN`.
The load payload accepts `schema_artifact_id`, `xml_artifact_id`,
`schema_dependencies` (relative path → retained artifact ID), `schema_prefix`
(default `depo_analytics`) and optional `business_views`.

The worker requires lxml and PostgreSQL. Its database role must have CREATE on
the database to create the dedicated versioned analytics schema, plus access to
the configured control-plane registry. Grant this capability to the approved
analytics worker role deliberately; ordinary API startup does not create or
alter schemas. Schema names contain the validated prefix and XSD closure digest.
Existing untracked schemas fail closed; different schema versions create new
projections without altering or dropping an existing projection.

One transaction creates the supported entity/link tables, validates and loads
the instance, retains the original bytes in BYTEA and a queryable XML document,
and commits a load receipt. Every entity row references its source document.
Repeated inputs reconcile the receipt without inserting rows again. A failed
write or lost worker lease rolls back the transaction. Raw XML/XSD input is
bounded to 25 MiB each, schema dependencies to 63 files and loaded entities to
100,000. XML is validated before any database writes; DTD/entity declarations
and remote schema dependencies are forbidden.

Business views require explicit entity grain and measures, for example:

```json
[
  {
    "name": "Entity count",
    "entity_id": "{urn:example}Record",
    "grain": "entity-instance",
    "group_by": [],
    "measures": [{"name": "count", "aggregate": "count"}]
  }
]
```

Use entity IDs and property names from the retained structural model. Supported
aggregates are count/sum/avg/min/max with datatype checks. A changed business
definition requires a different schema prefix. Without definitions, readiness
is **structural data loaded**, not a certified business warehouse. Cross-entity
joins, units, historical dimensions and KPI policies are not inferred.

XML source profiles now default to one document. Batch profiles must use an
explicit `records_path` or `mapping.record_mode = "children"`. Set
`mapping.namespace_mode = "qualified"` and use Clark names such as
`{urn:example}name` when namespaces share local names. Qualified source trees
remain in `source_documents`; exact byte recovery uses the retained XML bytes.

PostgreSQL backup now covers loaded XML bytes, entity/link data and receipts.
Evidence packages and original XSD artifacts still need an artifact-store
backup. Unsupported XSD choices/groups, identity XPath, facets, temporal rules,
mixed content and nillable complex entities remain explicit load blockers.
These restrictions prevent silent semantic loss; specialized mappings remain
separate work.

## Conclusion

Entities/properties/cardinality/datatypes can form a structural input contract for relational generation, but the current report is not complete enough to generate production DDL or analytical facts/dimensions automatically. It is explicitly a read-only mapping report. The schema-conversion analytics artifact currently retains ontology statistics and validation metadata, not a complete relational model or dimensional warehouse contract.

## Confirmed defects and gaps

1. **P1 — False successful parsing/closure.** `backend/Services/xsd_relational_report.py:45-65,190` silently skips missing or malformed schemas/includes and returns success even for malformed root XSD. No schema grammar compilation occurs in this report. Fail closed on invalid roots/missing closure; return explicit unsupported constructs and validation status. Restrict include resolution to the approved schema-set root; current schemaLocation traversal has no containment boundary.
2. **P1 — Root anonymous entities omitted.** `:83-88,180` maps only named top-level complex types. An element containing an anonymous complexType is omitted entirely. Traverse global elements, retain their expanded names and resolve anonymous type owners.
3. **P1 — Choice and compositor cardinality lost.** `:23-33,133` reads occurrence only on each element. Choice siblings default to required=true together, while a child of optional/repeating sequence is reported 1..1. Retain the particle tree, effective occurrence ranges and choice-group constraints; do not blindly map every required flag to NOT NULL. The OWL engine at owl_xsd_engine.py:801-806 also reads direct element occurrence, so Turtle alone is not a lossless source for these compositor semantics.
4. **P1 — Namespace/type reference collisions.** `:20,88,137` strips QName prefixes and indexes named types by local name. Imported namespaces with identical type names can collapse into the wrong entity. Element/attribute refs are not fully resolved to their declarations. Use expanded namespace-qualified identifiers and resolve refs across the validated schema closure.
5. **P2 — Repeated simple values have no child-table plan.** `:141-143` emits a scalar column even for maxOccurs>1, unlike repeated complex children. Represent repeated primitives as owner-key/value/position rows; preserve repeated compositor instance grouping as well as element position.
6. **P2 — Datatype/facet and inheritance contracts incomplete.** Simple types are counted, not resolved. No SQL type, decimal precision/scale, enumeration/range/pattern/length constraint, list/union policy or complex/simple-content inheritance mapping is emitted. Keep source lexical types and facets, map safely to PostgreSQL, and explicitly reject unsupported mappings. Prohibited attributes are reported max_occurs=1 instead of 0.
7. **P2 — Keys and FK candidates are not implementable constraints.** Names such as partnumber imply PK candidates without proving uniqueness. Key/keyref records omit selector/owner scope; keyrefs are copied onto every table. Some FKs exist only as candidate names without corresponding typed columns, and junction FK/sequence columns have no complete constraint definition. Resolve selectors/fields to owner paths; generate surrogate instance keys when needed and scoped UNIQUE/FK/ordering rules.
8. **P2 — Persistence and analytics generation are not implemented by this path.** The endpoint /reports/xsd-relational returns a report only. schema_conversion.py's schema-analytics-profile-v1 contains generated statistics and artifacts, not executable table DDL, XML row materialization, upgrade plans or fact/dimension grain. Add an immutable structural model artifact, reviewed DDL plan, versioned schema migration, XSD-validated instance loader with atomic writes, reconciliation/data-quality evidence and business metric/dimension mappings. Source structure cannot determine KPI aggregation, units, grain or slowly changing dimensions by itself.

## Direct reproductions

A synthetic schema showed: anonymous Root table absent; both choice alternatives required; a child inside minOccurs=0/maxOccurs=unbounded sequence incorrectly 1..1; prohibited attribute max_occurs=1; restricted Money type without SQL precision/facets. Replacing the root with malformed XML still yielded status=success. These reproduce structural reporting bugs; no live customer tables were generated or modified.

## Required functional sequence

Validate schema closure → build namespace-aware structural model with particle/cardinality/type/identity semantics → review relational plan → create/update versioned PostgreSQL tables → validate and load XML instances transactionally → define business facts/dimensions/metrics → execute data jobs with quality/lineage → expose report APIs/UI. Structural entity/property metadata is useful in both the ontology and database paths, but both must retain the validated source semantics and explicit unsupported cases.

No application code changed in this audit. The previous agent/OSLC/PostgreSQL fixes do not address these separate XSD model defects. This review does not certify full XSD 1.0/1.1 or QIF/AP242/AP239 conformance.


## Implementation follow-up

Conversion now retains structural-model-v2 and review-only analytics-schema-plan artifacts in the v2 XSD data-product draft. The report fails closed on bad/missing/traversing schema closure and compiles XSD grammar with lxml when available. Named/root/anonymous entities are namespace-aware, refs resolve across closure, effective cardinality and particle paths are retained, repeated scalars have entity tables, facets/decimal precision are retained, prohibited attributes are omitted and nillability is reflected. Unsupported choice/group/identity/facet/temporal/mixed-content cases explicitly block SQL generation instead of unsafe flattening. Existing schema analytics jobs accept v1/v2 drafts and no longer require Spark for bounded schema statistics.

Remaining implementation: generic instance materialization, approved execution/versioning of generated relational schemas, complete specialized mappings for blocked constructs, dimensional business profiles and operational warehouse reporting. This change provides a structural design data product; it does not claim to deliver a full analytics warehouse. OWL compositor semantics remain a separate limitation; the analytics model reads original XSD instead.

Tests cover source closure, QName collisions, anonymous/repeated entities, choice/group blockers, datatype facets, prohibited/nillable fields, actual conversion artifact wiring and the v2 data job without Spark. Commit and push status is recorded in Git.
