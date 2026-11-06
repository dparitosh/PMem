# Admin key/session handling review — 2026-10-09

Audited the working-tree maintenance delegation changes against baseline `cea9484`. No application changes were made during this audit. This is not live customer acceptance or proof that all session defects are absent.

## Findings fixed in the working tree

Follow-up: A1 preserves explicit Admin headers, including lowercase plain headers and AxiosHeaders. A2 uses combined read/maintenance verification in the header, probing `/auth/admin-access` with GET only and reporting separate results. A3 initializes the maintenance choice from restored session scopes. Focused regression tests passed (32 tests across 5 files); customer gateway acceptance remains pending.

### A1 — P2: automatic Admin header overwrites explicit credentials

`frontend/src/services/apiClient.js:148` unconditionally replaces `X-API-Key` on an Admin request with the stored profile. The earlier interceptor branch preserves explicit credentials, but this later branch reverses that decision. A request explicitly using a newly supplied raw Admin key can instead send an older maintenance token/key and fail authorization. Preserve an explicit header; inject the stored credential only when absent. Test both plain objects and AxiosHeaders.

### A2 — P2: revalidation does not check maintenance access

`frontend/src/app/AppShell.js:61` invokes `verifyStoredReadAccess`; `frontend/src/services/readAccessVerification.js:11` probes only `/auth/access` with the graph/read token. Maintenance scope is not checked. A read-only session or a separately invalid Admin key can pass this check while cleanup still fails. The success text correctly says Read access verified, but the button's broad label and lack of maintenance status leave the original ambiguity. Probe the existing nonmutating `/auth/admin-access` endpoint separately when maintenance is configured; display independent read/maintenance results. Never execute cleanup as a validation probe.

### A3 — P2: restored scope choice is not reflected in the maintenance checkbox

`frontend/src/Components/CredentialSettings.js:21` always initializes `includeMaintenance` to true. A session deliberately created without maintenance restores with that choice checked, while workflow writes correctly derive their choice from restored profiles. Reconnection then requests maintenance unless the user deselects it again. Derive this preference from restored session scopes when a session exists, preserving the chosen new-session default only when disconnected.

## Verified boundaries

- Browser-session creation verifies the raw Admin key, snapshots registered credential digests, and limits expiry to fifteen minutes or the Admin credential expiry.
- The backend API defaults maintenance to false and validates its boolean input independently of workflow-write scopes.
- Read-only sessions cannot pass maintenance authorization.
- Maintenance sessions cannot pass generic Admin verification for credential registration, rotation or revocation.
- Dedicated cleanup verification binds its maintenance scope to the active Admin digest and rejects rotation, revocation and expired sessions.
- Only the opaque session token and scope/expiry metadata survive same-tab reload. Raw API keys are memory-only.
- Expiry/logout clear delegated read, workflow and maintenance profiles. Requests use `X-API-Key` for maintenance; rejection handling recognizes opaque tokens in that header.
- A credential-authority outage fails closed rather than granting access.

## Operational limitation

APIM subscription keys remain memory-only. A restored opaque session alone cannot satisfy a gateway requiring that subscription header after a full reload. Re-enter/revalidate gateway credentials when needed; do not persist raw subscription keys as a workaround. This audit did not contact customer APIM.

## Validation

Focused isolated authorization/UI tests passed: 21 backend tests plus 3 subtests, and 23 frontend tests across 4 files. Suites cover browser credentials, Admin lifecycle, CredentialSettings, AdminPanel, serviceAuth and API client sessions. These exercise existing scope boundaries; A1–A3 are code-review findings outside their current assertions. Live PostgreSQL revocation/concurrency, real cleanup authorization and gateway/browser acceptance remain pending. No Neo4j data was deleted.
