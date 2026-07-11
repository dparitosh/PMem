# SKOS Taxonomy and SWRL-Style Reasoning

This app now has a focused semantic layer for SKOS taxonomy and SWRL-style rule handling without assuming Neo4j can execute SWRL natively.

## Architecture

- OWL classes and properties remain owned by the Owlready2/RDFLib ontology services.
- SKOS concept schemes and concepts are stored separately as `SkosConceptScheme` and `SkosConcept`.
- Instance data remains separate as imported business objects and relationships.
- Rules are represented as `SemanticRule`, `RuleExecution`, and inferred fact relationships.
- Inferred facts are distinct from asserted facts through `asserted=false`, `inferred=true`, `ruleId`, `sourceFacts`, `executionId`, `timestamp`, and `version`.

## APIs

All endpoints are under `/api/v1/ontology`.

- `POST /semantic/skos/validate`
- `POST /semantic/skos/search`
- `POST /semantic/skos/traverse`
- `POST /semantic/skos/storage-plan`
- `POST /semantic/rules/validate`
- `POST /semantic/rules/execute-preview`
- `POST /semantic/rules/materialization-plan`

The storage and materialization endpoints return parameterized Cypher plans. They do not execute unsafe string-concatenated Cypher.

## SKOS Payload

```json
{
  "scheme": {
    "scheme_id": "depo-taxonomy",
    "pref_label": "DEPO Taxonomy",
    "definition": "Controlled vocabulary for digital engineering terms.",
    "version": "1"
  },
  "concepts": [
    {
      "concept_id": "bearing",
      "pref_label": "Bearing",
      "alt_labels": ["SKF bearing"],
      "definition": "Rotating component used in motor assemblies.",
      "broader": ["asset"],
      "related": ["failure-mode"],
      "mappings": {
        "exactMatch": ["ap242:Part"]
      }
    }
  ]
}
```

## SWRL-Style Rule Payload

```json
{
  "rule": {
    "rule_id": "change-impact",
    "version": "1",
    "use_case": "change_impact",
    "expression": "satisfies(?req, ?func) ^ allocatedTo(?func, ?part) -> impactedBy(?req, ?part)"
  },
  "facts": [
    {"id": "f1", "subject": "REQ-001", "predicate": "satisfies", "object": "Function-01"},
    {"id": "f2", "subject": "Function-01", "predicate": "allocatedTo", "object": "Part-99"}
  ],
  "execution_id": "exec-001"
}
```

## Rule Execution Model

The rule engine supports a safe application-level subset:

- Class atoms: `Requirement(?x)`
- Object/data property atoms: `satisfies(?req, ?func)`
- Built-ins: `swrlb:equal`, `swrlb:notEqual`, `swrlb:contains`, `swrlb:startsWith`, `swrlb:greaterThan`, `swrlb:lessThan`

Unsupported rules are flagged instead of producing incorrect inferences.

## Neo4j Storage Pattern

Stable business identifiers are used for persistence:

- `schemeId`
- `conceptId`
- `ruleId`
- `businessId`
- `executionId`

`elementId()` remains a runtime/UI reference only.

Inferred facts are materialized as `INFERRED_FACT` relationships with provenance properties. Stale inferred facts for a rule version are removed before the next approved materialization plan is applied.

## UI

Ontology Junction already has an Inference Workbench. It now includes a compact SWRL-style rule editor that:

- accepts body/head expressions,
- validates variables and built-ins,
- displays IF/THEN preview,
- shows correction issues.

Taxonomy/Owl views continue to render Owlready2-derived class/property semantics. A full SKOS concept management screen is still a separate UI enhancement.

## Gap Analysis

Implemented:

- SKOS concept scheme and concept normalization.
- SKOS preferred labels, alternate labels, definitions, hierarchy, related concepts, and mappings.
- Duplicate label and cycle detection.
- Semantic search over preferred labels, synonyms, definitions, hierarchy, and mappings.
- SWRL-style parsing, validation, IF/THEN preview, safe execution, provenance, idempotency, and stale inferred fact cleanup plans.
- Parameterized Cypher storage/materialization plans.
- Backend tests for traversal, synonym search, rule parsing, validation, provenance, idempotency, and cleanup.

Not yet implemented:

- Full persisted SKOS CRUD UI.
- Human approval workflow that executes the returned materialization plans.
- OWL reasoner-backed SWRL execution for rules outside the safe subset.
- SHACL generation from approved SWRL-style rules.

## Files

- `backend/Services/semantic_taxonomy_service.py`
- `backend/Services/swrl_reasoning_service.py`
- `backend/routes/ontology_routes.py`
- `frontend/src/config.js`
- `frontend/src/services/apiClient.js`
- `frontend/src/Components/OntologyMapper.js`
- `backend/tests/test_semantic_taxonomy_service.py`
- `backend/tests/test_swrl_reasoning_service.py`
