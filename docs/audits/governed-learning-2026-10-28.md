# Governed mapping learning follow-up

Date: 2026-10-28. Follow-up to the L0–L4 remediation. The implemented scope is receipt-bound mapping feedback and approved advisory reuse, not autonomous model training.

## Delivered

- Human assessments require an exact published candidate and matching graph transaction receipt. Notes and publication provenance are retained in PostgreSQL.
- Assessment revisions append evidence rather than overwrite it. Only the current assessment can support a lesson; amending it atomically supersedes dependent active hints. Repeated requests cannot inflate sample counts or roll back to a superseded assessment.
- Pending lessons are not reusable. Explicit authorized approval promotes a hint; revocation removes it from the current lookup. Ontology/source changes prevent stale promotion, and the approved index is model-revision scoped and capped at 20 hints.
- Governor, Steward and the existing self-learning review role have the read-only `learning.lessons` tool. Steward results show matching approved patterns. Agents receive fixed-template hints rather than arbitrary human notes, cannot promote lessons, and cannot ground a business conclusion on hints alone.
- Semantic Bridge exposes separate feedback, preparation, approval, amendment and revocation controls. Requests are fenced by source/access generation, duplicate clicks are blocked, and late results are discarded. Errors do not claim a successful save.
- The existing control-plane service, approval credential and indexed PostgreSQL registry are reused. No new migration, broker or model service is required. Feedback operations do not publish or modify graph data.

## Validation

[Backend evidence](governed-learning-2026-10-28/backend.xml): **442 passing tests** after the live-discovered pagination and lightweight-receipt fixes. Includes receipt mismatch, missing publication, uncertain evidence, duplicate retries, amendment/supersession, stale source, corrupted records/index, transaction failure, unauthorized writes, API review flow, deadline preservation, injection text exclusion, large target pages, heavy-read avoidance and the existing L0–L4 suite.

[Frontend evidence](governed-learning-2026-10-28/frontend.xml): **75 passing tests** in five files. Includes the new feedback flow, explicit approval boundary, duplicate click, late response cancellation and wrong-source rejection, plus existing bridge recovery, Companion scope, product scope and read-goal behavior. Existing React/RDFLib deprecation warnings remain.

Tests use isolated stores and graph receipts for feedback mutations. They do not establish customer-server acceptance, live model quality or production restoration. Local runtime checks are recorded separately after deployment. No model calls are required for these controls.

The first live lookup exposed an existing cross-service limit: a retained large ontology caused Graph mapping targets to return 422 above 10,000 terms, propagated as ingestion failure and learning 503. The graph owner and peer client now support bounded, version-checked pagination. New negative tests cover changed revision/scope/continuation, duplicate targets and unversioned multi-page sources; partial target evidence is rejected. Complete reads remain capped at 100,000 terms, 64 MiB and the configured query deadline. Both graph and agentic applications were imported and their actual OpenAPI documents generated after this change.

A subsequent live attempt exposed a second coupling: hint reads unnecessarily rebuilt a full mapping snapshot and timed out. Hint retrieval now checks the ontology owner's lightweight artifact/lifecycle/foundation receipt. Full original source snapshot and publication checks remain mandatory at approval, with a bounded write budget. A regression proves that hint reads and Steward hint lookup do not call the heavy snapshot reader and that changed model receipts prevent reuse. The import task ID remains conversational context; a hint read does not verify that instance's data or conformance.

Local acceptance completed on 2026-10-29 (IST): [runtime receipt](governed-learning-2026-10-28/live.json). All ten APIs returned ready. The previously timing-out lookup completed in **672 ms**, with an authoritative model receipt and zero approved hints. Anonymous access and a feedback write using a read-only grant were rejected; the latter returned 403. All three intended roles expose only the learning read tool. Installed/workspace backend fingerprints match and **353 frontend build inputs** verified. Served asset: `/assets/index-CBLWuNDJ.js`. Startup verified PostgreSQL migrations 1–13 and the existing indexes/constraints; 17 application credential profiles remained unchanged. No live feedback or graph mutations and no LLM calls were performed. Positive promotion/revocation was exercised through isolated API/store tests, not against customer data.

## Still outside this scope

General outcome-based model tuning, automatic policy/model promotion, independent engineering verification, a populated customer business acceptance exercise, customer APIM/Windows behavior, large-model performance certification and verified disposable database restoration remain separate work. Mapping review counts must not be presented as measured model accuracy. See [the workflow and architecture contract](../GOVERNED_LEARNING.md) and [customer acceptance](../../infra/deployment/CUSTOMER_RELEASE.md).
