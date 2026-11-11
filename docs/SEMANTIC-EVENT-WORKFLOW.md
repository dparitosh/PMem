# Semantic source preparation and event review

PMem uses the existing workers, CEIM semantic contract, Governor/Steward boundaries, Graph Analyst, Companion and memory services. This workflow does not introduce another orchestrator, vector store or LLM gateway.

## What users do

1. Select a registered source in Admin and acquire records with an approved worker job. Source locations and credentials remain on the server.
2. Prepare an explicit source-field mapping through the approved `connector-ceim-normalize` job. Choose a supported source type from the existing CEIM mapping pack. The retained acquisition run and source artifact must match. The current mapping step is an API/job contract; it does not yet have a general drag-and-drop field-mapping designer.
3. Review the retained semantic proposal in Data Flow. Validation failure produces a rejected partition; success produces an accepted proposal. Neither outcome grants publication approval.
4. Obtain the intended approved semantic release and authorize publication through the existing canonical CEIM publication action. Verify its receipt before retrying after a timeout.
5. Use published graph data for contextual investigations and prepare approved analytics/product versions through their existing workflows.

Incoming events use the parallel path: approved source → capture → reconciliation → review → separately authorized publication. Data Flow → Event reviews lists retained reconciliations. Select a review to see processing state, semantic check status and publication status separately. Open the Companion or use Investigate event review for the existing Graph Analyst. No agent or model starts automatically.

## Semantic and memory boundaries

- The existing CEIM mapping packs and validator normalize and check proposed business records. Vocabulary supplies meaning; matching names alone do not establish equivalence.
- The existing Steward can inspect retained reconciliation evidence. The Graph Analyst can inspect both a selected processing run and reconciliation. These are read-only tools, not release privileges.
- The Companion reads the current owning-service record and returns a business-readable table with a retained citation. This selected-record answer works without an LLM. Missing, foreign or unverifiable evidence is held instead of replaced with another record.
- `reconciliation_id` participates in conversational scope, history matching, cancellation, page-task identity and the goal context envelope. Conversations for different event reviews do not reuse one another's context.
- The existing optional memory service retains scoped conversation/tool context through its normal paths. Approved, version-scoped semantic bridge lessons remain long-term advisory hints. Event captures and successful validation are not automatically promoted into approved business facts or model training. Current service evidence takes precedence over remembered context.
- SHACL/structural conformance, an executed artifact-bound OWL-DL check and engineering approval remain separate assertions. This workflow does not claim global OWL-DL consistency from event validation.

## Recovery and publication

Capture inserts an event identity atomically. Equal retries return the existing receipt; conflicting business payloads return HTTP 409. Transport approval fields are excluded from new captured artifacts and the business digest. Pre-upgrade retained envelopes remain immutable and can be compared safely on retry; historical artifacts are not rewritten by the upgrade.

Reconciliation uses a stable intent, bounded cross-process ownership, a staged result and a PostgreSQL transaction that compares and transitions the exact event rows and receipt together. A failure cannot expose a ready receipt for half-transitioned events. An interrupted operation can resume using the same event selection and authenticated identity. A competing event state or changed receipt is held rather than overwritten. Older partial transitions can be repaired only for the exact retained event set and original reviewer.

Publication remains separately authorized and receipt-verified. The event gateway is intentionally serialized during reconciliation; this is a bounded current design, not a production streaming throughput claim. The Kafka adapter remains snapshot acquisition, not continuous offset-managed streaming. Customer-specific ordering, supersession and retraction policies are still required before a live continuous feed is accepted.

## Operator setup for connector semantic preparation

Create a versioned job definition with job type `connector-ceim-normalize`, quality profile `semantic-core-v1` and explicit `allowed_standards`, then review/approve it through the normal Data Flow definition lifecycle. Example request input for an AP242 product-definition source:

```json
{
  "acquisition_run_id": "<selected completed acquisition run>",
  "artifact_id": "<that run's retained source artifact>",
  "standard": "ap242",
  "source_type": "product_definition",
  "id_field": "part_number",
  "attribute_fields": {"name": "part_name", "description": "part_description"}
}
```

These are references from the retained acquisition, not newly invented identifiers. Attribute targets must belong to the selected CEIM pack; source identity is explicit, duplicate identities require review, nested/oversized fields are rejected, and source bytes are verified against their content address. The proposal retains the source artifact, run and mapping-pack digest. It does not infer relationships or mappings from memory.

## Existing deployment upgrade

Use the repository-root `update-depo.ps1 -EnvFile .env.local` after deploying the matching release files. Migration `infra/postgres/migrations/017_speed_event_pagination.sql` adds the captured-event pagination index. Existing credentials, records and publications are preserved; no schema reset, event replay or approval is performed automatically.

The source framework remains the 17-ingestor inventory. Real cloud/warehouse/mail/MCP/Kafka credentials and vendor SDK acceptance are deployment-specific; see [Registered source acquisition](CONNECTOR-SOURCES.md).


## Existing autonomy and memory continuity

PMem already has bounded autonomous read planning, tool observations, retained workflows, optional graph conversation memory and governed mapping feedback. These mechanisms are reused; this change does not install a second memory framework or claim automatic model training.

| Memory | Existing owner | Use and freshness rule |
| --- | --- | --- |
| Short term | PostgreSQL Companion turns and workflow observations | Resolve follow-ups within the authenticated conversation and exact selected scope. Retain the resolved retrieval query so a second follow-up does not lose the original subject. Failed/unanswerable turns do not supply a subject. |
| Contextual | Current graph/service evidence; Semantica ContextGraph for its registered business-context records | Reload the selected record and relationship context before answering. Conversation memory can select a subject, but cannot establish a current fact. Semantica business-context state is PostgreSQL-backed and is not automatically synchronized with every graph projection. |
| Optional graph conversation memory | Existing AgentMemoryService | Project only allowed selection identifiers into context_json. Its failure remains visible as optional enrichment failure; mandatory PostgreSQL evidence is retained independently. Raw credential/context dictionaries are not copied into that property. |
| Long term | Governed learning outcomes/approved revision-scoped lessons; approved semantic bridge facts | Reuse as review hints within the current ontology revision and validity constraints. Superseded/revoked lessons and stale publication facts must not become current evidence or authorize a write. |

The Companion now supplies its selected scope when writing optional graph memory. It retains the resolved query alongside the original user wording in PostgreSQL. No database migration is needed for these added JSON fields/graph properties; old turns remain readable through the original-question fallback.

This reduces subject loss, cross-selection context reuse and optional-memory coupling. It does not eliminate API/session failures or replace transactional recovery. Agents still terminate within their existing tool/plan budgets, inspect current evidence and use existing approval boundaries. Self-learning here means retained reviewed experience and approved reusable hints, not unsupervised changes to model weights, approval policy or customer business facts.
