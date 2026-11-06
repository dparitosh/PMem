# DEPO agent memory design — proposed contract

## Context envelope

Version the internal envelope. Required fields: schema version; authenticated principal reference; tenant/project; purpose; session/run/task IDs as applicable; pinned source and ontology revisions; correlation ID; deadline; byte/token/evidence budgets; authorized tool-contract digest. Evidence items carry stable ID, owner-service reference, source revision, retrieval time, validity/lifecycle state, score basis and coverage limitations.

Secrets, bearer headers and full environment snapshots must not be retained. Use existing credential fingerprints and grants. Do not store hidden chain-of-thought; retain concise plans, observable decisions, tool inputs after sanitization, tool outcomes and business receipts.

## Layer ownership

| Layer | Existing owner to extend | Policy |
|---|---|---|
| Working | sessions, goals, companion adapters | Server pins identity/scope; compression preserves evidence references, unresolved questions and omission markers |
| Episodic | PostgreSQL workflow/goal owners | Append correlated observable events; read projection preserves owner authorization; optional graph enrichment is separately reported |
| Semantic | ontology/graph service and scoped memory adapter | Validate lifecycle and source revision before reuse; no approval inferred from model output |
| Procedural | existing agent/tool/workflow catalog | Versioned definition, digest, input contract, evaluation evidence, approver and deprecation policy |
| Forgetting | existing retention/cleanup owners | Coordinated request with per-owner receipts; no global best-effort success claim |

## Recovery and handoff

Keep current goal decision/deadline limits and failed-read observations. Permit alternative registered reads under the same scope; do not broaden privileges or retry writes automatically. Handoff transfers envelope and evidence references, not credentials. Reject a changed tool contract or stale approved source revision rather than silently resuming a different operation.

## Retention and deletion

Define separate policies for transient prompts, session metadata, execution receipts, approved mapping evidence and raw artifacts. Legal hold and mandated audit requirements need product policy decisions before destructive implementation. A deletion request progresses requested → executing → partially completed or completed, with per-store counts and failure reasons; this state machine is proposed. Invalidation removes facts from current retrieval immediately, while physical purge follows authorized retention policy.

Do not reuse expired conversations via semantic-memory fallback. Do not promise full deletion until PostgreSQL records, Neo4j projections, retained files and applicable indexes/caches have acknowledged their own work. Backups require a separate retention/restoration policy; a cache clear is not deletion of authoritative data.

## Procedural learning

A successful episode may suggest a procedure candidate. Promotion requires reviewed inputs/outputs, deterministic tests, security classification, compatible tool versions and explicit approval. Failed or malicious retrieved content never becomes executable instructions. Retire old procedures without invalidating already-retained run definitions.
