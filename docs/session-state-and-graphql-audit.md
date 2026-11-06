# Session, state and GraphQL audit

## Separate lifetimes

The same codebase serves multiple processes. Shared source does not make their running environment, credential-store connection, listener or process version identical. Access failures require the failing service's request ID and configuration; a timeout is not proof that a key is invalid.

| State | Owner | Expiry/reconnect behavior |
| --- | --- | --- |
| Application API credential profile | Central credential store and each service's authorization checks | A rejected profile is distinct from an unavailable LLM provider. Do not rotate credentials to cure a request timeout. |
| Delegated browser session | Server-issued, bounded and revocable session; `serviceAuth.js` owns its browser lifetime | Activity can renew within the server's absolute lifetime. Hidden/background traffic does not keep it alive indefinitely. Expiry clears delegated credentials and requires reconnect/recovery. |
| In-flight REST, GraphQL or agent HTTP request | Shared `requestSession.js` generation and cancellation tracking | Expiry, logout, credential change and replacement cancel obsolete requests. Late responses cannot become current-session results. |
| Companion conversation ID | Server-issued retained conversation, scoped to deployment and request context | It is not an API credential. Reconnect must reauthorize history; late streams or sample responses cannot replace the current conversation ID. |
| Agent or publication workflow | Retained server run, submission identity and receipt | Browser expiry does not cancel a server-accepted operation. Preserve references, reload authorized status, and reconcile uncertain writes before another submission. |
| Ontology/tab selection and evidence | Ontology provider and capability-specific panels | Clear stale evidence, approval selection and old inference/validation results on replacement. Reload using current access. Retained task references do not grant permission to read them. |

## Confirmed defects corrected

1. Agent HTTP requests lacked the credential-generation guard already used by the main API client. Both now share one guard; obsolete successes and errors are discarded before publication notifications or global auth rejection.
2. A delayed 403 for an old delegated session could trigger a global access-rejected banner after a successful reconnect. Only the current delegation can trigger that rejection path.
3. Read-goal expiry handling deleted pending submission bookmarks. Expiry and reconnect now preserve references and stop active requests; recovery reuses the submission ID only after user action. Explicit disconnect still clears local bookmarks.
4. Session replacement was not handled consistently by ontology registry, imported-instance selection, merge/inference workspace, rule validation, Semantic Bridge and workflow task views. These now invalidate their corresponding evidence/request state.
5. Companion cancellation did not immediately release its busy state on replacement. Its session-retry branch and sample-query loader could also adopt a late conversation ID. Cancellation now releases controls, and old responses are prevented from adopting state.
6. Shell access verification could finish after credential replacement. Replacement now cancels that verification before it can display an obsolete success.

## GraphQL's role

`frontend/src/services/graphApi.js` sends the named `ContextualSubgraph` query to `POST /api/v1/graphql` through the main API client. It supplies read authorization, import/ontology scope and cancellation. The query is an HTTP POST because it carries a query document; it is not a graph mutation.

The backend authenticates with `graph_read_identity`, applies document/variable/field/depth/cost bounds, and executes the read-only schema. Resolver failures are sanitized. Frontend GraphQL errors are not accepted as successful partial contextual graphs. Authentication failures are propagated; the client does not fall back to another endpoint to evade them. GraphQL uses the same request-session guard as REST. It does not own agent memory, browser login, conversation history, approvals or publication receipts.

## Verification and remaining acceptance

Regression checks include expiry/renewal, delayed old-token rejection, logout during renewal, old agent responses after reconnect, uncertain submission recovery, ontology refresh and selection invalidation, Companion session retry/sample races, GraphQL scope/cancellation/error propagation, rule validation and late access verification.

Validation: the cross-feature frontend run covered 226 tests across 21 files. It initially passed 224 and found two obsolete merge-reviewer selectors; after correcting them to the current accessible label, all 13 tests in that file passed, including both previously blocked scenarios. Backend session/GraphQL checks passed 37 tests across four files. The production build and diff whitespace check passed. Existing React test warnings and Vite large-chunk warnings remain. These are isolated regression results, not live customer acceptance.

Customer-specific 403 errors remain undiagnosed without the failed service's response/request ID and running configuration. Local regressions do not establish customer routing, shared-store connectivity, long-duration browser behavior, provider availability or acceptance against real customer data. Retest all Ontology Junction tabs, Companion and agent workflows on the customer URL after deploying the matching frontend/backend and rebuilding with the retained customer environment. Never delete history, disable auth or increase session lifetime merely to hide these failures.
