# DEPO memory gap analysis

Read with the [baseline evidence inventory](DEPO_ARCHITECTURE_AUDIT.md). “Missing” means not established in the inspected paths, not proof of repository-wide absence. Live deployment is unverified.

| Layer | Present evidence | Remaining gap | Status / priority |
|---|---|---|---|
| Working | E01–E03, E05: owner sessions, pinned scope, bounded observations, deadlines, persisted planning | G01 common context envelope; byte truncation is not token-aware semantic compression; explicit handoff compatibility/version policy | Partial / P0 |
| Episodic | E02–E04: plans, observations, failures, traces, durable workflow records | G02 mandatory-versus-optional evidence distinction; cross-owner correlation/read projection and governed retention | Implemented core, partial common access / P1 |
| Semantic | E04, E06, E07, E10: mapping facts, graph evidence, Semantica context and policy | G03 valid/revoked/superseded fact filtering; G05 representation/source synchronization contract; G07 retrieval evaluation | Partial / P1 |
| Procedural | E03, E08: registered tools/workflows, frozen execution definition and digest | G06 approved skill versions, test evidence, compatibility/deprecation and explicit promotion gate | Partial / P2 |
| Forgetting / governance | E01, E04, E09: expiry/pruning, retention, legal hold, purge intent | G04 coordinated memory deletion/invalidation, policy matrix, legal hold applicability and completion receipts | Partial / P1 design, P2 rollout |

## Security and correctness distinctions

A tenant/project scope string is not a substitute for an authenticated principal and resource authorization. A shared application key cannot distinguish individual users by itself. An ontology ID is a selected resource, not proof of entitlement.

A successful read is evidence that the service returned a result, not proof that the result is complete or semantically correct. Current goal completion excludes truncated observations; preserve that behavior when introducing compression.

Matching confidence is not correctness probability (E10). Failed actions are useful diagnostic episodes; never promote their output into approved ontology facts or executable procedures automatically.

Session expiry is access/conversation lifecycle. It must not silently delete required publication audit evidence. Conversely, retaining an audit event does not justify retaining an unrestricted copy of sensitive prompt text.

## Defect versus enhancement

No failing regression was reproduced in this review. G03 is a concrete absence of lifecycle predicates in the inspected fact-read query; the impact on live data needs a controlled fixture. G01/G02/G04–G06 are integration/design gaps. G07 is an evidence gap. Prior frontend changes and earlier audit findings are baseline work, not newly implemented fixes here.
