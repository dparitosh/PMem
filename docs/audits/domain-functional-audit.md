# Domain and functional audit — 2026-10-02

> Dated audit record: use [the current audit index](README.md) for latest validation and acceptance status. Findings and test counts below belong to their recorded review; they are not a current release certificate.

Scope: static code tracing across navigation, ingestion profiles, CEIM, ontology agents, Semantic Bridge, job handlers, product/catalog workflows, reports and PostgreSQL migrations. Focused reproductions executed actual isolated functions with mocked RDF primitives or controlled XML. No live customer workflow certification is claimed.

## Domain coverage

| Domain/workflow | Implemented boundary | Functional limits |
|---|---|---|
| Engineering ingestion | Native parsers and configurable XML/JSON/CSV/XLSX profiles; immutable artifacts | Parsing/inspection is not complete standards conformance or universal semantic mapping. Generic XML currently loses leaf attributes. |
| Canonical engineering model | CEIM 0.1 defines 18 entity and 15 relationship types; mapping digests, normalization, RDF, SHACL and resolution cases | Entity identity lacks source-system/tenant scope; model is a canonical subset, not complete PLM/MBSE/manufacturing standards coverage. |
| Standards mapping | Seven packs: AP242, PLMXML, QIF, ReqIF, SysML v1/v2, unstructured evidence | No dedicated CEIM packs found for AP239, B2MML, JEP30 or 3DEXPERIENCE. Other parsers/ontologies do not establish these publication workflows. |
| Ontology Junction | Taxonomy, vocabulary, alignment, reasoning and governance surfaces | Domain acceptance requires demonstrated preview/review/approval flows; deterministic alignment mainly uses exact term matching, not semantic equivalence proof. |
| Ontology agents | Evidence inspection, candidate plans and optional LLM suggestions | LLM suggestions are review-only and do not constitute autonomous approved ontology learning. |
| Semantic Bridge | Saved candidates, eligibility checks, approved selection, snapshot staleness, locked publication and graph receipts | Requires a representative customer dataset and ontology to establish useful linking accuracy and traceability. |
| Data jobs and quality | Ten trusted handlers, durable runs, lease worker, quality/provenance outputs | Schema analytics aggregation still invokes Spark; Spark-disabled is not equivalent to every job being executable. |
| Graph visualization | Overview/projection/traversal/search and contextual graph surfaces | Views are bounded. Graph counts and reports are not whole-enterprise warehouse measures. |
| Metadata Registry | Governance assets, versions and lifecycle plus ontology dictionary | This page is not the complete Data Catalog product-discovery workflow; separate API product namespaces exist. |
| Data products/catalog | Versioned artifacts, manifests, approvals and registration retries | Publication/idempotency/package reuse still needs concurrent immutable-content enforcement; earlier product audit details the gaps. |
| Reports/analytics | Current graph/context reports and pipeline telemetry | Dedicated populated warehouse facts, dimensions and business KPI calculation/load jobs are absent. |
| OSLC/integration | Resource/service contracts and optional remote retrieval | Remote connectors and vendor-specific domain round trips require customer configuration and acceptance fixtures. |

## Confirmed correctness findings

### P1: incorrect engineering type from stale provenance

`backend/ceim/contract.py`, `CEIMContract.to_rdf`: source-standard/type are read before the current entity's provenance is assigned. The variable initially contains the last normalized entity's provenance and subsequently the preceding entity's provenance. A controlled QIF CharacteristicDefinition + AP242 geometric_tolerance input reproduced swapped Bill-of-Characteristics classes using the actual method with mocked RDF primitives.

Fix: bind each entity's provenance at the top of its RDF loop before any standard-specific type mapping; regression-test mixed-standard entities and input order.

### P1: Data Flow publication cannot satisfy the release gate

`frontend/src/pages/DataFlowPage.js` calls `publishRun(run.run_id, {}, approval())`. Pipeline publication passes the missing semantic_release onward; `backend/depo_platform/semantic_registry.py` rejects anything that is not an approved asset/version reference. The page also reuses a single execution/publish key input even though configured governance/execution/publication credentials are distinct.

Fix: select an approved semantic release in the UI, submit its asset_id/version/lifecycle_status, and supply the credential for the specific action. Do not weaken backend approval to accommodate an incomplete UI.

### P1 for measurement ingestion: leaf XML attributes are discarded

`backend/ingestion_service/profiles.py`, `_xml_record`: a leaf child becomes its text only; attributes are retained only when recursion occurs. Controlled input `<Measurement><Value unit="mm" uncertainty="0.1">3.2</Value></Measurement>` produced only `{'Value': '3.2'}`. Namespace stripping can also collapse distinct attribute/element names.

Fix: retain structured leaf attributes/text and qualified names under a versioned extraction contract. Update profile field access and fixtures together so existing mappings are not silently broken.

### P1 when integrating multiple source systems: canonical identities collide

`backend/ceim/contract.py`, `normalize_entity` creates IDs from standard + source_id only. Two systems using the same standard and local ID produce the same CEIM ID and RDF URI; publication into the same ontology uses MERGE on that resource identity. Separate batches can therefore overwrite/merge unrelated facts. Within-batch resolution alone cannot prevent cross-batch collisions.

Fix: include stable tenant/project/source-system identity in entity and relationship IDs and provenance, with an explicit compatibility/migration plan for existing graph identities. Confirm whether any cross-system deduplication is intentional and approved.

## Completeness and integration priorities

1. Repair the three reproducible correctness failures above, then define and migrate scoped identity.
2. Establish one end-to-end customer digital thread: requirement -> part/revision -> feature/characteristic -> measurement/test -> evidence -> approved semantic publication -> catalog product -> report. Trace source artifact, mapping release, approver and job run throughout.
3. Add missing standards mapping packs and representative fixtures only for the required customer standards. Document unsupported source types explicitly.
4. Complete approved-release and action-specific credential selection in job publication UI.
5. Implement dimensional analytics with explicit fact grain, revision/time/unit/source dimensions, idempotent loads and reconciliation. Ontology counts must remain distinct from business KPIs.
6. Validate metadata/catalog/product lifecycle consistency and cross-process publication behavior.
7. Document agent limits: proposals and retrieval are supported; autonomous semantic correctness and self-learning are not established by current code.

## Acceptance evidence needed

Use representative QIF/AP242/ReqIF/PLMXML/SysML files; assert units, tolerances, IDs, namespace handling, revisions and source lineage. Validate malformed/optional/repeated structures, conflicting identities, approval rejection, changed-source previews, expired credentials, worker restarts, replay and duplicate publication. Check the resulting graph links and catalog manifests against expected business assertions. Run both gateway and local modes. Full standards compliance requires broader domain fixtures and validation than this source audit.

No application fixes or new schema migrations were applied during this audit. The preceding pushed release does not include fixes for these newly identified domain defects. See domain-functional-fixes.md for the subsequent corrections included with this audit.
