# SysML v2 API Client Audit

Date: 2026-07-04

## Verdict

The `Systems-Modeling/SysML-v2-API-Python-Client` package can help DEPO, but it should be treated as an optional SysML v2 repository connector rather than a replacement for the current XMI/MDXML parser.

Use it when a customer has a live SysML v2 API server that exposes projects, branches, commits, elements, relationships, and query results. Do not use it as the fix for large local XMI files; those still need the optimized streaming/parser and batched Neo4j import path.

## What It Adds

- Live repository sync from a SysML v2 API endpoint.
- Project, branch, commit, element, root, relationship, tag, and query-result access.
- Incremental import by commit or query instead of whole-file export/import.
- Better retry/resume behavior for connected model repositories.
- A cleaner bridge from SysML model elements to Neo4j, OSLC AM, ontology mapping, and GraphRAG.

## What It Does Not Add

- It does not parse local `.xmi`, `.mdxml`, or `.xml` files.
- It does not perform OWL reasoning.
- It does not replace Owlready2, RDFLib, SHACL, or Neo4j.
- It does not remove the need for semantic mapping from SysML elements to ontology classes/properties.
- It does not guarantee compatibility with every customer SysML repository implementation.

## Recommended DEPO Integration

Add an optional backend service:

`backend/Services/sysml_v2_connector_service.py`

Suggested flow:

```text
SysML v2 API
  -> projects / branches / commits
  -> elements / roots / relationships / query-results
  -> DEPO normalized import model
  -> Semantic Bridge mapping
  -> Neo4j instance graph
  -> OSLC / GraphRAG / visualization / reports
```

Suggested environment settings:

```env
SYSML_V2_API_ENABLED=false
SYSML_V2_API_BASE_URL=
SYSML_V2_API_TOKEN=
SYSML_V2_PROJECT_ID=
SYSML_V2_BRANCH_ID=
SYSML_V2_COMMIT_ID=
SYSML_V2_PAGE_SIZE=500
SYSML_V2_REQUEST_TIMEOUT_SECONDS=120
```

## Normalization Target

SysML v2 elements should be normalized into the same internal import contract used by XMI/PLMXML/STEP where possible:

```json
{
  "source_format": "sysmlv2",
  "source_system": "sysml-v2-api",
  "external_id": "element-id",
  "name": "element name",
  "element_type": "Requirement | PartDefinition | ActionUsage | ...",
  "owner_id": "owner element id",
  "documentation": "description or declared documentation",
  "properties": {},
  "relationships": []
}
```

Relationships should be written as semantic relationships, not as relationship nodes, unless the relationship itself has business identity or properties that must be preserved.

## UI Impact

If implemented, add one optional import source:

- Import page: `Connect SysML v2 repository`
- Fields: API base URL, project, branch, commit, saved query
- Preview: elements, relationships, unresolved references
- Commit: background/batched Neo4j load
- Semantic Bridge: map SysML model elements to ontology classes/properties

Do not add this UI until the backend connector is implemented and tested against a real SysML v2 server.

## Release Guidance

For the current release:

- Mark SysML v2 API integration as planned/optional.
- Keep current XMI/MDXML import as the supported file-based path.
- Keep large XMI performance work in the parser/import layer.
- Do not bundle the generated client until license and target server compatibility are reviewed.

## Risk Notes

- The referenced generated client shows older package metadata, so customer server compatibility must be verified against the customer OpenAPI spec.
- The repository includes LGPL/GPL licensing. Legal review is required before bundling it into a commercial release.
- Real customer servers will likely require authentication even if the generated sample docs show no authorization.


## KerML Relationship

KerML is the semantic kernel foundation for SysML v2, but DEPO does not currently parse `.kerml` textual files or project KerML abstract syntax directly into OWL/Neo4j. Current MBSE support remains XMI/MDXML file based plus SysML v2 readiness endpoints. See `docs/kerml-audit.md`.


## Generation Use

The SysML v2 API client can help with generation only when the target is a live SysML v2 repository/service. It is not a local `.sysml` or `.kerml` file generator.

Recommended split:

- Local file generation: DEPO should generate `.sysml` / `.kerml` text deterministically from ontology, graph, and reviewed LLM suggestions.
- Repository generation: the SysML v2 API client can be used later to create/update projects, branches, commits, queries, and tags, and to publish generated model data if the customer's SysML v2 server supports the required commit payloads.
- Validation: generated SysML/KerML should be validated before publishing. The generated client alone does not provide semantic validation.

Current DEPO status: SysML v2 generation is not implemented. The app can export OWL/RDF/TTL/JSON-LD today, and SysML/KerML generation should be added as a separate `SysMLGenerationService` before exposing it in the UI.
