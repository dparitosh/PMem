# Credential integration audit — 2026-10-05

> Dated audit record: use [the current audit index](README.md) for latest validation and acceptance status. Findings and test counts below belong to their recorded review; they are not a current release certificate.

Scope: local source, PostgreSQL migrations, shared authorization, Admin credential entry, OpenAPI discovery, workflow consumers, chat and graph. No customer VM/database or live gateway was available. Changes are not deployed.

## Storage and service trace

No dedicated credential table or migration exists. `depo_registry` stores JSON runtime records; `depo_chat_messages` stores conversation history. Neither is implemented as an API-key authority. Admin keys are held in frontend serviceAuth module memory. Backend authorization reads process environment with os.getenv; agentic downstream credentials independently read process environment. Therefore Admin entry does not register, rotate or synchronize server keys and cannot resolve server environment drift.

## Findings

| Priority | Finding | Evidence / required correction |
|---|---|---|
| P1 | Requested PostgreSQL credential authority is absent; cross-service startup drift remains | authorization.py and transport_auth.py use os.getenv, migrations contain no credential tables. Implement hashed keys with profile/scope/actor/expiry/revocation, migrations and a common validator before claiming database management. |
| P2 | Generic validation differs from actual administrative/approval authorization | service_runtime credential_check uses service_write_identity for all profiles. ADMIN routes use require_admin_api_key and X-API-Key; approval_identity additionally needs approved_by and does not trim expected values. Match credential validation to actual policy and clearly distinguish key validation from action authorization. |
| P2 | A read-key check covers only graph, while other services use separate environment snapshots | CredentialSettings routes GRAPH_READ_TOKEN to graph only. Validate read access across configured services and show per-service status. |
| P2 | Expiry or later revocation is not reflected in the configured UI badge | getServiceAuthToken presence drives the badge; no live validation state or expiry refresh. Treat it as stored, not authorized. |
| P2 | OpenAPI import mutates the active gateway subscription before contract discovery succeeds | ServiceAccessDiscovery calls setGatewaySubscriptionKey without rollback. Stage proposed settings and apply only after validation. |
| P2 | Existing frontend tests reference removed credential inputs | AppShell, Chatbot, SemanticBridgeJobs, QIF, DataFlow and SysML tests still target removed labels. Update these and add central Admin validation/failure/clear tests. |
| P2 | Credential-check contract has a dynamic profile with no explicit operation-profile description | Generic endpoint relies on query profile but static OpenAPI inference cannot identify one token. Describe supported profile mapping explicitly; do not auto-run mutating operations for validation. |

## Current consumer paths

- GraphApi read calls explicitly attach the shared graph-read credential.
- Chat stream and sample-query calls use serviceAuthHeaders with endpoint/method; ambiguous contracts fail closed.
- Import upload/execution obtains ingestion/execution profiles; commit retains user approval and uses ingestion write key.
- Semantic Bridge uses graph read for preview/status and AGENTIC_APPROVAL_TOKEN plus approver for publication.
- DataFlow uses execution, governance and publication profiles at action time.
- QIF and ontology merge use ONTOLOGY_APPROVAL_TOKEN.
- Admin requests use ADMIN_API_KEY through X-API-Key; legacy adminApiKey fallback remains and should be removed once compatibility tests migrate.
- Backend agent dispatch still obtains its own downstream keys from server environment, independently of browser validation.

## Validation and release status

18 dependency-light backend tests previously passed, including all 16 non-read allowed profiles; syntax parsing covered 17 modified JavaScript files. These checks do not constitute full frontend tests or a live gateway/customer integration test. A PostgreSQL authority, coordinated rotation and complete validation UX are pending. Do not store plaintext browser keys in generic registry JSON.


## Fix follow-up

Implemented an opt-in PostgreSQL incoming credential authority (`DEPO_CREDENTIAL_STORE=postgres`) with migration 008. Salted digests, actor, expiry and revocation are read for each validation; there is no environment fallback on database failure. Bootstrap inserts missing keys only and preserves existing rotations/revocations. Read, write, approval, admin and private graph Bridge publication boundaries use the authority in token mode. Admin offers explicit registration/rotation/revocation with administrator authorization; admin revocation is blocked to avoid self-lockout. The administrator validation uses its actual X-API-Key contract.

Read testing now checks all configured services with individual outcomes. The header badge says key stored. Contract import stages subscription credentials per request without changing the active setting. Updated affected frontend tests to use shared profiles and added Admin validation/partial-failure/clear regression tests. DataFlow publication was corrected to CEIM_PUBLISH_APPROVAL_TOKEN, matching its endpoint. Added explicit non-secret OpenAPI metadata for the dynamic check and administrative credential endpoints.

Validation: 49 dependency-light backend tests passed, package integrity passed with nine migration files, JSX syntax validation passed for modified frontend files. Full Vitest/Vite build and live PostgreSQL/gateway testing remain unavailable locally. No customer services were changed. Backend outbound token material remains in protected server environment because hashes cannot be used to authenticate to peers; coordinated outbound rotation still requires updating that material and restarting callers. Entra/disabled modes retain their existing identity policies; the new authority is for token-mode deployment. The environment-only rotation script now rejects postgres mode to prevent a misleading partial rotation.
