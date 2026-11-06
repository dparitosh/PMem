# Presentation implementation audit — 30 October 2026

Scope: 12-slide workflow deck against local PMem source. This is a documentation audit with focused backend regression tests, not full customer acceptance.

## Confirmed presentation defects corrected

| Severity | Slide | Defect and root cause | Correction / evidence |
|---|---|---|---|
| High | 7 | Conversation history and mapping lesson review implied one automatic learning chain. Separate implementations have different scope. | Split conversation context from mapping outcomes. backend/agentic_service/companion_memory.py:6; learning_review.py:133,162,198. Lessons remain advisory, revision-bound, and do not train models. |
| High | 4 | Ontology publication implied approval of a semantic asset release. These are distinct approval contracts. | Explicitly separated ontology publication from semantic release. backend/ingestion_service/workflow.py:84; backend/ontology_service/publication_jobs.py. |
| High | 10 | Graph storage implied ownership of retained ontology versions. | PostgreSQL authoritative ontology artifact ownership, graph published projections. backend/ontology_service/catalog.py:105. |
| Medium | 3 | All ingestion implied worker ownership and required agent involvement, source owner capture and unified catalog receipt. | Changed to import services, supported metadata and retained import/publication evidence; optional investigations. |
| Medium | 8,11 | Dimensional functionality described too broadly as absent. | Explicit dimension / aggregate fact views are supported. Full automatic mart design and KPI semantics remain gaps. backend/data_pipeline_service/xml_analytics.py:120-192. |
| Medium | 2,9 | Flow diagrams could imply a universal executable pipeline. | Qualified as capability flows and specifically validated bridge workflow. Actual bridge-validated-automation sequence in backend/agentic_service/catalog.json:774-797. |

## Verified boundaries

Governor proposes; Steward evaluates retained previews; server authorization controls publication. Actual workflow tools: bridge.mapping.preview, bridge.mapping.evaluate, bridge.mapping.publish_automatic. Ontology union produces a draft, not an automatically approved graph release. HermiT consistency is scoped to exact checked artifacts and does not establish mapping correctness or business suitability. Change Control aggregation is read-only visibility, not a complete unified CR/CO process. Presentation pipeline labels are not executable job identifiers.

## Execution evidence

Focused pytest: test_steward_governance.py, test_governed_learning.py, test_xml_analytics_materialization.py, test_change_control.py.
Result: 60 passed, 9 subtests passed. First attempt had six temporary-directory fixture access errors; rerun with a workspace-owned fresh --basetemp passed. No application source changed during this audit.

## Limits

No new customer deployment, LLM availability test, full browser acceptance or load benchmark was performed. Prior JEP30 and real PostgreSQL observations are historical acceptance evidence, not rerun in this audit. The deck explicitly lists open compatibility and acceptance gaps. Do not treat this deck as customer-release certification.
