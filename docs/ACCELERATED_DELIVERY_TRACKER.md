# DEPO Focused Delivery Tracker

## PostgreSQL analytics and knowledge-graph audit — 2026-09-18

- Confirmed the `semantic` PostgreSQL schema, migrations 1–4, control-plane
  tables, and `depo_ontology_analytics` view are present.
- Added an approval-gated, idempotent legacy ontology analytics backfill. It
  derives RDF metrics from retained artifacts and records a draft lifecycle;
  it cannot approve or publish an ontology. Applied locally to two AP242
  records and the QIF record.
- PostgreSQL catalog now exposes analytics for all four registered ontologies:
  AP242 (24,902 triples / 3,000 classes each), QIF (60,526 / 3,272), and
  PLMXML (66,068 / 5,235). Live Neo4j contains 22,217 published RDF resources.
- Catalog registration and Neo4j publication remain deliberately distinct:
  draft catalog records are not inferred to be graph-approved merely because a
  similarly named graph projection exists.

## Durable OSLC TRS control plane — 2026-09-18

- OSLC TRS change-log state now uses the PostgreSQL control-plane registry and
  advisory locking by default, so an ordered lifecycle feed survives service
  restart and can be shared across instances. File mode requires the explicit
  `OSLC_TRS_STORE=file` local-development setting.
- Focused OSLC/TRS and service-contract verification: 29 tests passed. The
  restarted live OSLC service returned a `trs:TrackedResourceSet` descriptor
  and a readable PostgreSQL-backed changelog.

## Control-plane contract cleanup — 2026-09-18

- Removed duplicate quality-profile and telemetry keys from durable data-job
  manifests, leaving one authoritative value in API and persisted output.
- Removed the duplicate remote-sync capability from the OSLC OData catalog.
  The generated OpenAPI contract exposes exactly one remote-sync path.
- Focused pipeline, service-contract, and OSLC lifecycle tests: 32 passed.
  All local PMem and OSLC readiness endpoints returned HTTP 200 after restart.

## Publication recovery and mapping release gate — 2026-09-17

- Normalized CEIM batches now prove the active mapping-pack identifier,
  version, and SHA-256 digest for every entity and relationship. A stale or
  mixed retained batch is rejected before validation or graph publication;
  replay must use its original governed mapping release or be deliberately
  remapped and approved.
- Graph publication now accepts the durable pipeline run ID as a publication
  ID and records a Neo4j `OntologyPublication` receipt. If the CEIM response
  times out or a gateway returns 502/503/504, the pipeline queries that receipt
  and advances a checkpoint only when the committed publication is proven. It
  never blindly retries a write.
- Existing graph data remains unchanged by this safety change. A controlled
  replay/re-publication is required to apply newly added relationship typing.

## Approved PLMXML structural publication — 2026-09-17

- User-approved local-test mapping release
  `plmxml-motor-structural-local-test-20260917` version 0.3.0 was created,
  reviewed, and approved with explicit non-certification evidence.
- New governed run `a98e68ee-7504-4798-a709-f73c407cf176` completed with 1980
  entities and 1688 structural relationships; canonical publication advanced
  its PostgreSQL checkpoint. Receipt: 7647 RDF resources, 22012 relationships,
  and 1049 typed hierarchy edges.
- Publisher now promotes the full declared CEIM relationship vocabulary to
  typed Neo4j edges (including TRACE_TO, SATISFIES, REALIZES, verification,
  impact, and production relations). Existing published graphs are immutable;
  this behavior applies to future or deliberately replayed publications.
- Focused graph/CEIM verification: 9 tests passed. Services restarted and key
  readiness endpoints return HTTP 200.

## Relationship provenance quality gate — 2026-09-17

- CEIM RDF reifies every canonical relationship as an RDF statement and retains
  `sourceStandard`, `sourceType`, and `sourceKey` provenance.
- New SHACL relationship assertion shape requires source, predicate, target,
  and the three provenance values; adapters without a field-level key retain a
  deterministic `mapping:<relationship-source-type>` key.
- Basic CEIM relationship validation conforms with two node shapes and one
  property shape. Services restarted; ontology, graph, CEIM, and pipeline
  readiness endpoints return HTTP 200.

## PLMXML structural-reference extraction — 2026-09-17

- PLMXML mapping pack now declares source structural fields instead of relying
  only on generic parser relationship labels: ProductInstance `parent_ref` and
  `part_ref`, ProductView `root_refs` and `product_ref`.
- Each CEIM relationship records its `source_key` in provenance. Free-text
  attributes such as names, revisions, and descriptions remain properties.
- The Induction Motor validation sample emits 1980 entities and 1688 declared
  structural relationships (340 more than the prior generic-parser result),
  with all relationship provenance keys verified. PMem services were restarted
  and ontology, graph, ingestion, CEIM, and pipeline readiness return HTTP 200.

## Structural and recovery fixes — 2026-09-17

- CEIM SHACL contract now exposes a named `ExternalIdPropertyShape`; live
  validation reports one node shape and one property shape.
- Graph publication promotes CEIM `hasPart`, geometry, feature, and
  characteristic predicates to typed Neo4j relationships while retaining the
  source RDF predicate. Existing published data is not rewritten implicitly.
- Fixed Windows recovery: stop script now discovers only PMem processes by the
  deployment manifest instead of trusting stale PID files. A clean restart was
  performed; ontology, graph, CEIM, and pipeline readiness endpoints return 200.

## Runtime reliability fixes — 2026-09-17

- Renamed internal `backend.platform` package to `backend.depo_platform`.
  This removes the collision with Python's standard-library `platform` module
  when operators run pytest from the `backend` directory.
- Canonical and speed-path publication timeouts now use bounded, validated
  `GRAPH_PUBLICATION_TIMEOUT_SECONDS` configuration (default 180 seconds,
  minimum 1, maximum 3600). Invalid values safely use the default.
- Replaced the obsolete localhost:8000 import CLI, whose upload/preview/commit
  routes no longer exist, with a client for the governed ingestion endpoint on
  port 8014. It cannot clean or publish the graph.
- Focused backend verification: 32 tests passed from the backend directory.

## Scoped PLMXML publication completed — 2026-09-17

- User-authorized local-test mapping release `plmxml-motor-local-test-20260917`
  version 0.2.0 created and transitioned through review to approved via the
  metadata API, with explicit limited-validation evidence (not certification).
- Published run `451c9183-1e06-43b3-bc6c-8380d12b9c6e` through pipeline → CEIM →
  graph API. First request timed out after its graph transaction committed.
- Added missing composite lookup index on OntologyResource(ontology_id, iri).
  Re-runnable provisioning DDL: `infra/deployment/neo4j-publication-index.cypher`.
  Governed idempotent retry returned HTTP 200; no direct graph-data bypass.
- Independent PostgreSQL read confirms `published` and checkpoint `advanced`
  at 2026-09-17T08:00:54.770697+00:00. Neo4j read confirms 7304 RDF resources
  and 18624 edges, matching receipt counts after retry (including provenance).
- Business input remains 1980 entities / 1348 relationships. These counts are
  not interchangeable with the RDF projection counts.
- Generated XSD ontology remains draft; full semantic constraints and customer
  certification are still outstanding. This closes only scoped local publication.

## Recovery and publication recheck — 2026-09-17

- Follow-up: increased service readiness timeout from 90 to 300 seconds,
  configurable up to 3600 seconds; added waiting/log-location diagnostics.
  PowerShell syntax validation passed. Ontology `/readyz` now returns HTTP 200
  after completing its earlier startup. The startup availability blocker is
  cleared; publication and receipt verification below remain pending.

- PostgreSQL recovered after an unclean shutdown; the pipeline API returns saved
  run `451c9183-1e06-43b3-bc6c-8380d12b9c6e` as completed, retaining 1980 entities
  and 1348 relationships. Its checkpoint remains `awaiting_approved_publication`.
- Live graph health returns HTTP 200 for Neo4j database `ontology`.
- Fixed Windows startup logging to place future PostgreSQL logs outside PGDATA,
  avoiding an active log handle in the directory crash recovery must sync.
- User authorized scoped local publication, but no publication performed:
  ontology service port 8011 remains unavailable after the startup readiness
  timeout. Restore this dependency, record the scoped release approval through
  its API, publish through the pipeline canonical endpoint, then verify the
  receipt/checkpoint and graph counts. Do not bypass the release gate.
- The generated schema ontology remains draft with partial semantic coverage;
  local publication approval must not be described as customer certification.

## PLMXML governed job execution — 2026-09-16

- Neo4j graph health verified OK (database ontology).
- Initial run 2df93b34-7de2-4518-b1d7-aeb534495b89 failed because Spark was disabled.
  Restarted only pipeline with installed Spark 4.1.2/Java 21 and replayed retained input.
- Run 451c9183-1e06-43b3-bc6c-8380d12b9c6e completed in 55.2 seconds at
  2026-09-16 10:03:41 IST; 1980 entities and 1348 relationships retained.
- PostgreSQL manifests retain accepted artifact, mapping digest, replay lineage,
  and checkpoint state awaiting_approved_publication. No Neo4j write performed.
- Publication blocked: no approved PLMXML semantic release. Existing boc-core and
  historical governance acceptance approvals must not substitute for this draft.
- Validation scope is limited: current CEIM SHACL summary has one node shape and
  zero property shapes. Full semantic conformance is not established by that pass.
- Restart pipeline with -EnableSpark in the standard startup script; the manual
  runtime enablement is process-scoped. Schema draft remains partial and unapproved.

## PLMXML draft analytics and OSLC closure — 2026-09-16 09:53 IST

- This pass ran approximately 09:49–09:53 IST (3 minutes 49 seconds).
- Applied migration 4: `semantic.depo_ontology_analytics`, a relational VIEW of
  registered ontology statistics/provenance, not instance-domain analytics tables.
- Verified SQL row for plmxml_12662e4cec26454b: 5235 classes, 516 object properties,
  3865 datatype properties, lifecycle draft.
- Connected retained catalog artifacts to authenticated/authorized OSLC shape
  lookup and added ontologies to lifecycle discovery. Live HTTP response is 200
  with 5235 classes and 4381 properties, explicitly draft/partial semantics.
- Persisted a local-development grant scoped to this ontology in ignored .env.local;
  restarted only OSLC. No approval or publication was fabricated.
- 27 focused OSLC tests passed. Open semantic limitations remain XSD facets,
  choices/groups, identity constraints and QName scope; approval requires review.

## PLMXML artifact registration — 2026-09-16 09:42 IST

- Continuation began 09:39 IST; registration/state verification took approximately
  3 minutes 30 seconds. Ontology, pipeline health and OSLC catalog return HTTP 200
  after slow startup (the startup script's initial readiness deadline expired).
- Registered PostgreSQL ontology draft `plmxml_12662e4cec26454b`; read-back confirms
  lifecycle draft and retained analytics-profile artifact. 23 source XSDs retained.
- Generated RDF: 66068 triples, 5235 OWL classes, 516 object properties and
  3865 datatype properties. Generator reports partial XSD semantic completeness.
- Analytics artifact is JSON, NOT a PostgreSQL relational analytics schema.
- OSLC draft shape returns 404: standalone catalog registration is not yet
  connected to the legacy OSLC ontology-shape path. This remains a concrete gap.
- No approvals or graph/product publication were performed. Semantic review,
  relational analytics materialization and OSLC draft discovery remain pending.

## PLMXML live-state verification — 2026-09-16

- Extended explicit PLMXML mapping v0.2.0 for Terminal, ConnectionRevision and
  GDE as Resource, retaining source types; occurrence references use TRACE_TO.
- Real sample: 1980 entities, all 1348 parsed relationships retained, zero
  dropped relationships. Six focused PLMXML/OSLC tests pass.
- Started existing PostgreSQL cluster after interrupted shutdown; read-only
  verification succeeded after recovery despite initial startup wait timeout.
- PostgreSQL has eight semantic control-plane tables. Two PLMXML-related
  validation runs are completed; these are prior runs, not this sample's release.
- No rows in ontology_catalog, catalog_products or data_products. Therefore no
  registered PLMXML ontology or published analytics product is verified.
- Schema analytics currently produces JSON profiles/drafts, not relational
  analytics tables. Full ontology generation/registration and approved product
  publication remain open. Do not equate parser success with these steps.

## PLMXML execution follow-up — 2026-09-16

- Corrected validator path identity: all 23 schemas combine successfully and
  003257_InductionMotor.xml passes XSD validation. The earlier duplicate type
  diagnosis was a validator URI-resolution defect, not incompatible schemas.
- Executed parser and CEIM normalization. Fixed fragment references (#id) being
  compared with bare entity ids: 1680 entities and 1048 relationships now emitted.
- 300 of 1348 parsed relationships remain unmapped; counts now explicitly report
  this loss. Full semantic completeness is NOT claimed. No graph publication.

## PLMXML schema-set audit — 2026-09-16

- Added read-only `tools/diagnostics/validate_schema_set.py`, with local-only
  schema resolution. Tested the supplied 23 XSDs and InductionMotor XML.
- All 23 individual schema entry points compile. Individual entry points do
  not validate this multi-extension export (RevisionRule/Terminal coverage).
- Combining all files indiscriminately fails with duplicate SetupInstanceType.
  An explicit compatible extension profile is required; do not label this as
  invalid source data or silently drop schemas to manufacture a pass.
- No data published; semantic/AP242 mapping validation remains pending.

## Context and policy safety — 2026-09-16

- Disabled caller-selected policy exemptions; evaluation rejects them with 422.
- Context writes reload under an advisory lock and persist a staged graph before
  replacing shared memory, preventing failed-request leakage and stale-writer loss.
- Analytics explicitly identifies bounded-projection scope.
- Verified: two graph analytics tests and five context/policy tests passed;
  changed Python modules compile. The context suite completed with Hugging Face
  offline flags after earlier collection delays; networked initialization remains
  an operational concern.
- Remaining: diagnose slow import initialization and refresh
  long-lived readers, and implement separately governed decision/causal/temporal
  capabilities. These are not made available by this safety patch.

## Pre-push review — 2026-09-15

- Added default-deny lifecycle resource grants, denied unauthorized collection
  enumeration, and removed spoofable bootstrap reader identity headers.
- Verification: 47 focused contracts, OSLC, gateway trust and DT compatibility
  tests passed. Two rdflib deprecation warnings remain.
- Release status: development checkpoint, NOT production certification.
- Open implementation: lifecycle TRS, governed mutation contracts, external DT
  coded-tool binding, comprehensive content negotiation and service credential
  propagation. Customer acceptance must cover authentication, installation,
  restart/recovery and live database/workflow behavior.

## OSLC lifecycle extension — 2026-09-15

- Follow-up verified: 29 OSLC tests passed. Individual lifecycle resources support
  explicit JSON, Turtle, RDF/XML and JSON-LD Accept types, representation ETags,
  and Vary: Accept. Collection/shape responses remain JSON.
- Replaced full-manifest disclosure with allowlisted scalar summaries and added
  property definitions for those fields. Full evidence needs a separately governed
  access contract. Registry identifiers are paged in PostgreSQL rather than memory.
- Not complete: per-resource authorization, collection RDF representations, full
  Accept negotiation, lifecycle TRS, approved mutation contracts and DT binding.
  The earlier pending list below is historical; database-side paging and individual
  resource serialization are now implemented, not live interoperability-certified.

- Added authenticated read-only `/oslc/lifecycle` discovery, shapes, paged
  job definitions, job-run evidence and catalog product-version resources.
- Added ETag/If-None-Match conditional reads and catalog discovery link.
- Fixed outbound client support for bounded `ontology:<id>` query identifiers.
- Verification: two focused HTTP/client tests passed.
- Remaining: these JSON endpoints are PMem extensions, not certified OSLC domains.
  RDF negotiation, complete evidence property shapes, database-side pagination,
  per-resource access policy, governed mutation/If-Match contracts, DT client
  bindings, TRS lifecycle events and live interoperability are still open.

## DT agent integration — 2026-09-15

- Added explicit PMem tool allowlists for all 12 ontology roles and a capability
  discovery endpoint. Includes approved-job execution, run quality/lineage evidence,
  product versions and schema-analytics job discovery. Six focused tests pass.
- Export tool now returns a typed base64 artifact instead of attempting JSON parsing.
- These are PMem bindings, not deployment verification. Downstream service credentials,
  external OSLC client bindings and live execution remain pending.

- Implemented approval-gated PMem-to-DT current-plan gateway dispatch, correlated
  PostgreSQL run evidence and protected status retrieval.
- Fixed empty/unknown-agent compatibility false positives. Five focused tests pass.
- Deployment contract: `docs/architecture/DT_AGENT_INTEGRATION.md`.
- Still open: DT coded-tool bindings back to PMem, workflow-specific dispatch,
  authenticated session ownership, gateway provisioning and live acceptance.
  Existing release tasks below remain open; this is not full agent integration.

## Repository restructuring verification — 2026-09-15

- Moved ontology reasoning and taxonomy into `backend/ontology_service/domain`;
  migrated callers in ingestion, OSLC, graph views, semantic workflows and tests.
- Ingestion browser/export adapters reside in `backend/ingestion_service/api`.
- Current service/API catalog: `docs/architecture/SERVICE_CATALOG.md`.
- Removed obsolete monolith documentation, an excluded live report script and
  unused background graph-write code. Existing customer artifacts are retained.
- Verification: focused contracts, ontology runtime and semantic workflow tests:
  28 passed, four skipped. Skips are not conformance evidence.
- Added catalog/deployment consistency and retired-import regression checks.
- Remaining: shared upload/runtime dependencies in `backend/Services` still need
  migration before that folder can be retired; full release acceptance is open.

## Spark installation verification — 2026-09-11

- Verified locally: Spark 4.1.2 with Java 21 and application Python workers;
  deterministic DataFrame count/sort smoke test passes, including four synthetic
  AP242/QIF/ReqIF/PLMXML rows. This is not ontology or source-file conformance.
- Fixed: smoke script provisions its Hadoop environment, validates the helper,
  defaults to supported Spark, disables the unnecessary Spark web UI, asserts
  results and stops its session in a finally block.
- Regression verification: 23 pipeline/readiness tests passed. Live execution
  evidence: `logs/spark-smoke-validation.log` (local runtime log, not committed).
- Still pending: live Neo4j connector read, authenticated UI replay, real PLMXML
  schema/instance end-to-end validation and customer-environment acceptance.
  Spark 4.2 remains outside the configured connector compatibility range.

## MBSE continuation

- Implemented: governed SysML v1 XMI and v2 JSON profiles; ReqIF nested references and hierarchy retention.
- Implemented: configured SysML v2 commit snapshot import with bounded pagination and approved job submission.
- Verification: nine focused MBSE, repository HTTP-mock and governed-import tests passed.
- Pending: live repository acceptance, incremental revision/deletion synchronization, textual SysML/KerML parsing, full port/behavior semantics and typed ReqIF attributes. Do not claim complete language conformance.

## Operating rule

Keep one active delivery item at a time.  Do not start a new P1 item until the
active item has a reproducible verification result.  New requests are added to
the backlog first, then promoted only when their dependency is available.

**Definition of done:** implemented, automated or reproducible verification
recorded, user-visible failure mode is clear, and deployment impact is
documented.  Avoid speculative connectors, new frameworks, and duplicate
services unless they close a listed acceptance gap.

**Active P2/P3:** Customer deployment hardening. The governed batch, speed,
semantic-serving and raw-zone foundations are complete locally. Target
environment identity, TLS, database roles, backups and monitoring are the
remaining release activities.

## Current priority queue

| Priority | Outcome | Status | Acceptance check |
|---|---|---|---|
| P0 | Stable local platform | Complete | Frontend plus services `8010-8019` start; all service health checks pass, all 13 SPA routes render without an error boundary or blank state, and Home/Knowledge Companion interactions pass. |
| P0 | Correct AP242 ontology view | Complete | SMRLv12 EXPRESS plus AP242 BOM and Domain Model XSD conversions preserve RDF classes, properties, hierarchy, domain and range links; the validation API is repeatable and read-only. |
| P1 | Canonical Engineering Information teModel (CEIM) | Complete | CEIM v0.1 RDF, SHACL shapes, deterministic RDF projection, OpenAPI/OData service, and explicit approved graph publication are available. |
| P1 | Standards-to-CEIM mapping | Complete | AP242, QIF, ReqIF, and Teamcenter PLMXML mapping packs normalize with provenance and can use governed publication. The Teamcenter motor EBOM PLMXML acceptance fixture produces 77 CEIM entities and 106 relationships, conforms to CEIM SHACL over 1,201 triples, and retains PLMXML as its source standard. The NIST QIF sample remains a separate validation fixture, not the pipeline identity. |
| P1 | ISO 11179 semantic governance foundation | Complete | The metadata registry owns persistent IDs, namespaces, stewardship, semver, compatibility, replacement, deprecation, lifecycle transitions, and approval evidence. A live local acceptance run created a release, transitioned draft → in_review → approved, resolved it through CEIM, passed SHACL and published a two-node/one-edge graph projection. A draft release negative control was rejected with HTTP 422 before graph publication. |
| P1 | Governed vocabulary curation | Complete | The ontology service owns immutable versioned SKOS drafts with preferred/alternate labels, definitions, hierarchy, external mappings, release provenance, validation evidence, stewardship, controlled review/approval, content-addressed Turtle export, and graph publication only after approval. Live release `engineering-terms-20260904:1.0.0` completed all lifecycle stages and published six graph resources. |
| P1 | Semantic normalization, resolution and PROV-O evidence | Complete | CEIM applies deterministic Unicode/text, ISO-8601 date/time and decimal normalization with retained rule evidence before RDF construction. Exact duplicate entities merge with all source provenance; divergent facts create durable, publication-blocking cases that a steward resolves using `keep_most_complete`, `source_priority`, or `manual`. CEIM RDF emits PROV-O source, mapping, SHACL-validation and approved-publication activity links. |
| P1 | Evidence-grounded knowledge companion | Complete | The companion now uses bounded score-ranked graph retrieval, caps evidence at 12 items, exposes sources with every grounded response, and returns `answerable: false` instead of generating text when no evidence matches. Dependency failure is fail-closed with HTTP 503. The Home chat renders an expandable evidence list. |
| P1 | OSLC-governed agent context retrieval | Complete foundation | Added a read-only `/api/v1/oslc/graph-rag` OpenAPI tool that queries a configured OSLC provider, returns bounded evidence with resource IDs, ontology/revision context, validation status and source links, and is catalogued for the Graph Analyst agent. It has no graph write path or direct database bypass. Live provider acceptance remains an environment prerequisite (`OSLC_REMOTE_BASE_URL`). |
| P1 | OSLC domain/resource profiles | Complete read-only foundation | Added advertised AM, RM, CM and QM discovery profiles with allow-listed resource types, domain predicates, resource-shape properties, canonical property-definition URIs, dictionaries/taxonomies and TRS links. Authoring factories and full RDF content negotiation remain a separate conformance task. |
| P1 | DT Requirements Design interoperability | Complete compatibility foundation | Added a read-only manifest compatibility adapter and `/api/v1/integrations/dt-requirements-design/compatibility` endpoint. External agents remain OSLC-gateway clients; PMem does not import their runtime or permit direct graph/MCP writes. |
| P1 | Governed data-flow jobs with Apache Spark | Complete | The PostgreSQL-backed control plane enforces cross-process single-owner scheduling, post-seed schedules, bounded retry, durable telemetry, immutable input/result/accepted/rejected partition artifacts, deterministic replay, and publication-gated checkpoints. Live acceptance processed the retained NIST QIF source into 416 entities/391 relationships, passed CEIM SHACL over 2,055 triples, published only through the canonical CEIM/graph boundary, and atomically advanced the checkpoint. A repeated finalize call returned the same publication digest without another write. No scheduler, job, or Spark executor writes Neo4j directly. |
| P2 | Batch/speed semantic reconciliation | Complete | Approved source profiles define standards, lateness and retraction policies. The speed API retains idempotent immutable envelopes, quarantines deletion/retraction events for steward review, normalizes ordinary events through the same CEIM mapping and SHACL rules, retains provisional partitions, and can publish only through an explicitly approved CEIM request. No broker, Spark executor or speed adapter writes Neo4j directly. |
| P2 | Immutable raw zone and replayable batch jobs | Complete | Input, result, accepted and rejected partitions are content-addressed and replay lineage is durable. Checkpoint candidates advance atomically only after canonical publication, with idempotent finalize recovery. PostgreSQL-backed policies now govern retention duration, hot/warm/cold/archive tier, legal hold, expiry reporting and approved purge, while a durable tombstone preserves who, when, why and bytes deleted. |
| P2 | Semantic serving completeness | Complete foundation | The graph service exposes bounded, read-only GraphQL and SPARQL projection APIs protected by the deployment auth profile; graph mutations and SPARQL update/SERVICE operations are absent or blocked. Approved HTTPS federation peers are allow-listed by ontology and use an operator-managed token; arbitrary endpoints remain impossible. Evidence-grounded vector retrieval remains a separate product capability requiring an approved corpus and embedding policy. |
| P2 | Distributed semantic analytics | Foundation complete | Governed baseline jobs `rdf-quality-statistics`, `rdf-deduplicate-serialize`, and `document-evidence-enrichment` are provisioned idempotently through the deployment lifecycle. They provide Spark-based lexical quality, deterministic deduplication/serialization, and document evidence proposals with durable accepted/rejected artifacts and no graph write. Distributed OWL reasoning/rule materialization and semantic ML still require concrete governed product use cases and remain pending. |
| P3 | Speed-path event integration | Complete foundation | A generic OpenAPI event gateway is available with source approval, owner, standard allowlist, maximum lateness, retraction policy, 1 MiB envelope bound, immutable capture, event-id idempotency, CEIM/SHACL reconciliation and canonical publication approval. A customer may configure CDC or a message-bus connector only after selecting its source, throughput and latency SLO. |
| P2 | Customer production hardening | Planned | APIM/Entra/TLS, least-privilege database roles, backups, observability and release preflight pass in the target environment. |
| P3 | Digital twin closed loop | Deferred | Telemetry ingestion, synchronization policy, command authority and a verified feedback workflow still require a customer safety case; this cannot be safely inferred from generic event transport. |

## Next focused increment

1. Run customer production hardening in the target identity, TLS, database-role, backup and monitoring environment.
2. Configure a named source, volume/latency SLO and connector deployment for any CDC/message-bus speed feed.
3. Select a governed rule-materialization, semantic-ML or vector-retrieval data product before adding those product-specific capabilities.

## Verification record

- **2026-09-04 — normalization, conflict and PROV-O acceptance:** added the
  common CEIM normalizer and durable entity-resolution cases. A live QIF
  projection converted whitespace/Unicode text, an ISO timestamp and a decimal
  value while retaining the applied rules; generated Turtle contained
  `prov:wasDerivedFrom` and `prov:Activity`. A separate conflicting QIF Part
  batch was correctly blocked, stored as case
  `9800942b-0db8-41e5-b6e2-684d28254121`, manually resolved by the local
  steward, and replayed into one non-blocking canonical entity. No test fact
  was published to the graph. Focused CEIM/pipeline tests passed **37 tests**;
  the complete backend suite passed **343 tests** with 5 environment-dependent
  skips.

- **2026-09-04 — P2/P3 speed and federation foundation acceptance:** added a
  PostgreSQL-backed allow-listed federation-peer registry. A peer must use
  HTTPS, be separately approved, restrict ontologies and use an
  operator-managed token; forwarded queries reapply the bounded SELECT/ASK
  rule and reject `SERVICE`. Added the generic speed-path OpenAPI boundary:
  approved source profile, standard allowlist, lateness/retraction policy,
  immutable one-megabyte event envelope, event-id idempotency, CEIM mapping,
  SHACL reconciliation and explicit CEIM-only publication. Live QIF event
  `qif-speed-live-20260904-event-1` captured artifact
  `sha256:4534b3591fdf99b0c4e06119a05df0a7e09c9bfe171ace5dfef1e57b4baedf22`,
  reconciled as SHACL-conformant provisional partition
  `sha256:b9b041102cecb5295e2cf88a57d7e6c2c1e6866af57e4fa2c112b7410b2fec5a`,
  and correctly remained un-published pending canonical approval. The focused
  speed/federation suite passed **25 tests**; the complete backend suite passed
  **339 tests** with 5 environment-dependent skips.

- **2026-09-04 — governed Spark RDF serialization acceptance:** added the
  versioned `rdf-deduplicate-serialize` job contract. It reads only an immutable
  N-Triples artifact, applies bounded Spark lexical validation, distributed
  deduplication and deterministic ordering, then retains accepted and rejected
  partitions without graph publication. Live run
  `793c40af-9aa9-469e-ba35-eb1e5b83aa84` examined four lines, accepted three,
  produced two distinct sorted triples, identified one duplicate and one
  malformed line, and retained canonical artifact
  `sha256:5954190023ffae4763173fe66c8d6231c8fcaeea45b956aa60a1e0556845ecee`
  plus rejected evidence
  `sha256:e14e1d00802f638609c67e1cd18d69a0d4900215e64c2988756065dbdb8112ff`.
  The focused pipeline/serving/governance suite passed **36 tests**, the full
  backend regression passed **336 tests** with 5 environment-dependent skips,
  and the frontend production build completed. The build retains a non-blocking
  warning for two large JavaScript chunks; bundle splitting is tracked as UI
  performance work rather than a semantic-pipeline correctness issue.

- **2026-09-04 — raw-zone retention and semantic-query acceptance:** added
  PostgreSQL-backed artifact policies for retention duration, storage tier,
  legal hold, expiry reporting and approved purge. Purge verifies the exact
  content-addressed path and retains a durable tombstone after bytes are
  deleted. The retained NIST QIF source was registered in the archive tier for
  3,650 days under legal hold and correctly excluded from due-for-purge results;
  the automated lifecycle test verifies hold rejection, hold release, expiry,
  deletion and three audit events using an isolated artifact. The graph service
  now enforces the deployment auth profile on bounded read-only GraphQL and
  SPARQL. Live SPARQL returned six rows from the governed SKOS ontology and
  GraphQL returned its bounded overview; mutation keywords and federated
  `SERVICE` are fail-closed. The focused backend suite passed **36 tests** after
  adding governed deterministic N-Triples serialization.

- **2026-09-04 — P1 vocabulary and companion acceptance:** added immutable,
  versioned SKOS curation with integrity validation, steward provenance,
  controlled `draft → in_review → approved → published` transitions and
  content-addressed Turtle publication. Live release
  `engineering-terms-20260904:1.0.0` published artifact
  `sha256:45f690358eda327f5153f79a6a1a76cf3c6a887351ce05671e48dffa33775e30`
  and six graph resources. Replaced the companion's canned acknowledgement
  with bounded parameterized graph search, ranked exact matches, a 12-item
  evidence ceiling, source references, and fail-closed no-evidence/dependency
  behavior. Live Product/Part retrieval returned evidence from CEIM, QIF,
  AP242 and the governed SKOS release; a non-existent query returned
  `answerable: false` with zero evidence. Focused backend tests passed and the
  frontend production build completed. The isolated Siemens IX/JSDOM chat
  test remains affected by the existing Node 24 custom-element heap issue.

- **2026-09-04 — canonical publication/checkpoint acceptance:** added the
  idempotent `POST /api/v1/pipeline/jobs/runs/{run_id}/publish` hand-off. It
  resolves only an accepted semantic partition, calls the CEIM publication
  API, and advances the checkpoint only after the canonical graph boundary
  returns `published`. Replayed run
  `71face53-d9c4-42b7-b754-1715f1fd9015` published ontology
  `qif-pipeline-acceptance` against the approved semantic release, then
  advanced to the retained source's `validated` checkpoint. A repeated call
  returned the same publication digest
  `sha256:4ab1f545e1b008be890d5b5684bc2c39c19f2fa4af77debbd85a91b639911848`
  with no second mutation, and the pipeline log contained no errors. The
  final focused suite passed **27 tests** and the full backend regression
  suite passed **326 tests** with 5 environment-dependent skips.

- **2026-09-04 — retained real-QIF pipeline acceptance:** the CEIM QIF and
  ReqIF adapters now retain uploaded source bytes and return the immutable
  source artifact ID plus an explicit `normalized-ceim-v1` representation.
  This also fixed a double-normalization mismatch between adapters and Spark.
  The supplied NIST QIF sample was retained as
  `sha256:c92f4755bf84f30ed0e3963ece2e1ca7534b2f83c2e02a27530a217c2c423693`,
  extracted into 416 entities and 391 relationships with zero unresolved
  references, and executed as approved run
  `867a9399-1139-4038-ab1c-ab9f480de4ac`. SHACL conformed over 2,055 triples;
  the accepted partition is content-addressed and the checkpoint remains
  gated as `awaiting_approved_publication`. The focused CEIM/pipeline suite
  passed **26 tests**.

- **2026-09-04 — governed scheduler and partition acceptance:** added a
  PostgreSQL session advisory lock so multiple API workers cannot start the
  same due schedule concurrently. Jobs now retain content-addressed accepted
  and rejected partitions, while `next_checkpoint` is recorded only as an
  `awaiting_approved_publication` candidate. The focused suite passed **15
  tests** and the full backend suite passed **325 tests** with 5
  environment-dependent skips. Live acceptance approved and seeded
  `scheduler-acceptance-20260904`, then observed supervisor-owned run
  `9ed5ccbd-5a37-4905-ad3a-d2221457da34` replay seed
  `43938605-11bd-44de-8321-918756fc9d22`; both resolved to the same immutable
  accepted partition. The recurring test schedule was disabled after the
  check and scheduler health reported one run with no error.

- **2026-09-04 — data-job monitoring and scheduler correction:** corrected the
  Data Flow client to use the owned `/api/v1/pipeline/*` routes, added
  post-seed schedule configuration, execution authorization, replay lineage,
  durable result artifacts, scheduler health, and cross-job telemetry counts.
  Focused backend and frontend-contract tests passed (**14 tests**), the Vite
  production build passed, and live health reported Spark enabled plus the
  scheduler enabled/running. No configured job exists yet, so a real scheduled
  source-run acceptance remains open.

- **2026-09-03 — live ISO 11179 registry-to-graph acceptance:** created a
  uniquely named semantic release in the running metadata registry, recorded
  its `draft → in_review → approved` lifecycle with three audit events, then
  published a SHACL-conformant QIF CEIM projection through the CEIM and graph
  services. The graph projection returned two resources and one relationship.
  A distinct draft release was submitted as an `approved` reference and CEIM
  rejected it with HTTP 422 before graph publication. The CEIM client was also
  corrected to accept either host-root or `/api/v1` graph-service discovery
  URLs, preventing a recovery-time double-prefix 404.

- **2026-09-02 — Spark API foundation:** `backend/tests/test_data_pipeline_service.py`,
  `backend/tests/test_ceim_service.py`, and `backend/tests/test_ceim_contract.py`
  passed (**12 tests**). The live local `POST /api/v1/pipeline/jobs/transform`
  test initialized Spark, accepted two records, rejected one quality-failed
  record, and returned chart data; `GET /api/v1/pipeline/telemetry` reported
  the run. This verifies the service foundation only, not the queued scheduled
  CEIM jobs.
- **2026-09-02 — reference-architecture alignment review:** the supplied
  Semantic Digital Engineering Reference Architecture was reviewed across its
  industrial data platform, semantic pipeline, CEIM, ontology, graph,
  semantic services, batch/event, and AI layers. The verified mapping and
  production boundaries are recorded in `docs/SEMANTIC_INTEGRATION_LAMBDA_PIPELINE.md`.
  No unimplemented speed path, GraphQL/SPARQL layer, or closed-loop telemetry
  capability is marked complete.
- **2026-09-02 — enterprise Lambda topology baseline:** the accepted source →
  connector → parser → batch/speed → serving → consumer model, with its
  cross-cutting semantic control plane, is now recorded in
  `docs/SEMANTIC_INTEGRATION_LAMBDA_PIPELINE.md`. The tracker explicitly keeps
  raw-zone/replay, semantic serving, and speed integration as pending work;
  it does not treat the Spark preview endpoint as a full Lambda pipeline.
- **2026-09-02 — QIF CEIM mapping fixture:** the strict QIF adapter extracts
  declared Part, InspectionPlan and MeasurementResults records from
  `data/ceim/fixtures/qif-inspection-instance.xml`, applies the governed
  `qif-core` mapping pack, creates the declared relationship, and passes CEIM
  SHACL validation. The isolated HTTP OpenAPI smoke test documented the
  adapter route and returned 1 part, 1 inspection plan, 1 measurement result,
  and 1 relationship. This is representative-fixture evidence, not a
  substitute for a customer QIF export.
- **2026-09-02 — QIF XSD validation boundary:** the CEIM service now exposes
  `POST /api/v1/ceim/adapters/qif/validate`, which compiles the bundled QIF
  3.0 document schema using its local XML Signature dependency and validates
  an instance without network access. The isolated HTTP smoke test reported
  `conforms: true` for `qif-minimal-valid.xml`; the semantic-mapping fixture
  remains separately and intentionally non-schema-valid.
- **2026-09-03 — NIST AP242 QIF sample mapping closure:**
  `nist_ftc_08_asme1_ap242-1.qif` passes the bundled QIF 3.0 document XSD and
  the isolated OpenAPI validation/normalization routes. The governed `qif-core`
  mapping now yields 416 CEIM entities and 391 relationships: 1 part, 46
  features, 74 characteristics, 11 datums, 9 datum-reference frames, 54 PMI
  annotations, and 221 geometry bodies, with zero unresolved references and a
  passing CEIM SHACL projection. This is body-level geometry topology scope;
  detailed geometric primitives remain in the immutable source artifact rather
  than being silently promoted to unsupported CEIM assertions.
- **2026-09-03 — official QIF validation-tool audit:** the official
  `QualityInformationFramework/qif-validation-tools` v1.0 schema checker
  succeeded on the NIST sample using a local XML Signature schema reference.
  Its XSLT report contained 0 format findings, 0 semantic findings, and 174
  quality findings: 170 `G-FA-IT` inconsistent-face-on-surface and 4
  `G-SH-FR` free-edge reports. The evidence is retained as a source-quality
  gate; it does not overwrite, repair, or reclassify the source model.
- **2026-09-03 — ISO 11179 registry contract increment:** the existing
  metadata registry was extended rather than duplicated. Semantic assets now
  record persistent identity, namespace/prefix, semantic version, compatibility,
  replacement, deprecation reason, and approval evidence. Lifecycle transitions
  require an actor; approval/deprecation/retirement require evidence, and an
  approved release can re-enter review. The contract and deployment boundary are
  documented in `docs/SEMANTIC_GOVERNANCE_CONTRACT.md`; focused regression tests
  verify field validation and audit-event evidence.
- **2026-09-03 — governed manifest linkage:** CEIM graph publication and data
  product validation now require an approved semantic asset ID and semantic
  version. Data-product package/catalog manifests retain those release
  references. The remaining acceptance is an online registry lookup and
  configured graph-registry lifecycle smoke test, so a caller cannot be treated
  as a registry authority merely because it supplied an `approved` label.
- **2026-09-03 — authoritative release-resolution gate:** publication and data
  product packaging now resolve each semantic release through the metadata
  registry. A missing registry, unknown asset, version mismatch, or non-approved
  lifecycle state blocks the mutation. The registry URL defaults to the local
  ontology service and may be set with `SEMANTIC_REGISTRY_URL` for deployment.

## Weekly review

- Close, defer, or split every active item; do not leave ambiguous work in progress.
- Promote only one P1 item after P0 is green.
- Record a test command, result, owner, and deployment impact for each closed item.
- Treat UI changes as a separate work item after backend contracts are stable.
