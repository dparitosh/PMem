# Ontology creation and merge follow-up audit

## Scope

Reviewed local creation/publication, source resolution, automated merge completion, diagnostics and Admin session changes. This is a focused code audit, not complete customer release acceptance. No live customer database or APIM was accessed.

## Findings fixed in the working tree

Follow-up corrections: publication metadata offers OWL/existing RDF only, with SHACL/Both explicitly retained in registration-only mode and a pre-dispatch guard for older incompatible selections. Completed automatic merges dispatch a shared refresh once per run; direct automatic-apply responses also refresh unless held. Taxonomy falls back to retained RDF and uses that file for source inspection. Import statistics use validated publication receipt counts; malformed/negative counts fail receipt verification.

Validation: 16 backend tests and 28 frontend tests passed. These include publication transport, invalid receipts, missing original uploads, generation choices, visible publication counts, one-time merge refresh and standalone metadata form compatibility. Production build and whitespace checks passed; the build retains large-chunk warnings. Customer Neo4j/APIM acceptance remains pending.

### P2 — Selected generation mode is ignored by publication

`frontend/src/Components/DataImportPipeline.js:573` sends name/prefix/description/publication but not generationType or schemaType to engineering-workflows. The metadata form offers SHACL, OWL and Both; `backend/ingestion_service/schema_conversion.py:83` generates OWL and default shapes regardless of that selection. Enabling publication by default makes this inconsistency more frequent. Align the publication contract with the selected generation mode, or clearly limit the choices offered for that operation. Do not imply that a selected SHACL-only transformation was honored.

### P2 — Automated merge completion leaves ontology dropdowns stale

`frontend/src/Components/OntologyMapper.js:3013` records merge success without publishing the shared ontology-change event. The browser observes workflow status GET requests while registration runs server-to-server. The response interceptor cannot observe that registration. Additionally `frontend/src/utils/ontologyEvents.js:4` matches manual `/apply`, but not `/apply-automatic`. Refresh the shared ontology context once when a completed merge creates a new draft, without repeatedly triggering refresh on polling.

### P2 — Taxonomy retains the original-upload dependency

`backend/ontology_service/domain/taxonomy.py:154` still rejects an absent original file even when its converted semantic artifact exists. The reasoning resolver has been corrected, so the same ontology can merge successfully while taxonomy still fails. Use a shared resolver or implement the same artifact fallback with coverage for both paths.

### P2 — Publication counts are discarded by the import result

`frontend/src/Components/DataImportPipeline.js:626` reads `nodes_merged` from registration metadata and sets relationships to null. The publication receipt already carries resources/relationships, but the UI ignores them. A successful Neo4j publication can therefore show blank metrics. Populate publication statistics from the verified graph receipt, keeping registration-only statistics distinct.

## Confirmed safeguards and limits

- Failure messages are classified into safe static text; arbitrary upstream bodies are not retained by the new diagnostic helper.
- Publication requires a matching graph receipt; registration alone is not presented as published.
- The backend publication API remains opt-in; the UI defaults publication on and allows registration only.
- Automatic union produces a retained draft and does not promise graph publication.
- Existing customer failure details cannot be recovered from the old exception-only report.

These four findings are fixed locally in the follow-up. No P1 defect was confirmed in this focused pass. The absence of a confirmed P1 here does not certify customer release readiness.
