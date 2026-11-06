# Ontology release versions

An ontology family is a stable human-assigned identity such as `AP242`. Each catalog artifact has its own `ontology_id`; its SHA-256 identifies exact retained content. A prefix is a namespace alias, not a version number.

## Operator sequence

1. Register the initial ontology or replacement through Import. Keep the old registration/publication while reviewing the replacement.
2. Open **Ontology Junction → Ontology lifecycle and knowledge graph publication**. Enter the approver, then expand **Ontology release versions**.
3. For the first release, enter family `AP242`, version `1.0.0`, select **First release**, leave the predecessor blank and supply Change notes.
4. For a replacement, use the same family and latest declared ontology ID as predecessor. Increase the major version for declared breaking changes, minor for additive changes, or patch for corrective changes. Example: `1.1.0` is additive after `1.0.0`; `2.0.0` is breaking after `1.1.0`.
5. Choose **Declare immutable release**. This records lineage; it does not approve compatibility, satisfy quality checks, publish a graph, deprecate the predecessor or migrate instances/mappings.
6. Run validation and scoped reasoning for the replacement artifact, review affected mappings/business queries, then use existing review, approval and publication controls. Verify the publication receipt separately.
7. Deprecate/retire the predecessor only after consumer migration is reviewed. Existing mappings keep their original ontology identity.

History is linear. Stale predecessors, reused versions, inconsistent increments and competing successors are rejected. Identical retries return the existing record. An artifact has one immutable release declaration. For corrections, retain it and register a reviewed replacement; no edit/delete-release API is provided.

## API and persistence

- `GET /api/v1/ontologies/{ontology_id}/releases` returns release, family history and `artifact_matches_release`. Legacy registrations return `release: null`; no version is invented.
- `POST /api/v1/ontologies/{ontology_id}/releases` accepts `family_id`, `version`, nullable `predecessor_id`, `change_kind`, `change_notes` and the existing approval identity contract. Read access alone cannot declare a version.

Example successor body; supply credentials through the existing secure access mechanism:

```json
{
  "family_id": "AP242",
  "version": "1.1.0",
  "predecessor_id": "previous_catalog_ontology_id",
  "change_kind": "additive",
  "change_notes": "Adds inspection characteristics; affected consumers reviewed.",
  "approved_by": "authorized-reviewer"
}
```

`backend/ontology_service/releases.py` uses the existing PostgreSQL `depo_registry`, namespace `ontology_releases_v1`; no new table/destructive schema migration is required. Ontology/family advisory locks and transactional `put_many` prevent conflicting assignments and partial history. The catalog lifecycle lock protects artifact inspection.

Publication checks a declared artifact hash before queueing and again before dispatch. Changed bytes cannot reuse that declaration. Publication records include declared family/version/predecessor/hash when present. Unversioned registrations retain their existing lifecycle behavior.

Semantica `/ontologies/versions` snapshot/compare APIs remain separate analysis facilities. Declarations do not rewrite `owl:versionIRI`/`owl:versionInfo` or prove semantic/consumer compatibility. `compatibility_verified` remains false. Existing instance mappings and learning hints remain bound to their source ontology/revision, with no automatic latest-version redirection.

## Recovery

Back up release records together with catalog records, immutable files, publication receipts and graph data. PostgreSQL restore alone cannot recover missing files or graph state. See [recovery qualification](audits/recovery-qualification-2026-10-29.md).
