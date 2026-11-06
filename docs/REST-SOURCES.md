# Register and fetch REST sources

Open **Admin → Data sources**. This uses Semantica's installed `RESTIngestor`
through the existing pipeline service; it does not add a microservice.

## Server configuration

Add the exact permitted hostnames to the selected deployment `.env.local`:

```dotenv
DEPO_REST_ALLOWED_HOSTS=plm.example.com,parts.example.com
DEPO_REST_SECRET_PLM=replace-locally-with-the-external-api-key
```

Never commit the real secret. Restart the services and worker after changing
server settings. This dedicated outbound secret is separate from DEPO API tokens:
DEPO's central credential authority stores one-way verification hashes and cannot
recover those hashes as outbound credentials. Do not reuse a DEPO access token.

Endpoints may use HTTP port 80 or HTTPS port 443. Both support Bearer,
`X-API-Key`, and `api-key` headers. HTTP sends the key without transport
encryption; HTTPS is preferred. URLs cannot embed credentials, query strings or
fragments. Redirects and private/loopback/link-local addresses are blocked even
when their hostname is listed. This initial connector supports public endpoints,
not private-network deployment endpoints or arbitrary ports.

## User sequence

1. Connect source-management (`DATA_JOB_APPROVAL_TOKEN`) and execution
   (`DATA_JOB_EXECUTION_TOKEN`) scopes in Admin API access.
2. Select Data sources → Register a REST source. Give it a unique ID and name,
   endpoint, optional records path such as `data.items`, and the server secret
   reference `DEPO_REST_SECRET_PLM`. Choose its authentication header. Leave the
   reference empty for an anonymous API. Do not paste a key into this form.
3. Register, then select Test connection and preview. Up to ten records display
   as property/value rows. Preview does not retain an ingestion or publish data.
4. Refresh sources and jobs. If no approved acquisition job exists, create its
   draft, then review and approve it in Data Flow. The job type is
   `rest-source-ingest`; the initial draft is `rest-source-acquisition@1.0.0`.
5. Select the approved job and source, then Fetch records with worker. Inspect the
   queued run in Data Flow. If a response is lost, use Refresh retained submission;
   its reference survives reconnect and navigation. The server reconciles that
   reference and shares an already-active acquisition across tabs for the same
   actor/source/job. Prepare another fetch becomes available after a terminal
   outcome is confirmed. It requests a new snapshot, rather than replaying an
   unresolved submission.
6. Use retained records as source evidence for subsequent reviewed processing.
   The target-model field is descriptive metadata, not a mapping or validation.
   This acquisition does not automatically create graph entities, analytics
   tables, dimensions, facts, KPIs or products.

## Persistence and execution

Registrations are immutable PostgreSQL `depo_registry` entries in the
`rest_sources` namespace. No new database migration is necessary. Revised
configuration uses a new source ID. Secrets stay in server configuration.
Runs and leases use the existing `data_job_runs` registry and pipeline worker.
Submission intents and references use the `rest_source_submissions` namespace.
Source listing is paged (50 entries in Admin, server limit 100). A failed job
catalog does not block independently loaded source browsing or preview.
Fetched JSON is retained by ArtifactStore with source, endpoint, model reference
and correlation provenance; the run output references it under
`partition_artifacts.source`. It is not an accepted semantic partition.

Limits: one GET request, 2 MiB response, 1,000 record objects, 5-second connect and
10-second read timeouts inside a killable, maximum 20-second acquisition process
(or the earlier inherited operation deadline). A child watchdog also terminates
acquisition if its parent crashes. No automatic
HTTP retry or pagination. A run replay fetches a new snapshot of the registered
endpoint; it does not reproduce the original remote response. Recurring refresh
is not exposed by this source form. Semantic validation and publication require
their existing separate workflows and authorizations.

## Verification scope

Automated tests exercise the real Semantica adapter with a mocked HTTP boundary:
protocol and header selection, host restrictions, redirects, response size,
malformed records, absent credentials, source immutability and artifact handoff.
UI tests cover approved-job selection, submission locking and late responses
after session expiry. A customer endpoint and its secret are still required to
verify actual customer network connectivity and end-to-end acquisition there.

Initial local automated verification on 2026-10-31: 79 backend tests and 112 request-schema
subtests (connector, existing pipeline and body contracts), 20 frontend tests
(source panel, Admin and session transport), and production builds passed. A
stale legacy handler name in the historical API inventory was corrected. The
deployment contract gate caught an initially unnamed registration body; the
explicit RestSourceBody and a new gate regression now pass. Local restart,
endpoint validation, browser authentication, Admin source loading and form
rendering passed; no browser console errors were observed in that check. The
HTTP boundary is simulated in adapter tests; no customer key or live external
endpoint was supplied. Source registration did not create any sample source or
grant approval automatically.

Audit follow-up: the six findings in `audits/rest-sources-2026-10-31.md` have
regression fixes. Verification now includes 91 backend tests, 112 schema subtests,
26 frontend tests and real PostgreSQL registration/concurrent-submission checks
in disposable namespaces. The current implementation uses paged listing and
retained submission recovery, and enforces the acquisition deadline with a
killable process and child watchdog. Customer endpoint authentication remains
untested without that customer's endpoint and server-side credential reference.
