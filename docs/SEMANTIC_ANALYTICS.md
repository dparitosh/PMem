# Semantic records for reusable analytics

Data Products now starts with registered RDF data from the Data Catalog or Metadata Registry. XML/XSD preparation remains an alternative import path. Users select a source, then its prepared dataset, namespace, business entity type and properties. Technical artifact identifiers are resolved from registered references.

## Storage and identity

Migration `infra/postgres/migrations/015_semantic_datasets.sql` creates shared, versioned tables:

| Table | Responsibility |
|---|---|
| `depo_semantic_datasets` | Source/version, immutable artifact digest, projection receipt and validation scope |
| `depo_semantic_namespaces` | Namespace URIs and prefix aliases per dataset |
| `depo_semantic_terms` | Entity/vocabulary identity, label, description and declared types |
| `depo_semantic_values` | Property values, references, datatypes, languages and finite numeric values |

Full IRIs identify records. Prefixes are display aliases. Repeated property values remain separate; missing values are not converted to zero. Ontology classes and properties do not count as business instances. Snapshots are idempotent and transactionally written with lease fences; a retry does not duplicate rows. Shared indexed tables avoid a new physical table for each namespace or property.

## Governed worker sequence

1. Register a retained RDF artifact reference on a versioned Catalog product or Metadata Registry asset. A live graph requires a registered RDF snapshot; this feature does not automatically export the live graph.
2. Create a data-job definition through `POST /api/v1/pipeline/jobs/definitions`: `job_type=rdf-semantic-materialize`, `quality_profile=semantic-core-v1`, plus `job_id`, `name` and semantic `version`. The service resolves the owner. Creation produces a draft. Review and approve it through the existing Data Flow governance controls.
3. In Data Products, select the registered source and approved preparation workflow. Run it using connected execution access. Follow its retained result in Data Flow.
4. Refresh registered data and select the prepared dataset. Select namespace, business entity type and analysis properties.
5. Run an approved `semantic-dataset-analysis` definition, also using `semantic-core-v1`. The worker retains analysis output and a draft product with source lineage. Product publication still requires its approved semantic release and steward authorization.

Supported initial strategies: completeness, property frequencies, numeric count/minimum/maximum/average/standard deviation, Pearson correlation, and bounded dimension previews. They use deployment-owned SQL; users cannot submit SQL or Python. Correlation does not establish causation. Numeric strategies reject repeated/non-numeric values and conflicting property-level declared units. Missing unit metadata remains unknown.

This supplies reusable records and initial measures, not a complete dimensional warehouse. Business grain, cross-entity joins, unit normalization, slowly changing dimensions, domain KPI formulas and arbitrary data-science algorithms require separately reviewed models/handlers. Dimension previews are not published data marts.

## Validation and limits

RDFLib parses RDF. Optional registered SHACL-core rules are evaluated through Semantica using `shape_source_id` and `shape_artifact_id` worker inputs. Without rules the receipt explicitly says `not_assessed`. SHACL conformance does not establish full OWL-DL consistency or target coverage. Executable SHACL rules/imports are blocked.

Initial input limits: 25 MiB, 250,000 triples and indexed IRIs of 800 UTF-8 bytes. Supply partitions or a reviewed identifier mapping for larger inputs. Analyses use read-only repeatable-read transactions with statement timeouts and bounded output. Frequency/dimension previews are explicitly marked when limited. No model service is needed for these deterministic strategies.

## Verification

`backend/tests/test_semantic_datasets.py` checks identity, repeated/language values, numeric typing, artifact ownership and unsafe parsing inputs. `backend/tests/test_semantic_datasets_postgres.py` exercises migration, actual COPY writes, retry idempotency, dimension values, numeric guards and failure rollback in `depo_acceptance_test`; its disposable schema is removed. Frontend tests exercise catalog selection, approved worker submission, duplicate-click protection and unavailable sources.

## Configuration baselines and tracked changes

New preparations automatically freeze their declared input selections in PostgreSQL `depo_registry`, namespace `semantic_configurations`. The digest identifies an immutable baseline; a change to any selected artifact or registered source revision produces a different configuration. Creation does **not** grant release approval. Projection receipts and analysis results retain this configuration identity. Historical baseline replay uses its captured version selections, verifies retained artifacts and never silently resolves to today's latest version.

Worker inputs can include `configuration_inputs`: up to 19 dependency selections with `role` (`ontology`, `mappings`, `kpi` or `shapes`), `source_id` and `artifact_id`. All references must belong to registered Catalog/Metadata sources. One SHACL rule artifact can be evaluated during preparation. Other dependency roles record reproducibility context; selecting a KPI artifact does not automatically execute its formula or apply ontology entailments. Dependency discovery is not automatic. The primary source is frozen from the source selected in the UI.

To reuse a baseline, supply its `configuration_id` with its original source/artifact. The processing API also accepts a deployment-local `Configuration-Context` URI `/oslc/lifecycle/analytics-baselines/{configuration_id}` or its absolute `OSLC_BASE_URL` equivalent. Foreign origins and conflicting header/body selections are rejected; no supplied URL is fetched. Analysis/review requests must reference a dataset from that configuration. The CORS allowlist includes this header.

Baseline summaries are available through the existing read-only OSLC lifecycle extension. Grant `analytics-baselines:*` or the specific identifier through `OSLC_LIFECYCLE_READ_GRANTS` for authorized OSLC readers. The pipeline read API exposes the baseline at `GET /api/v1/pipeline/semantic/configurations/{configuration_id}`. These resources are **PMem extensions**, not a claim of a complete OSLC Configuration Management provider. Stream creation, merges, global configuration contributions and external-provider configuration negotiation are not implemented here.

### Review and refresh sequence

1. Prepare and approve a `semantic-source-review` job definition using quality profile `semantic-core-v1`. The UI can prepare its draft; approval remains in Data Flow.
2. Select a prepared dataset in Data Products and choose **Check source changes and refresh needs**. The worker reconciles every declared registered input revision and artifact, and reads one bounded page of the existing local TRS feed. The UI displays the retained assessment.
3. To repeat checks, schedule the retained review run through the existing Data Flow scheduler. This is a scheduled consumer, not a new broker or an automatically enabled subscription.
4. Changed selections or matching catalog-resource/reset events produce `refresh_required`. Missing/unavailable TRS coverage produces `review_required`. Known refresh requirements persist across subsequent empty pages. Checkpoints and findings are stored together in `semantic_refresh_reviews`; a lost execution lease cannot advance the checkpoint.
5. Inspect the changed sources, select current versions and prepare a new snapshot through the approved workflow. Review and publish separately. Existing published results are retained throughout; neither a TRS event nor a baseline grants approval or replays publication.

TRS coverage is partial: catalog lifecycle resource paths and graph-reset notifications are matched; Metadata Registry revisions are reconciled directly. This does not trace every graph-node change to every KPI. Retention gaps, restored counters and unavailable feeds are explicitly reported and never treated as proof of freshness. A gap remains unresolved pending operator review; this feature does not silently acknowledge or clear it. Large feeds need multiple scheduled review executions to catch up.

Baseline creation and its pending TRS notification are retained in one registry transaction. The review worker retries that notification; delivery is at least once and duplicate notifications cannot replay graph writes. No Neo4j projections or published package records are modified by the assessment.

### Replay and execution status safeguards

The preparation baseline is resolved before the canonical execution input is retained and queued. Both synchronous and leased-worker execution reload that retained input, so a later Metadata Registry revision does not select a different baseline on retry. Explicit replay still requires current execution authorization; historical input selection does not grant a publication approval.

Legacy completed runs may recover their baseline binding from a retained output receipt. A legacy preparation with no verified binding is rejected for replay; inspect its sources and submit a new preparation instead. Published products and original artifacts remain retained.

A successful source review has execution status `completed` and a separate `assessment_status` such as `refresh_required` or `review_required`. Draft manifests retain configuration ID/context, and analysis source lineage carries them into packaging inputs. UI callbacks from an older session cannot overwrite current error feedback; late server-issued run receipts remain recoverable after reconnect or navigation.

New baselines capture the TRS head **before** resolving selected sources. The first review starts at that position, so older graph-reset events do not invalidate a newly prepared snapshot. Events occurring during or after preparation remain eligible for assessment. Older baselines without a captured position remain explicitly uncertain; existing refresh findings are not silently cleared.
