# Admin maintenance session correction — 2026-10-09

## Root cause

The central connection cleared all browser credentials, including the raw Admin key. Its delegated session intentionally excluded `ADMIN_API_KEY`. Read-access probes then passed, while cleanup routes still required the Admin key. The header's general access indicator obscured this distinction. Raw keys were memory-only and therefore could not survive reload either.

## Correction

Session creation accepts a separate boolean `include_maintenance`, false by default in the API. The connection UI exposes this choice and enables it by default when the administrator connects. It does not implicitly enable workflow write scopes. When selected, the opaque fifteen-minute session contains a maintenance grant bound to the current Admin credential digest. Frontend navigation and same-tab reload restore this opaque grant; no raw Admin key is persisted.

Admin maintenance routes accept this grant through their dedicated verifier. Generic Admin credential verification still rejects session tokens, so registration/rotation/revocation of credentials requires a raw Admin key. Expiry, logout, Admin rotation and revocation invalidate the delegated maintenance grant. Read-only sessions fail closed for maintenance. The UI names maintenance access separately from verified service reads and links directly to the credentials tab.

## Upgrade procedure

Deploy frontend and backend changes together and restart the API services. Existing sessions have no maintenance grant: reconnect in Admin → Service credentials using the Admin key with **Enable Admin maintenance for this session** selected. Enable upload/execution scopes separately if those operations are needed. Reconnection does not execute cleanup; destructive actions retain their confirmation and scope-preview controls.

## Validation boundary

Final focused checks: **21 backend tests passed** (plus 3 passing subtests) and **23 frontend tests passed across 4 files**. These counts overlap existing suites and must not be added to the full-suite total.

Isolated tests cover delegated scope creation, rejection of credential administration, read-only scope escalation, Admin rotation, maintenance route dispatch, UI storage without raw secrets, reload and expiry. No customer Neo4j data was deleted and no live PostgreSQL/APIM acceptance was performed.
