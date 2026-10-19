# Browser access profiles

Configure these **server-side settings in the repository-root `.env.local`**.
They are read when the frontend launcher starts; do not put keys in frontend
environment variables or compile them into JavaScript.

| Setting | Default | Purpose |
| --- | --- | --- |
| `DEPO_BROWSER_AUTH_MODE` | `manual` | `manual` uses the existing explicit session connection; `local` uses the workstation's frontend credential broker. |
| `DEPO_LOCAL_BROWSER_WRITES` | `false` | In local mode, `false` grants registered read access; `true` also grants currently registered workflow scopes. Credential administration is always excluded. |
| `DEPO_LOCAL_SESSION_AUTHORITY_URL` | `http://127.0.0.1:8011` | Ontology service issuing delegated sessions. Must be HTTP with a literal loopback address, no credentials, path, query or fragment. |
| `DEPO_BROWSER_SESSION_IDLE_SECONDS` | `900` | Existing delegated-session idle limit, 60–900 seconds. |
| `DEPO_BROWSER_SESSION_MAX_SECONDS` | `28800` | Existing maximum lifetime of a delegate, 900–86400 seconds. |

## Single-user workstation

```dotenv
DEPO_ROUTING_MODE=local
DEPO_FRONTEND_HOST=127.0.0.1
DEPO_BROWSER_AUTH_MODE=local
DEPO_LOCAL_BROWSER_WRITES=true
DEPO_LOCAL_SESSION_AUTHORITY_URL=http://127.0.0.1:8011
```

Local mode explicitly trusts the users and processes on this workstation. It
is not Windows integrated authentication, and is unsuitable for an untrusted
shared computer. The launcher must run under the intended Windows account with
access to `.env.local`. Local mode rejects non-loopback frontend binds, APIM
routing and gateway configuration. Use only a trusted local ontology authority.

The browser obtains a scoped, revocable delegate automatically. It never
receives `ADMIN_API_KEY` or raw service keys. The frontend broker requires an
HttpOnly, SameSite=Strict launcher cookie, the exact same origin and an approved
loopback Host/client. The broker disables redirects and environment HTTP proxies.
PostgreSQL still verifies the administrator credential and registered scopes;
credential rotation and revocation continue to invalidate delegates.

Visible local application tabs renew their delegates automatically. After an
idle/absolute expiry, local access can obtain a fresh delegate from the trusted
launcher. Hidden tabs do not keep sessions alive. Explicit **Clear credentials**
remains signed out across same-tab refresh; use **Reconnect local access** to
resume. Maintenance and credential changes retain explicit administrator access.

After changing server-side settings, stop/start the frontend with the normal
Windows scripts. Restart backend services when changing delegated-session
lifetime settings. No frontend rebuild is needed for profile changes once this
release is installed. No services or credentials are recreated.

## Distributed / APIM deployment

```dotenv
DEPO_BROWSER_AUTH_MODE=manual
DEPO_LOCAL_BROWSER_WRITES=false
```

Keep normal routing, registered service scopes and session renewal. Frontends
hosted by an existing static server fall back to manual access if the local
broker endpoint is absent. This change does not implement an SSO provider or
remove authentication from network-facing services. Integrate trusted SSO/APIM
identity at the deployment boundary; do not distribute an administrator API key
to ordinary end users as an identity solution.
