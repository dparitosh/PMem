# Semantic Integration and Lambda-Style Data Pipeline

## Purpose

This design explains how DEPO turns heterogeneous engineering information into
a governed Digital Thread without maintaining separate meanings for batch and
near-real-time processing. It implements the framework's principle of **one
semantic contract**: CEIM identity, mappings, ontology versions, SHACL rules,
policy decisions, and provenance must mean the same thing on every path.

It is a target architecture. The batch foundation is available today; the
speed path provides a disabled-by-default governed event boundary. A named
source, throughput, latency, ownership and retraction policy must be approved
before it is enabled. Both paths are implemented as
named **data jobs** in one governed data flow, with Apache Spark as the
execution engine for volume-oriented jobs.

## Scope and non-goals

In scope:

- Engineering source files, APIs, documents, standards schemas, and later
  event feeds.
- Extracting business objects and relationships into CEIM.
- Validating, approving, publishing, querying, and reconciling semantic graph
  assertions.
- Rebuilding a trusted graph from retained inputs.

Out of scope:

- Running scheduled or production-volume Spark workloads in a FastAPI request
  worker. The implemented data-pipeline API is a bounded **preview** service:
  it may initialize one local Spark session to validate a small transformation
  and return telemetry, but it does not publish graph data, advance a source
  checkpoint, or replace a scheduled job runner.
- Giving an agent direct graph-write authority.
- Using a source schema as proof of an instance-data mapping.
- Adding a message broker, stream processor, or second graph store without a
  customer workload that needs it.

## Reference-architecture alignment

The Semantic Digital Engineering Reference Architecture describes a layered
flow, not a mandatory product stack. The table below maps each prescribed
responsibility to one DEPO owner and records the delivery state so no preview
service is mistaken for a production data pipeline.

| Reference layer/component | DEPO service or component | Status and boundary |
|---|---|---|
| Engineering source systems and acquisition | Ingestion, schema-set, OSLC, and source-profile adapters | Available for supported file/API sources; source authority and artifact provenance stay external. QIF is one supported source profile, not the pipeline identity. |
| Industrial data platform: catalog, metadata, lineage, policy | Data catalog, data products, metadata registry, PostgreSQL control plane | Foundation available; a single ISO 11179 lifecycle contract is still planned. |
| Canonical transformation | CEIM service and governed mapping packs | Available for AP242, QIF, ReqIF, and Teamcenter PLMXML packs. The PLMXML adapter retains the source as PLMXML and produces a CEIM batch; it does not relabel a Teamcenter export as AP242. QIF structural XSD validation and semantic mapping are separate automated checks. Detailed geometric primitives remain source-artifact evidence until CEIM gains an approved geometry profile. |
| Metadata enrichment and standards mapping | Ingestion adapters, CEIM mappings, ontology service | Available as explicit mappings and ontology releases; unmapped types must enter review rather than be inferred. |
| Industrial ontology and semantic governance | Ontology service, Semantica adapter, SHACL/policy/approval boundaries | Foundation available; steward-reviewed vocabulary curation is planned. |
| Enterprise knowledge graph | Graph service with governed CEIM publication and Neo4j/RDF projections | Available for approved publications; GraphQL/SPARQL interoperability is planned. |
| Semantic engineering services | Graph, OSLC, catalog, agentic services | Available through OpenAPI/OData service contracts; evidence-grounded companion completion remains planned. |
| Batch execution plane | Spark data-pipeline service plus portable Spark runtime | Bounded transformations, durable telemetry, a PostgreSQL-backed versioned job-definition control plane, supervised interval scheduling, retained-input replay, and bounded retry are implemented. A real scheduled source-run acceptance is still required before declaring the batch plane production-ready. |
| Speed/event path and reconciliation | Future authenticated event adapter, idempotency/watermark and reconciliation jobs | Designed only. No Kafka/Flink/broker or provisional assertion flow is enabled without a named source and latency target. |
| Digital Thread, Twin, GraphRAG and agents | CEIM/graph/OSLC/agentic integration | Foundational graph and agent tools exist; closed-loop telemetry, GraphRAG retrieval evidence, and autonomous actions remain separately governed roadmap items. |

This mapping follows the reference sequence: source systems → industrial data
platform → semantic pipeline → CEIM/ontology → enterprise graph → semantic
services/AI. Each row owns a single boundary; Spark cannot bypass CEIM,
approval, catalog, or graph publication services.

### Spark and Neo4j connector boundary

When `DEPO_SPARK_NEO4J_ENABLED=true`, the data-pipeline service configures the
official Neo4j Connector for Apache Spark from an operator-provided Maven
coordinate (`DEPO_SPARK_NEO4J_PACKAGE`) and the existing Neo4j deployment
configuration. This enables governed Spark jobs to read graph data as DataFrames
without adding a Python connector dependency. The current official Connector 6.0
coordinate (`org.neo4j.connectors:spark:6.0.0-s_2.13`) requires Spark 4.0–4.1
and Scala 2.13; the service rejects an unsupported Spark runtime before it tries
to initialize the connector.

The connector is deliberately not a bypass for graph publication: Spark may
prepare, validate, and stage CEIM output, but approved writes remain CEIM →
graph-service mutations with registry evidence and SHACL checks.

## Logical flow

```text
                ┌─────────────────────── source systems ───────────────────────┐
                │ PLM / CAD / ALM / ReqIF / QIF / OSLC / MES / QMS / documents │
                └───────────────────────────────────────────────────────────────┘
                                      │
                         capture artifact or source event
                                      │
                 ┌────────────────────┴────────────────────┐
                 │ immutable artifact + source provenance   │
                 └────────────────────┬────────────────────┘
                                      │
             ┌────────────────────────┴────────────────────────┐
             │                                                 │
   batch path (trusted rebuild)                    speed path (provisional context)
   scheduled / replayable                          event-driven / bounded latency
             │                                                 │
   parser → CEIM mapping → SHACL                   adapter → same CEIM mapping → SHACL
             │                                                 │
   steward/policy approval                          policy + event quality gate
             └────────────────────────┬────────────────────────┘
                                      │
                         reconciliation and publication gate
                                      │
                   governed graph projection + data product
                                      │
                     graph APIs, OSLC, search, companion, agents
```

## Data flow and Spark job model

The pipeline is a sequence of independently runnable data jobs. A job never
passes an in-memory Python object to the next job as its only hand-off; it
publishes a versioned output manifest containing immutable input/output
references, schema/CEIM versions, metrics, validation evidence, and a
checkpoint. That makes jobs schedulable, retryable, observable, and suitable
for Apache Spark.

```text
Source artifact/event
        │
        ▼
CaptureJob ──► ParseJob ──► NormalizeJob ──► ValidateJob ──► ReasonJob ──► ReconcileJob ──► PublishJob
  immutable       staging       CEIM batch       SHACL/policy       approved       derived          approved       graph + catalog
  artifact        records       + lineage        report             assertions     projection     data product
        │               │             │               │                 │                │
        └───────────────┴─────────────┴───────────────┴─────────────────┴────────────────┘
                         persisted job manifests, checkpoints, and correlation IDs
```

## Enterprise Lambda reference topology

This is the accepted topology for DEPO. It preserves one semantic contract
between the complete/replayable batch view and the provisional low-latency
view; neither path may create a different ontology or write the graph outside
the governed publication boundary.

```text
Enterprise engineering sources
CAD / PLM / ALM / ERP / MES / QMS / IoT / documents / standards
        │
Connectors and ingestion
APIs · OSLC/TRS · CDC · message bus · file drop · event gateway
        │
Parser and extraction
STEP/AP242/AP239 · SysML/XMI · ReqIF · XML/JSON · CSV · PDF/OCR · telemetry
        │
        ├─ Batch path — complete and accurate ──────────────────────────────┐
        │   immutable raw zone → semantic batch pipeline → trusted batch view │
        │   capture/provenance     CEIM/RDF/SHACL/reasoning    reconciled graph│
        │                                                                      │
        └─ Speed path — low latency ────────────────────────────────────────┤
            event stream → semantic stream pipeline → near-real-time view    │
            change/telemetry  normalize/validate       alerts/provisional     │
                                                                             ▼
Semantic serving layer
enterprise knowledge graph · graph/SPARQL/search APIs · vector index ·
digital thread services · digital twin context
        │
Consumers and governed closed-loop actions
engineering search · impact analysis · configuration/compliance intelligence ·
copilots · agents · workflow orchestration

Cross-cutting semantic control plane: ISO 11179 metadata registry · industrial
ontology · SKOS taxonomies · persistent IDs · mapping registry · versioning ·
SHACL rules · stewardship · security · observability
```

### Component alignment and delivery state

| Target component | Current DEPO alignment | Delivery state |
|---|---|---|
| Enterprise source and connector layer | File/API ingestion, source profiles, schema sets, OSLC adapters | Available for supported sources. CDC, message bus, and event gateway are not enabled. |
| Parser and extraction layer | STEP/AP242/AP239, XMI, ReqIF, XML/JSON, CSV, QIF and document extraction | Available by supported parser. Direct document indexing is retired; unstructured document jobs produce content-addressed source and evidence-batch artifacts, chunk-cited semantic proposals, and a quality report without indexing or publishing graph facts. Telemetry parser and a common parser capability registry remain planned. |
| Immutable raw zone | Artifact handling and provenance/control-plane foundations | Partial: scheduled-job immutable input/output manifests and retention policy must be completed before a batch path is called production-ready. |
| Semantic batch pipeline | CEIM mappings, RDF projection, SHACL, policy/approval and Spark preview | Partial: `normalize-ceim`, `validate-semantic-batch`, checkpointing, reasoning and replayable job manifests are queued. |
| Trusted batch view | Governed CEIM graph publication, graph service, catalog/data products | Partial: trusted approved graph exists; complete lifecycle reconciliation, lineage index and durable watermarking are queued. |
| Event stream and semantic speed pipeline | No enabled source; design specifies CEIM/provisional assertion rules | Designed only. A named event source, owner, latency objective, idempotency and retraction rule are prerequisites. |
| Near-real-time view | No provisional event graph projection | Planned; it must visibly distinguish provisional from approved graph assertions. |
| Semantic serving layer | Graph, OSLC, OpenAPI/OData, catalog, agentic service | Partially available. A bounded read-only GraphQL API provides graph projections plus configured data-job-run and data-product read models; it cannot start Spark jobs or publish graph writes. SPARQL, federation, vector index and evidence-grounded retrieval remain planned. |
| Consumers and closed-loop actions | Search, graph traversal, impact/traceability foundations, agent tool catalog | Partial. Copilot evidence, policy-gated workflow actions and digital-twin feedback must be delivered separately. |
| Cross-cutting semantic control plane | CEIM, ontology/SHACL, approval/policy boundaries, metadata/catalog services | Partial. ISO 11179 stewardship lifecycle, SKOS curation, mapping registry, unified versioning and observability need convergence. |

**Architecture rule:** the batch path establishes the trusted, complete view;
the speed path improves awareness with explicitly provisional assertions.
Every source uses the same CEIM version, mapping digest, ontology release,
identity rules, SHACL profile, provenance and policy boundary.

### Canonical job contract

Every job has a common control-plane contract:

| Field | Purpose |
|---|---|
| `job_id` / `run_id` | Stable definition identity and unique execution identity. |
| `job_type` | One of capture, parse, normalize, validate, reason, reconcile, publish, or a governed extension. |
| `input_manifest_ids` | Immutable artifact or prior-job output manifests. |
| `output_manifest_id` | Immutable result registered as a data product or staging artifact. |
| `standard`, `mapping_digest`, `ceim_version`, `ontology_release` | Semantic reproducibility controls. |
| `checkpoint` | Source cursor/watermark and a deterministic resume point. |
| `correlation_id` | Links API request, Spark application, approvals, and graph publication. |
| `status` | `queued`, `running`, `validated`, `awaiting_approval`, `published`, `failed`, or `cancelled`. |
| `metrics` | Input/output/reject counts, durations, validation coverage, and watermark lag. |
| `data_quality` | Versioned quality profile, rule results, threshold outcome, rejected-record manifest, and remediation route. |
| `approval` | Required only for governed publication or policy exceptions; never embedded in a Spark executor. |

Spark submits and executes data-plane work. The DEPO control plane creates the
job definition, issues scoped input/output locations, records the run state,
and invokes the approved CEIM/graph publication API. Spark does not receive
graph credentials or bypass service boundaries.

### Structured and unstructured consistency

Both source classes use the same governed lifecycle and may not create a
parallel document-only graph:

```text
structured source:   artifact → parser → source CEIM batch → SHACL → catalog → approved publication
unstructured source: artifact → evidence/chunks → document proposal → source CEIM batch → SHACL → catalog → approved publication
```

The unstructured bridge is the versioned `unstructured-evidence` mapping pack.
It maps `Document` to CEIM `Document`, `DocumentChunk` to CEIM `Resource`, and
the evidence containment link to CEIM `HAS_PART`. Raw chunk text stays only in
the content-addressed evidence artifact; the graph carries stable identifiers,
content digests, provenance and the approved semantic projection. Therefore
unstructured enrichment cannot bypass CEIM, SHACL, data-product lineage or the
canonical publication API.

`POST /api/v1/pipeline/workflows/document-evidence/run` executes that
unstructured path as a fixed workflow chain. Callers select approved, enabled
versions of the validation, enrichment and CEIM-normalization job definitions;
the service transfers only the retained proposal artifact between stages. A
quality warning halts the chain. A completed workflow still requires the
separate canonical publication approval for its accepted semantic run.

### Data-quality job

`data-quality-assessment` is an independent, source-neutral governed job—not
a dashboard calculation. It accepts `quality-records-v1` and produces a
retained `data-quality-report-v1` with accepted and rejected partitions plus
completeness, validity, uniqueness and provenance evidence. It requires each
record to declare a source identity and source artifact. The Data Flow page
shows the number of configured quality/validation jobs and the selected run's
quality profile.

### Serialized schema analytics product

Engineering schema conversion now retains three linked immutable artifacts:
the source schema, its Turtle serialization, and a `schema-analytics-profile-v1`
report. The conversion response includes a `schema-analytics-data-product-v1`
draft containing those artifact references and the required approvals. It is
not auto-published: a steward must first approve the semantic release, then
submit the explicit Data Product API request. This keeps schema analytics
discoverable and reproducible without allowing an XSD upload to silently
create a catalog release or graph mutation.

The retained schema may then be supplied to the approved
`schema-analytics-product` data job. That Spark-backed job emits a durable
`schema-analytics-data-product-draft-v1` run manifest, metrics series and the
three artifact references. This makes schema analytics visible in Data Flow
alongside other jobs while preserving the separate Data Product approval gate.

### Implemented configuration boundary

`/api/v1/pipeline/jobs/definitions` is the current configuration API. A
definition is immutable by `job_id` and semantic `version`, starts as `draft`,
and must be explicitly approved before it can run. An approved definition may
be disabled immediately. The initial supported job type is
`interactive-quality-summary` with `semantic-core-v1`; it consumes the bounded
`quality-records-v1` input and emits `quality-summary-v1` telemetry.
`normalize-ceim` and `validate-semantic-batch` use the same lifecycle and
require a configured allowlist of standards, so a QIF definition cannot be
used to run an AP242 batch. They normalize/validate only and cannot publish to
the graph. This is a safe foundation for future job types, not a general
Spark-code upload API.

Every configured run persists a control-plane manifest containing the immutable
SHA-256 digest of its request and result, input/output contracts, artifact
references, checkpoint metadata, correlation ID, status and timestamps. The
raw payload is intentionally not copied into PostgreSQL; a production source
must instead be retained through the content-addressed artifact service and
referenced by `artifact_ids`.

Operator configuration remains environment based: `DEPO_SPARK_ENABLED`,
`DEPO_SPARK_HOME`, `DEPO_JAVA_HOME`, `DEPO_HADOOP_HOME`,
`DEPO_SPARK_MASTER`, `DEPO_SPARK_OUTPUT_ROOT`, and the optional official Neo4j
Spark connector settings. Production definitions will add manifests,
checkpointing, mapping/ontology versions, schedules, retry policy and scoped
service credentials before they are enabled.

### Embedded data quality contract

Data quality is part of every job's input/output contract. It is not a
separate dashboard or a final best-effort check. Each job emits a versioned
quality report and a separate rejected-record manifest; valid records can
continue only when the job's declared quality gate is met.

| Quality dimension | Embedded job check | Failure handling |
|---|---|---|
| Completeness | Required identifiers, source type, mandatory CEIM attributes, relationship endpoints, and required provenance are present. | Quarantine the record with rule code and source pointer. |
| Validity | Schema/parser checks, datatype/unit checks, controlled vocabulary checks, CEIM SHACL, and ontology/policy rules pass. | Block the invalid partition from publication. |
| Uniqueness | Stable business key, event ID, artifact digest, and mapping identity are deduplicated/idempotent. | Route duplicates to reconciliation; never create duplicate graph assertions. |
| Consistency | Source revision, CEIM mapping version, ontology release, namespace, and relationship types agree. | Create a conflict record for steward review. |
| Timeliness | Source/event timestamp, batch watermark, processing delay, and provisional assertion age meet the job profile. | Flag stale data; do not silently present it as current. |
| Accuracy evidence | Source checksum, parsing diagnostics, mapping confidence, validation evidence, and transformation lineage are retained. | Mark as `pending_review` when evidence is insufficient. |

Every job declares a **quality profile** containing rule IDs, threshold values,
severity mapping, and permitted exception policy. A profile is versioned with
the job definition and semantic release. For example, a publication job may
require 100% valid identifiers and SHACL conformance, while a discovery job may
allow warning-level documentation gaps but must still quarantine malformed
records.

```text
job input → profile checks during each transformation → accepted partition
                  │                                      │
                  ├─ rejected partition + rule evidence   ├─ aggregate quality gate
                  └─ conflict/review queue                └─ publish only if passed/approved
```

No job may discard rejected records, coerce invalid values silently, or advance
its checkpoint when a blocking quality threshold fails. Quality reports and
rejected-record manifests are cataloged alongside the successful output so a
steward can reproduce and remediate the result.

### QIF validation gates

QIF has three distinct validation layers; passing one does not imply the next:

1. **QIF 3.0 XSD conformance.** The CEIM QIF validation endpoint checks the
   supplied document against the bundled schema without fetching remote
   resources.
2. **QIF format, quality, and semantic checks.** The official
   `QualityInformationFramework/qif-validation-tools` suite is an optional
   external validator. Its schema checker and XSLT report must be retained as
   source-quality evidence; the product does not bundle the external binaries.
3. **Semantic normalization and governance.** Declared QIF-to-CEIM mappings,
   CEIM SHACL, provenance, ontology policy, and approved publication validate
   the meaning and lifecycle of accepted information.

For the NIST AP242 QIF sample, the official schema checker succeeded; its XSLT
report contained no format or semantic findings and 174 geometry/topology
quality findings. Those findings are source-quality evidence for engineering
review, not a reason to change the source data or silently suppress geometry.

### Initial job catalogue

| Job | Spark responsibility | Input | Output | Publication rule |
|---|---|---|---|---|
| `capture-artifact` | Optional distributed file discovery/checksum for large drops. | Source export or file drop. | Immutable artifact manifest plus checksum/completeness report. | None; capture is not graph publication. |
| `parse-engineering-source` | Partitioned parsing/extraction for supported source families. | Artifact manifest. | Typed staging records, diagnostics, and rejected-record partition. | Unknown/malformed types are quarantined to review. |
| `normalize-ceim` | Apply an approved mapping pack at scale and enforce identity/type completeness. | Staging records plus mapping digest. | CEIM entity/relationship batch, lineage, and mapping-quality report. | No direct graph write. |
| `validate-semantic-batch` | Partition checks and aggregate data/semantic quality evidence. | CEIM batch and ontology release. | SHACL/policy report plus accepted, rejected, and conflict partitions. | Blocking quality failures cannot proceed. |
| `rdf-quality-statistics` | Read-only Spark lexical integrity and predicate-distribution checks for immutable N-Triples artifacts. | Content-addressed N-Triples artifact. | Versioned RDF quality report. | No graph, vector, or catalog write. |
| `reason-semantic-batch` | Run an approved, bounded inference profile after validation. | Validated CEIM batch plus ontology/inference profile release. | Derived assertions with rule evidence and inference-quality report. | Derived assertions remain attributable and cannot bypass validation/publication. |
| `reconcile-semantic-state` | Compare source revision/watermark with approved and provisional state. | Valid CEIM output plus prior checkpoint. | Reconciliation plan, conflicts, quality trend, and next checkpoint. | Conflicts require steward review. |
| `publish-semantic-projection` | Verify the release quality gate and prepare bounded RDF/projection payloads; no DB driver in executor. | Approved reconciliation plan. | CEIM publication request, quality evidence, and data-product manifest. | CEIM approval endpoint performs the graph write. |
| `compact-provenance` | Retain/compact staging outputs under the approved retention policy. | Expired staging manifests. | Retention report. | Requires retention-policy approval. |

The first Spark implementation should be `normalize-ceim` followed by
`validate-semantic-batch` for a real high-volume source. `reason-semantic-batch`
follows only when the ontology release includes an approved bounded inference
profile. This sequence exercises the
shared semantic contract without prematurely implementing a streaming system.

## Shared semantic contract

Every adapter must emit a canonical envelope before it can publish.

| Field | Rule |
|---|---|
| `event_id` | Globally unique, stable across retries; derived from source event ID or artifact digest plus record key. |
| `source_system` and `source_standard` | Identify the authority and representation, such as Teamcenter/ReqIF or QIF 3.0. |
| `source_record_id` | Original business identifier; never overwritten by a generated graph ID. |
| `ceim_version` | Exact CEIM contract version used to normalize the record. |
| `mapping_pack`, `mapping_version`, `mapping_digest` | Declared source-to-CEIM mapping evidence. |
| `ontology_release` | Approved ontology/namespace version used for semantic projection. |
| `observed_at`, `ingested_at` | UTC source observation and DEPO ingestion timestamps. |
| `artifact_id` or `source_locator` | Immutable evidence pointer and content digest where an artifact is involved. |
| `validation_status` | `valid`, `invalid`, `warning`, or `pending_review`; invalid data cannot be published. |
| `assertion_state` | `provisional` for speed-path assertions, `approved` for reconciled batch assertions, or `retracted`. |
| `correlation_id` | Carries a request/workflow correlation identifier across services. |

CEIM entities and relationships remain the canonical payload. The current CEIM
service already records the mapping pack/version/digest and validates an RDF
projection with SHACL. The envelope above is the additional control-plane
record required before large-scale batch or speed processing is introduced.

## Batch path: authoritative reconstruction

The batch path produces the trusted lifecycle view. It is used for initial
loads, schema and standards ingestion, large source extracts, repair, replay,
and periodic reconciliation.

1. **Capture (`capture-artifact`).** Store the source artifact through the immutable artifact
   boundary with content digest, source location, classification, owner, and
   collection timestamp.
2. **Extract (`parse-engineering-source`).** Run the appropriate parser or declared source-profile adapter.
   Examples include AP242 EXPRESS/XSD, STEP/STPX, ReqIF, QIF, XMI, PLMXML, JSON,
   and CSV. The parser reports skipped records and parsing diagnostics; it does
   not silently turn unknown structures into ontology assertions.
3. **Normalize (`normalize-ceim`).** Resolve an approved mapping pack and normalize records to
   CEIM. Unmapped types are sent to a review queue with source evidence, not
   guessed.
4. **Validate (`validate-semantic-batch`).** Apply source checks, CEIM SHACL, ontology quality checks, and
   policy checks. Persist accepted, rejected, and conflict partitions plus a
   validation summary keyed by artifact, mapping, quality profile, and ontology
   release.
5. **Stage.** Write a versioned, immutable normalized output and data-product
   manifest. The manifest identifies input artifacts, code/mapping versions,
   record counts, errors, and watermarks.
6. **Reconcile (`reconcile-semantic-state`).** Compare the validated output to
   the prior approved watermark. Produce conflicts and a deterministic next
   checkpoint before any graph update.
7. **Approve.** A steward approves publication when required by classification,
   policy, or mapping confidence. Approval records the person or gateway
   principal, timestamp, decision, and reviewed release.
8. **Publish (`publish-semantic-projection`).** Call the CEIM publication endpoint, which validates again and
   delegates graph writing to the graph service. No batch worker writes Neo4j
   directly.
9. **Checkpoint.** Advance the source watermark only after the publication and
   catalog/data-product registration outcomes are durable. Failed outputs are
   retryable from the immutable stage, not by reparsing an altered source.

Spark is appropriate for `parse-engineering-source`, `normalize-ceim`,
`validate-semantic-batch`, `reason-semantic-batch`, and
`reconcile-semantic-state` at scale. It runs as
a scheduled or supervised job, reads approved artifacts, and calls DEPO
service APIs only at the governed boundaries.

## Speed path: provisional low-latency context

The speed path is reserved for named sources that emit change events, such as
an OSLC/PLM change notification, a quality event, or equipment telemetry.
It must use the same adapter, CEIM mapping pack, namespace, SHACL shapes, and
identity rules as the batch path.

1. Receive an authenticated event with an event identifier, source timestamp,
   source revision, and correlation ID.
2. Reject duplicates using the source event identifier and a bounded
   idempotency store.
3. Normalize and validate the small event payload using the same CEIM contract.
4. Publish only validated records as `provisional` assertions with an expiry or
   reconciliation watermark. Do not overwrite an approved assertion merely
   because a late event arrived.
5. Expose provisional status to graph/API consumers so copilots and impact
   analysis can distinguish current signals from reconciled evidence.
6. Route unsupported event types, validation failures, and conflicts to
   stewardship review.

The speed path must not be implemented as a second source of ontology truth.
It improves awareness; the batch path remains the mechanism that establishes
the trusted, complete graph.

## Reconciliation rules

| Situation | Required outcome |
|---|---|
| Batch and speed agree on the same source revision | Mark the batch assertion `approved`; retire the matching provisional assertion. |
| Speed event is newer than the last batch watermark | Keep it provisional and include it in the next batch window. |
| Same enterprise identity, incompatible attributes | Preserve both assertions with provenance, mark a conflict, and require steward resolution. |
| Mapping or CEIM version changes | Reprocess the affected artifact scope; never merge old and new semantic interpretations without version evidence. |
| Source deletion or tombstone | Publish a retraction with source evidence; do not physically delete historical provenance by default. |
| Failed publication | Keep the staged output and retry idempotently. Do not advance the source watermark. |

Reconciliation must be deterministic: given the same artifact set, mapping
versions, ontology release, and watermark, it produces the same approved graph
projection. This is the replayability requirement.

## Governance and security gates

- **Metadata registry:** allocates ontology and mapping identifiers, namespaces,
  owner/steward, lifecycle status, semantic version, and compatibility policy.
- **Vocabulary governance:** SKOS schemes and mappings are steward-reviewed;
  unknown terms cannot become preferred enterprise vocabulary automatically.
- **Policy and quality:** SHACL/policy failures block publication. Warnings may
  be accepted only with recorded steward rationale.
- **Approval:** graph publication, data-product release, and agent actions use
  explicit approval identities. Agents may prepare or recommend; they do not
  bypass the publication boundary.
- **Access:** APIM/Entra is the production ingress. Service ports and graph
  databases remain private. Disabled local authentication is loopback-only.
- **Audit:** record source, artifact digest, mapper, ontology release,
  validation result, approval, publication response, correlation ID, and
  watermark for every published scope.

## DEPO service responsibilities

| Service | Pipeline responsibility |
|---|---|
| Ingestion | Capture, source-profile execution, engineering parser workflows, staging requests. |
| CEIM | Declared mapping packs, normalization, RDF projection, SHACL validation, approved publication request. |
| Ontology | Approved ontology artifacts, namespace services, reasoning/merge governance, semantic release metadata. |
| Graph | Sole graph projection/persistence boundary and explorer/query projection. |
| Data product and catalog | Immutable manifests, lifecycle, owner/steward metadata, publication history, and discovery. |
| OSLC | Governed source-system integration and explicit synchronization boundaries. |
| Agentic | Tool discovery/orchestration; mutation plans require approval and use service APIs. |
| Spark | Optional high-volume batch execution plane. The FastAPI service exposes a bounded preview transformation only; scheduled jobs remain outside request workers and retain the production data-plane boundary. |

## Implementation sequence and acceptance criteria

### Increment 1 — semantic envelope and batch lineage

- Define the shared envelope and persist a manifest for every CEIM batch.
- Add artifact, mapping, ontology release, validation, and correlation evidence
  to the data-product manifest.
- Acceptance: a ReqIF or AP242 batch can be replayed from its artifact digest
  and produces the same CEIM batch and validation summary.

### Increment 1a — data-job control plane and first Spark job

- Register job definitions and immutable run manifests in the data catalog.
- The implemented data-pipeline API provides bounded, interactive quality
  summaries and telemetry; it is not a replacement for scheduled data jobs.
- Implement `normalize-ceim` and `validate-semantic-batch` as Spark jobs using
  the existing portable Spark installation.
- Embed quality profiles, rejected-record manifests, and checkpoint blocking in
  both jobs.
- Acceptance: a scheduled job accepts only a registered input manifest,
  produces a versioned CEIM output and quality manifest, resumes only from a
  passing checkpoint, and never publishes directly to Neo4j.

### Increment 2 — governed batch reconciliation

- Add source watermark and idempotency records.
- Publish a scoped graph projection only after approval and durable catalog
  registration.
- Acceptance: retrying a failed run cannot create duplicate entities or advance
  its watermark.

### Increment 3 — first speed source

- Select one source, event type, volume, latency objective, data owner, and
  retraction rule.
- Implement bounded idempotency and provisional assertions for that source.
- Acceptance: duplicate, out-of-order, invalid, and conflicting events have
  deterministic outcomes and are visible to a steward.

### Increment 4 — reconciliation and serving

- Reconcile speed assertions with a batch window and expose assertion state in
  graph/OSLC/companion responses.
- Acceptance: a user can trace any displayed relationship to its source,
  mapping, validation, approval, and current assertion state.

## Operational metrics

Track these per source, mapping pack, and ontology release:

- records received, normalized, valid, blocked, and published;
- provenance and semantic-validation coverage;
- completeness, validity, uniqueness, consistency, timeliness, and accuracy-
  evidence scores by quality profile;
- rejected, quarantined, and steward-resolved record counts with rule codes;
- duplicate/replayed events and unresolved conflicts;
- end-to-end batch duration and speed-path latency;
- graph publication retry/failure rate;
- watermark lag and provisional assertion age;
- approved versus rejected mapping/term changes.

These measures are the release gate for scaling the pipeline, not merely
dashboard metrics.
