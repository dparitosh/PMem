# DEPO demo user guide

Current: 2 November 2026. Companion: [editable workflow deck](../deliverables/DEPO-Workflow-Audited.pptx). This replaces the older customer demo sequence. Dated audits remain historical evidence.

## Demo objective and preparation

**Business story:** bring together product specifications, engineering models and design records; inspect their meaning; review proposed connections; find evidence; prepare reusable analytics and release it through its owning approval workflow. The induction motor is sample data, not a product-specific application rule.

Allow 30–40 minutes: orientation (3), sources/meaning (8), connections (8), decision support (6), analytics/governance (8). Rehearse conversions and prepare retained results before presenting. Never reset customer data for a demo.

From an already installed release's root, the operator runs:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\manage-depo.ps1 -Action Start -EnvFile .\.env.local
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\diagnose-depo.ps1 -Phase Runtime -EnvFile .\.env.local
```

Open the frontend URL printed by the launcher. In **Admin → API access**, connect registered services. Connect execution/approval scopes for the intended demo; maintenance access is unnecessary and is not a substitute for those scopes. Check API and worker readiness. Spark is needed only for configured Spark jobs. Without an available LLM, demonstrate deterministic retrieval/SQL and retained status; defer live model planning and generation acceptance. Keep credentials out of slides, screenshots and chat.

Record the selected source, ontology version, completed run and reviewer before presenting. The local rehearsal reviewer is **paritosh** where authorized; a customer names its own accountable owner. Counts below are historical examples, not expected results for every import.

### Local sample inputs

Root: `D:\GenAI_Projects\SPLM_Folder`. These are local rehearsal inputs, not files bundled in every customer release. Choose one revision; compare identities/digests where folders contain duplicates.

| Input under that root | Workflow | Business example |
|---|---|---|
| `plmxml_individual\000098-Induction Motor System Req Specification.xml` | Import instance graph | Specification records and source references |
| `plmxml_individual\000138_A_4-JuicePurification-InductionMotor.xml` | Import instance graph | Product/assembly context where supplied |
| `MBD3D_BO\DomainModel.xsd` plus referenced companions | Create ontology | AP242 vocabulary |
| Intended root XSD and companions in `SPLMXML` | Create ontology; select together | One grouped PLMXML ontology |
| `XMI\SugarPlantMBSE.xmi` | Create ontology | MBSE concepts and recorded relationships |
| A small supported file in `step_files`, e.g. Rotor Shaft Key | Engineering instance conversion | Retained Data Flow evidence, then separate publication |

## 1. Import business records

1. Open **Import → Import instance graph**, select the specification XML and start once.
2. Follow parsing, validation and loading. Inspect processing details and retain the request/task ID if it fails.
3. Open the resulting graph only when the load/publication evidence supports it. STEP conversion may link to **Data Flow** for separate publication; conversion success alone is not graph publication.
4. Add the product/assembly XML. Show its source filename and retained task.

**Say:** “Every recorded business object has a source we can inspect.” Show terminal task state, scoped counts and the publication receipt where publication occurred. Refresh does not cancel a worker. After a lost acknowledgement, inspect retained status before submitting again.

## 2. Register and publish meaning

1. In **Import → Create ontology**, select the root XSD and companions together. Review the ontology name and prefix. The grouped set should appear as one schema-set entry.
2. If dependencies are requested, select their containing folder and resolve/retry the same upload. Public schema retrieval is bounded and may be unavailable offline. XSD dependencies and OWL imports are different operations.
3. Review retained validation and the exact version, then use its authorized approval/publication controls.
4. In **Ontology Junction → Taxonomy / OWL**, choose that version. Use list or hierarchy for different questions; select a term and show its detail above the classes. Same labels may identify different IRIs. Anonymous OWL restrictions are not extra named parent classes.
5. In **Metadata Registry**, filter the dictionary and inspect definition, ownership and source revision.

**Say:** “Registration makes a definition discoverable; publication makes its checked graph projection available.” A registry name does not prove graph publication. If Home reports **RDF projection not published for this scope**, check the selected version's publication status, then refresh after publication.

**Counts:** declared named individuals count explicit `owl:NamedIndividual` declarations, not every imported record. Zero declared annotation properties does not mean labels/descriptions are absent.

**Inference Workbench:** distinguish Semantica structural checks from HermiT OWL-DL evidence for an exact artifact. The bundled engine is tested, but external OSLC, Dublin Core, SKOS and SHACL imports without a supported local closure remain **unknown / unresolved imports**. Do not remove imports or claim full consistency from structural validation.

## 3. Link instances and review two-ontology merge

1. In **Semantic Bridge**, select the imported task and target ontology version; inspect source/target details.
2. The **Governor** prepares proposals; the **Steward** assesses the retained candidates using compatibility, ambiguity, confidence and current evidence.
3. Use automated mapping only when its displayed policy/publication authorization is intended. Starting it can authorize policy-approved publication; it is not merely an explanation action.
4. Review grouped candidates, decisions and **View** evidence. Keep unresolved alternatives held. A similarity score is not semantic correctness.
5. Inspect publication receipt and held results. Optional ontology agent review explains alignment; it does not itself publish mappings.

**Example:** a local specification-to-PLMXML acceptance run published 7 mappings and held 50 proposals. Recompute for the current versions; do not promise these counts.

For **two-ontology merge**, choose both versions, prepare/save the plan, inspect assessment/reasoning, then use its owning approval/publication controls. A union with zero identity consolidations does not establish class equivalence. After reload, resume the saved plan and verify its receipt before any repeat write. **Change Control** aggregates evidence; it is not a complete unified CR/CO authoring engine.

## 4. Explore context and make a decision

1. **Graph Explorer → Overview:** show source/ontology groups; counts describe the visible bounded slice.
2. **Ontology:** select a published version and inspect classes/properties.
3. **Processes:** choose an imported process scope; a registry definition is not proof of loaded process instances.
4. **Instances:** search `induction motor` or `Rotor Shaft Key`, select the intended business identity, then expand recorded neighbors. Search matches are not all equivalent objects.
5. **Where Used:** inspect recorded dependency paths for that selected object.
6. **Recommendations:** demonstrate **Change Impact**, **Similar Parts**, and **Process Context** separately. Reuse the selected identity and scope when names are ambiguous. Direct graph analysis does not need an LLM; agent investigation requires a capable provider.

**Ask:** “Which recorded requirements refer to this assembly?” “What dependants need review if this part changes?” “Which parts have comparable properties and units?”

**Expected:** business names/descriptions, property values, source links, scoped paths and missing-evidence warnings. Unknown revisions, effectivity, units or PMI ownership stay unknown. Missing paths do not establish absence of impact.

## 5. Companion and memory

In **Home → Knowledge Companion**, select the business scope and ask:

> What requirement specifications are associated with induction motor? Show names, descriptions and recorded source references.

Follow with:

> Which of those have a recorded link to a product or assembly?

Compare against source records and ontology terms. A schema-definition list instead of business specifications fails the demonstration. Do not invent detail to conceal sparse evidence.

| Memory | Demonstration | What it establishes |
|---|---|---|
| Short-term | Ask a follow-up using “those” in the same scope | Subject/context retained for retrieval |
| Contextual history | Reload retained history, then retrieve fresh evidence | Recovery; an old restored answer alone is not current verification |
| Long-term reviewed lesson | For a receipted mapping: record outcome → prepare lesson → approve → reload support for the same revision | Approved scoped advisory recall, not model training or automatic publication |

Use Admin **Check model configuration**, **Verify model capabilities**, and **Check agent memory** before this segment. Optional graph memory needs configuration and populated evidence. If there are no approved lessons, show that state; do not claim successful recall. Keep unavailable-model fallback separate from natural-language answer acceptance.

## 6. Prepare analytics and release a data product

Explain: **choose available data → prepare it → review an analysis → release it → find it in the catalog**. Business users select registered sources; they should not discover artifact IDs manually.

1. In **Data Catalog** or **Metadata Registry**, select a source/version with retained RDF evidence. A vocabulary-only source may have no business instances.
2. In **Data Products**, select that source and an approved preparation workflow. Existing `rdf-semantic-materialize` prepares versioned namespace/entity/property records with lineage. Follow its worker result in **Data Flow**, refresh and choose the prepared dataset.
3. Select namespace, business entity type and properties. Approved `semantic-dataset-analysis` supports completeness, frequencies, bounded dimension previews and supported numeric statistics/correlation. Correlation does not establish causation.
4. For a reviewed dimensional model, use `semantic-business-mart`. Inspect supported product portfolio, classification, traceability or manufacturing relationships, plus dimension, ODS, link, measure and KPI evidence. Agree grain, formulas, units, revisions, BOM baseline and effectivity first.
5. The alternative approved `xml-analytics-materialize` job validates retained XML against its schema and creates relational projections. Retaining files alone does not create those tables.
6. Review product contract, business owner and approved semantic release. Validate and publish through the product workflow; inspect packaging and catalog delivery separately.
7. In **Data Catalog → Published products**, confirm exact version, lineage and consumer evidence.

**Business example:** AP242 Structural Inventory can show observed part records, names, classification and source traceability. It is not automatically a complete manufacturing BOM or a certified PMI coverage KPI. Test marts are not customer-approved products. Missing formulas/units/ownership cannot be filled by approval inference.

Migration creates supporting structures; an authorized worker populates the chosen dataset/mart; publication creates a package; delivery registers the release. These are separate observable outcomes.

## 7. Change, approval, TRS and configuration demonstration

### Change Control and approval

Open **Change Control**, find the intended merge, bridge, ontology publication, run, product release or learning review, and compare its authorization, execution and delivery fields. Open the owning workspace to review/approve the actual retained proposal. After execution, return and inspect receipt/delivery. This is central read-only evidence, with OSLC CM representation/linking; it is not a complete unified CR/CO authoring process. A policy-authorized automated workflow can publish within its declared scope. Neither an agent explanation nor a successful logical check grants authority.

**Example:** a merge plan can be ready for review while its graph publication is not verified. A product package can be retained while catalog delivery needs attention. These should not appear as one vague “approved” state.

### Configuration baseline

Select a registered RDF source/version and prepare a dataset. Inspect its retained configuration identity and source lineage. The baseline freezes the source plus declared ontology/mapping/KPI/shape references and content digests. Reopen the run after a source revision changes: historical replay must retain its pinned inputs rather than silently use the newest version.

Technical demonstration, if required: the processing API accepts this deployment's retained `Configuration-Context` URI `/oslc/lifecycle/analytics-baselines/{configuration_id}`; the baseline read API is `GET /api/v1/pipeline/semantic/configurations/{configuration_id}`. Use configured access, not keys pasted into the slide. Foreign/conflicting context is rejected. This is a PMem extension; OSLC stream creation, global configurations and external-provider negotiation are not implemented. Referencing a KPI artifact records context; it does not by itself execute a formula.

### OSLC TRS and refresh assessment

With local TRS enabled and a prepared dataset selected, choose **Check source changes and refresh needs** in Data Products using an approved `semantic-source-review` workflow. Demonstrate a controlled revision change to the registered demo source, then inspect the worker's retained assessment. It reconciles declared input revisions/artifacts and one bounded page of ordered TRS events, retaining its checkpoint. Execution can be completed while assessment says `refresh_required` or `review_required`.

**Say:** “We can identify evidence needing review without silently replacing the released product.” Disabled/unavailable TRS or a retention gap remains explicit. Publisher coverage is partial, so revision reconciliation is still required. Recurrence uses the existing scheduler only when configured; TRS notification is not permission to rebuild or publish. A new approved preparation/release follows the owning workflow.

## 8. Recovery and final rehearsal

| Situation | Action |
|---|---|
| 401/403 or expired access | Reconnect necessary scopes; inspect retained status. Do not rotate all keys blindly. |
| Run history busy (503) | Retry the read after the suggested delay. Do not repeatedly replay. |
| Lost acknowledgement / interrupted worker | Inspect durable status and reconcile receipt before another write. |
| Missing artifact/import | Restore the retained source or supported offline dependency closure. |
| Job finished, catalog empty | Inspect product approval, package and delivery status. |

Navigate away/back, refresh, reconnect and reopen the same run. Confirm no duplicate submission, no stale response replacing current scope, and the same receipt/version. Capture the first failure's request ID and matching sanitized service log. The lock-contention fix bounds run-history reads; the original three historical soak timeouts remain unattributed.

## 9. Upgrade an existing customer environment

Use a maintenance window and verified backup/rollback procedure. Place the **complete matching release** in the existing directory, preserving `.env.local`, credentials and customer data/artifacts. The updater does not download GitHub code. Do not copy just the wrapper or mix old workers and new APIs.

From the customer install root (example):

```powershell
Set-Location E:\App\PMem
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\update-depo.ps1 -EnvFile .\.env.local -PreflightOnly
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\update-depo.ps1 -EnvFile .\.env.local
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\diagnose-depo.ps1 -Phase Runtime -EnvFile .\.env.local
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\infra\windows\test-depo-browser-session.ps1 -EnvFile .\.env.local
```

Use `-InstallDependencies` when backend requirements changed or isolated runtimes are missing; frontend lockfile compatibility is checked automatically. Default update preserves timeouts; `-LlmTimeoutSeconds` explicitly requests a configuration update.

Sequence: package/configuration/runtime checks → read-only database history/privileges and graph compatibility → managed application shutdown → root installer → pending checksum-verified PostgreSQL migrations → credential validation → graph provisioning/index checks → APIs/workers/endpoint checks → frontend build/readiness → upgrade reviews. Existing PostgreSQL/graph data is retained. Migration files currently run through **017**; older supported installations receive semantic datasets (**015**) and business marts (**016**). Migration and final schema verification share a transaction. New changes need new migrations, not edited historical checksums.

For failure, inspect `logs/installation/runs/` and `logs/windows-services/`, correct the reported cause, and rerun the same update. Do not drop schema/history or start an older release against a migrated schema without reviewed rollback. Reviews do not automatically approve/publish customer data. Refresh and reconnect after upgrade; check retained status before replay.

## References

[Workflow ownership](WORKFLOW-ENGINE.md) · [Analytics contracts](SEMANTIC_ANALYTICS.md) · [Installation](../INSTALLATION.md) · [Reasoning and timeout evidence](audits/owl-dl-timeout-verification-2026-11-02.md). Slide notes identify code sources. Local tests/code presence do not certify an untested customer deployment.
