# KerML Audit

Date: 2026-07-05

## Verdict

KerML support should be treated as a distinct SysML v2 foundation capability, not as the same thing as legacy SysML/XMI import.

KerML is the Kernel Modeling Language behind SysML v2. It provides application-independent modeling constructs with formal semantics, including relationships, annotations, namespaces, classification-based semantics, associations, and behaviors. For DEPO, KerML matters because it is the semantic substrate for future SysML v2 repository and textual-model ingestion.

## Current DEPO Status

Current code audit found:

- No explicit `.kerml` textual parser.
- No KerML-specific import workflow.
- No KerML-specific backend route.
- No KerML-specific OWL/Ontology projection service.
- Current MBSE handling is primarily XMI/SysML-style import and XMI-to-OWL generation.
- The SysML v2 API readiness endpoint exists, but repository synchronization/import is not implemented yet.

Therefore, KerML is not currently a supported runtime ingestion format.

## Why KerML Helps

KerML can improve DEPO in these areas:

- More precise semantic modeling than tool-specific XMI exports.
- Cleaner model element identity, namespace, relationship, and annotation handling.
- Better foundation for SysML v2 textual models.
- Better mapping to ontology classes/properties because KerML has formal language semantics.
- Improved validation of MBSE model structure before committing to Neo4j.
- Stronger bridge from MBSE models to OSLC AM, AP242, PLMXML, and GraphRAG.

## Target Architecture

KerML should be introduced as an optional MBSE connector layer:

```text
KerML / SysML v2 source
  -> parse or API fetch
  -> normalize namespaces, elements, memberships, relationships, annotations
  -> map KerML classifiers/features/relationships to ontology concepts
  -> validate semantic constraints
  -> write business model instances and semantic relationships to Neo4j
  -> expose through OSLC AM, GraphRAG, visualization, reports, and Semantic Bridge
```

## Suggested Normalized Model

```json
{
  "source_format": "kerml",
  "source_system": "sysml-v2-kerml",
  "external_id": "stable KerML element id or qualified name",
  "qualified_name": "package::element",
  "name": "element name",
  "element_type": "Class | Feature | Association | Behavior | Namespace | Annotation | Relationship",
  "namespace": "owning namespace",
  "classifier": "resolved classifier/type when present",
  "documentation": "comments or annotations",
  "properties": {},
  "relationships": []
}
```

## Ontology Mapping Guidance

Recommended mapping:

| KerML concept | DEPO ontology / graph target |
| --- | --- |
| Namespace / Package | Ontology module, vocabulary scope, or graph domain |
| Classifier / Class | `owl:Class` and business object type |
| Feature | `owl:DatatypeProperty` or `owl:ObjectProperty` depending on value/type |
| Association | Object property / graph relationship |
| Behavior | Function/process/activity node or class |
| Annotation / Documentation | Annotation property / provenance metadata |
| Membership / Ownership | containment or namespace relationship |
| Specialization | `rdfs:subClassOf` / semantic hierarchy edge |

## Implementation Recommendation

Do not add KerML UI until one of these is true:

1. The customer provides `.kerml` / SysML v2 textual files and expected outputs.
2. The customer exposes a SysML v2 API server whose payloads include KerML/SysML v2 abstract syntax.
3. A KerML parser library or grammar is selected and tested.

Minimum backend additions when ready:

- `backend/Services/kerml_parser_service.py`
- `backend/Services/kerml_ontology_projection_service.py`
- `backend/routes/kerml_routes.py` or extend `/api/v1/sysml-v2/*`
- Import workflow: `Connect SysML v2 / KerML source`
- Tests for namespace resolution, specialization, association, feature typing, annotations, and relationship projection.

## Release Guidance

For the current release:

- State that KerML is reviewed and planned as a SysML v2 semantic foundation.
- Do not claim KerML ingestion support.
- Keep XMI/MDXML import as the supported MBSE file path.
- Keep SysML v2 API endpoints as readiness/integration-plan endpoints only.

## Risk Notes

- KerML is formal and expressive; a naive XML/text parser will lose semantics.
- Relationship-like KerML elements should usually become graph relationships, not business-object nodes, unless they carry explicit identity or domain properties.
- Namespace and qualified-name handling must be deterministic to avoid duplicate classes and unstable graph IDs.
- Mapping KerML to OWL requires careful separation between classes, individuals, features, annotations, and relationships.
