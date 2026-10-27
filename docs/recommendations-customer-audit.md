# Recommendations customer audit

This review covers Change Impact, Similar Parts and Process Context in both direct graph and existing Graph Analyst modes. The checks below use isolated test records and mocked transports. They do not certify a customer's credentials, model, database contents or deployed build. No finite audit guarantees that every bug has been found.

## Defects corrected

| Failure class | Correction |
| --- | --- |
| HTTP browser compatibility | Generate investigation UUIDs using cryptographic browser randomness when `randomUUID` is unavailable. |
| Invalid inputs | Validate Similar Parts limits in both modes; an empty or invalid limit no longer disables Change Impact or Process Context. Bound selected object names to 500 characters. Ignore non-text graph prefill names. |
| Service contracts | Report malformed tool catalogs, result envelopes, evidence rows and retained agent records without crashing the page or presenting a successful analysis. |
| Unusable agent completion | Explain when a completed run lacks usable evidence bound to the current analysis, object, limit and scope. Retain recovery identity after an uncertain submission. |
| Access and session state | Pause after rejected API access, cancel obsolete direct requests, clear stale displayed results, and resume recovery only after access verification. |
| Process relevance | Classify processes from declared or mapped business types rather than words in their names. Exclude schema/publication storage nodes from process neighbors. |
| Process scope and performance | Apply ontology ID/prefix filtering before limiting neighbors, use the bounded graph query timeout, deduplicate process identities, and expose truncation and incomplete coverage. |
| Business presentation | Describe recorded dependency paths and process links without implying calibrated risk, verified manufacturing sequence, whole-graph completeness or approval. |

## Regression coverage

- Inputs: blank object, graph identity prefill and scope, manual edits, limits outside 1–50 or fractional, switching analyses with an invalid hidden limit.
- Execution: correct service routing, direct/agent separation, evidence citations, controller tool contract and read-only bindings, lost-response recovery, cancellation, late responses and failures, navigation and session changes.
- Dependencies: unavailable readiness, service-specific holds, malformed tool catalog, rejected access, graph driver failure, unavailable decision-policy/audit store, policy changes and review holds.
- Business evidence: units, engineering property conflicts, missing coverage, typed candidate selection, ambiguous source lookup, bounded dependency paths/cycles, configuration/effectivity uncertainty, scope isolation, process type matching and result deduplication.
- Presentation: empty and malformed responses, unusable completed goals, missing process context, limited graph slices, accessible dependency inspection, and absence of false approval/severity claims.

## Customer acceptance still required

Validation for this change: **64 frontend tests passed** across seven test files; **73 backend tests passed** across six test files. The production Vite build and `git diff --check` passed. Existing React test-utils/Python deprecation warnings and Vite large-chunk warnings remain; none failed these checks. This run did not exercise a live customer browser, LLM or database.

Apply the complete matching source release and use `update-depo.ps1` with the customer's existing environment file so the frontend is rebuilt and normal release checks run. Do not deploy only a developer's configured `dist` folder. Preserve credentials, database contents and retained tasks.

On the customer URL, refresh the browser and verify access. For each analysis, run both direct and agent modes with a known scoped business object. Check an ambiguous name, a missing object, a record without engineering properties, and a bounded large result. Compare displayed names, properties, conflicts and path identities with retained source evidence. Verify polling/cancellation after navigating away and returning. Agent mode also needs a working configured model; direct mode does not.

The reported customer ontology 403 has no verified root cause yet. The import registry 503 has a separate sidecar-discovery correction. Neither is repaired by bypassing authentication, clearing history or assuming an LLM key change. Keep customer request IDs and inspect the matching service logs when these persist.
