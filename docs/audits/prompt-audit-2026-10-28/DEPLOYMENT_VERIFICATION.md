# Installed application verification — 2026-10-28

Deployment target: `D:\GenAI_Projects\Apps\PMem`.

The managed frontend, ten APIs and three workers were stopped before the code update. PostgreSQL and the graph database remained running. The updated frontend was built using the installation's existing routing configuration and Node.js 24.22.0. Managed startup checked the existing PostgreSQL schema and credential profiles; all 17 supplied application profiles were unchanged. Baseline provisioning/publication was skipped. LLM features remained disabled.

Initial backup: `logs/prompt-audit-update/20261028-060623-6b006370b362465ca48dcb569eac5057`.

Follow-up backup: `logs/prompt-audit-update/20261028-061802-fe5a790266cf4f73b8a426abb2d40b42`.

Customer `.env.local`, frontend environment files, databases, uploaded artifacts, dependency runtimes and the unrelated AOI dependency lock were preserved. Removed standalone Owlready2 files were backed up before removal. No external IIF installation was modified.

## Additional browser-discovered defect: DEP-01

The live browser intermittently received `Local session authority is unavailable` after startup even though service readiness and direct delegated-session diagnostics passed. The broker used a two-second upstream read timeout. The UI then mounted service-reading children without a successful initial local sign-in, causing secondary authorization errors.

A temporary loopback authority returning a valid delegate after 2.3 seconds reproduced HTTP 503 before the fix. The same case passes after the fix. The broker now uses a bounded 12-second read allowance within its existing response/request limits. Origin, loopback, cookie, scope and response-size controls are retained. Logs capture only stage, exception class and upstream status, never keys, tokens or upstream response bodies.

The browser boundary now holds service-reading children until initial local sign-in succeeds. Manual mode remains available as before. Explicit sign-out stays disconnected, and existing mounted workflows remain retained during ordinary renewal/reconnect handling.

## Executed tests

- 283 deployed backend tests passed: core prompt/agent/memory/recommendation/Companion/MCP selection plus 21 Semantica migration cases.
- Seven deployed broker tests passed, including the real slow loopback-authority reproduction and origin/scope/expiry controls.
- 96 deployed frontend tests passed, covering startup access, sign-out, reconnect, renewal, investigations, recommendations, inference and citations.
- The installed production frontend build passed.
- The direct delegated browser-session diagnostic passed across all ten services and the ontology health/list reads after the final restart; it disconnected its temporary test session.

The 283-case core/Semantica selection ran before DEP-01; the seven broker and 96 frontend cases ran against the final follow-up deployment. These are separate selections, not a single 290-case run.

## Live browser results and limits

All three Recommendations tabs completed direct graph analysis for an explicitly selected PLMXML assembly. Similar Parts returned ten bounded candidates; Change Impact reported unknown impact when no eligible dependency path was found, and Process Context disclosed the missing direct process links. No shared decision policy is configured in this installation. These results do not establish interchangeability, engineering approval or complete graph coverage.

Taxonomy loaded automatically with the selected AP242 ontology. Semantic Bridge loaded the retained imported instance list. API revalidation retained the selected ontology, instance and Bridge tab. No approval, publication or model inference was invoked.

A large Mapping Vocabulary view loaded 5,000 mapping edges, but subsequent browser-control commands timed out. Reload restored the page and Bridge navigation worked. The cause of that timeout is unconfirmed; large-vocabulary responsiveness remains a qualification limit. The service log also contains a nonfatal missing optional `source_format` property warning. These observations must not be represented as a complete UI performance pass.

See `deployment-verification.json` for final live checks, source hashes, frontend asset identity and browser observations. Browser and service smoke checks do not qualify live-model reasoning: inference remains disabled, and the open risks in `DELIVERABLE_STATUS.md` still apply.
