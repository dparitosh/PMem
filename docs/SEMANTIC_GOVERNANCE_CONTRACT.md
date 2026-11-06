# Semantic Governance Contract

The metadata registry is the single lifecycle boundary for semantic assets:
ontology releases, namespaces, mapping packs, SHACL rule sets, SKOS schemes,
and data-product semantic contracts. It does not duplicate the graph store,
artifact store, or data catalog; those systems retain their operational records
and reference the approved registry asset.

## Required identity and release fields

Every registry asset has a stable `asset_id` and `persistent_id`, name,
definition, asset type, owner, steward, lifecycle status, and semantic `version`.
Optional semantic release fields are `namespace_uri`, `namespace_prefix`,
`compatibility_status` (`compatible`, `breaking`, or `unknown`),
`replaces_asset_id`, `ontology_uri`, and `implementation_ref`.

An approved release requires both a steward and an `approval_evidence` locator.
A deprecated or retired release requires a `deprecation_reason`. These evidence
fields are stored on the asset and on the lifecycle audit event.

## Lifecycle

```text
draft -> in_review -> approved -> deprecated -> retired
                   ^           |
                   |-----------|
```

An approved release may return to `in_review` for correction. All lifecycle
transitions require an actor. Approval, deprecation, and retirement additionally
require their respective evidence. Direct PATCH updates cannot alter lifecycle
state; they must use the transition endpoint so that previous state, actor,
comment, changed fields, and evidence are audit-recorded.

## Integration boundary

1. A mapping pack or ontology release is registered as a draft asset with its
   namespace, persistent identifier, source artifact, and compatibility status.
2. A steward moves it through review and approval.
3. CEIM publication and data-product packaging must reference the approved
   `asset_id`/version in their manifest; graph publication remains a separate,
   approval-gated operation.
4. A superseding release uses `replaces_asset_id`; a deprecated release provides
   a replacement and reason where applicable. Consumers may therefore resolve a
   supported release without guessing from file names.

The service is exposed at `/api/v1/metadata-registry/assets` by the ontology
service and advertised in its OpenAPI/OData service catalogue. It remains
database-backed through the configured graph registry; production access control
and database backup policy are deployment responsibilities.
# Live acceptance record

On 2026-09-03 the configured local registry, CEIM and graph services completed
a governed publication acceptance test. A semantic release was created as
`draft`, transitioned to `in_review`, then `approved` with approval evidence,
and resolved by CEIM before a SHACL-conformant graph publication. The graph
projection contained two resources and one relationship. A separate draft
release was rejected as an unapproved semantic reference before graph mutation.
