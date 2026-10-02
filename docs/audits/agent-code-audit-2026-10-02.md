# Agent code audit — 2026-10-02

Scope: agentic control-plane execution, ontology review, companion sessions, transport authorization, telemetry, DT integration, configuration and recovery. This is a source audit with focused regressions, not live customer-environment certification.

## Confirmed defects

1. **P1: synchronous registry writes block async execution deadlines.** `backend/agentic_service/router.py:525,543,554` and telemetry start/span/finish call synchronous PostgreSQL operations directly in async routes. A stalled connection/query prevents the event loop from delivering timeout cancellation and servicing other requests. Move registry/telemetry I/O into awaited threadpool calls and enforce database statement/connect deadlines; persist dispatch intent before mutation and retain uncertain-write state when timeout occurs. Merely adding another asyncio timeout does not interrupt a blocking database call.
2. **P1: tool response bodies are unbounded.** `router.py:430-445` buffers HTTP responses before JSON parsing or base64 export. Upload limits do not constrain downloads. A large response can exhaust the service and is amplified when full results are persisted in workflow traces. Stream with a byte limit checked cumulatively, including responses without Content-Length; retain oversized artifacts separately with bounded metadata.
3. **P2: DT cancellation leaves permanent dispatching state.** `router.py:123-136` catches ValueError and HTTPError only. Cancellation/process loss leaves a dispatching record without deadline projection or reconciliation status. Record a deadline and mutation uncertainty; handle cancellation independently from failures and expose expired dispatch state without resending the request. Terminal registry-write failure also currently loses the recovery ID.
4. **P2: agent readiness accepts invalid service ports.** `configuration.py:32-38` validates hostname but never accesses parsed.port. An endpoint such as http://service:invalid/api/v1 is accepted and fails only when dispatched. Validate integer port range and expected API base contract using the shared service-URL validator.
5. **P2: run recovery remains incomplete for ontology and companion routes.** `router.py:193-207,248-292` creates telemetry IDs but omits them from success/error responses, unlike tool/workflow routes. Their errors cannot trigger the existing frontend recovery notice. Return telemetry_run_id/run_id and X-DEPO-Run-ID consistently; identify operation type in retained lookup. Do not repeat a successful chat simply to recover its missing identifier.
6. **P2: workflow traces lack per-owner access checks.** `router.py:522,590-598` persists full downstream results without an owner and allows any valid graph reader to retrieve a known workflow ID. Chat jobs explicitly enforce owner checks. This matters when credentials represent separate users/projects; it is not an unauthenticated endpoint. Store execution ownership/scope and enforce owner or explicit supervisory access. Define a compatibility policy for existing ownerless records rather than assigning them to the first reader.

## Behavior checked and retained

Mutating tools require approval and downstream approval contracts. Automatic retries are restricted to tools explicitly marked non-mutating. Tool path placeholders reject traversal delimiters. Companion sessions validate credential ownership, absolute expiry and idle expiry; startup maintenance prunes expired metadata and graph history. Workflow and telemetry IDs now link explicitly. Agent tool/workflow errors expose retained recovery IDs. Ontology LLM suggestions are review-only and the LLM clients have configured provider timeouts; this audit does not claim they lack network timeout settings.

## Verification

Twelve dependency-free focused regressions passed: run IDs, OpenAPI credential profiles, service URL validation and gateway credential scoping. A direct configuration experiment confirmed all ten malformed service ports were omitted from invalid_settings. Other findings are established by code tracing, not production load testing. FastAPI integration tests were not run because temporary dependencies have been removed. No application code was changed during this audit.


## Fixes implemented

All six findings have fixes: async agent registry/telemetry calls use cancellable thread offload; registry connections apply statement/lock deadlines; downstream tools stream with a decoded-byte limit; DT cancellation and lost-process reads retain uncertain dispatch state; service readiness uses shared URL validation; ontology/chat responses expose recovery IDs; workflow reads enforce owner or approval supervision and reject ordinary reads of historical ownerless records. Frontend recovery distinguishes DT records from telemetry/workflow records.

Nineteen focused Python regressions passed, including chunked response limits, malformed ports, event-loop heartbeat during cancelled database work, DT cancellation persistence, owner mismatch, matching owner and historical supervisory access. Run-tracking JavaScript checks passed. These are focused source-extracted route checks, not a live FastAPI/PostgreSQL/APIM integration run. Application dependencies remain uninstalled. Commit and push status is recorded in Git.
