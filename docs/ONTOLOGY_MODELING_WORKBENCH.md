# Superseded Modeling Workbench Note

This document describes the earlier custom Sirius-Web-inspired DEPO modeling workbench. That approach is superseded by the actual Sirius Web integration documented in `docs/SIRIUS_WEB_INTEGRATION.md`.

For release planning, use Sirius Web as the modeling workbench and keep DEPO Graph Explorer for graph analysis/traceability. Do not use this document as the active Modeling page specification unless the team explicitly decides to revive the custom DEPO-native workbench.

---
# Ontology Modeling Workbench

Sirius-Web-inspired modeling surface for ArchiMate, MBSE, UAF, and PLM knowledge-graph editing without adding a separate modeling server.

## UI Structure

- Left panel: Model Explorer tree: `Project -> Package -> Element`.
- Center: Editable SVG diagram canvas for nodes and relationships.
- Top palette: creates `Capability`, `OperationalActivity`, `Resource`, `Performer`, `Requirement`, `Function`, `Interface`, `Product`, `Part`, and `Document`.
- Right panel: selected node/link properties with editable JSON key-values.
- Bottom validation panel: missing required properties, orphan nodes, duplicate identifiers.
- Search: label, type, property key, property value, and graph-slice search.

## Optional Metamodel JSON

The Modeling Workbench loads an optional metamodel configuration from:

`backend/config/modeling_metamodel.json`

It currently defines OWL, UAF, SysML, ArchiMate, and PLM profiles, allowed element types, relationship types, required properties, and UI colors. If the file is missing or invalid, backend defaults are used.

## Neo4j Storage Pattern

Dynamic labels and relationship types are avoided for safer parameterized Cypher.

```cypher
(:ModelElement {
  uid,
  label,
  name,
  type,
  project,
  package,
  ...domainProperties
})

(:ModelElement)-[:MODEL_REL {
  type,
  label,
  ...relationshipProperties
}]->(:ModelElement)
```

Use `elementId()` for UI identity and update/delete operations. Use `uid` for stable business identity.

## API Contracts

Base path: `/api/v1/modeling`

### Metamodel

`GET /metamodel`

Returns allowed element types, relationship types, and required properties.

### Indexes

`POST /indexes`

Creates Neo4j indexes:

```cypher
CREATE INDEX model_element_uid IF NOT EXISTS FOR (n:ModelElement) ON (n.uid);
CREATE INDEX model_element_project IF NOT EXISTS FOR (n:ModelElement) ON (n.project);
CREATE INDEX model_element_type IF NOT EXISTS FOR (n:ModelElement) ON (n.type);
CREATE INDEX model_element_label IF NOT EXISTS FOR (n:ModelElement) ON (n.label);
```

### Graph

`GET /graph?project=Digital Engineering Model&search=&limit=500`

Response format:

```json
{
  "nodes": [{ "id": "elementId", "label": "Monitor Health", "type": "Function", "properties": {}, "x": 460, "y": 420 }],
  "links": [{ "id": "elementId", "source": "nodeId", "target": "nodeId", "type": "SATISFIES", "properties": {} }],
  "counts": { "nodes": 6, "links": 5 }
}
```

### Tree

`GET /tree?project=Digital Engineering Model`

Returns `Project -> Package -> Element` hierarchy.

### Search

`GET /search?q=Safety&project=Digital Engineering Model&limit=50`

Searches label, name, type, property names, and property values.

### Context

`GET /context/{elementId}?depth=1&limit=300`

Returns selected root plus connected one-hop context. Depth is capped at 2.

### Nodes

`POST /nodes`

```json
{
  "project": "Digital Engineering Model",
  "package": "Requirements",
  "type": "Requirement",
  "label": "Safety Requirement",
  "uid": "req:safety",
  "properties": { "text": "System shall remain safe." }
}
```

`PUT /nodes/{elementId}` updates properties.

`DELETE /nodes/{elementId}` detaches and deletes the node.

### Links

`POST /links`

```json
{
  "source": "sourceElementId",
  "target": "targetElementId",
  "type": "SATISFIES",
  "properties": { "rationale": "Design function satisfies requirement." }
}
```

`PUT /links/{elementId}` updates relationship properties.

`DELETE /links/{elementId}` deletes the relationship.

### Validation

`GET /validation?project=Digital Engineering Model`

Returns validation issues:

- missing required properties
- orphan nodes
- duplicate `uid`

### Sample Seed

`POST /seed`

Creates a small model:

- Mission Capability
- Operate System
- Safety Requirement
- Monitor Health
- Controller Assembly
- Relationships: `REALIZES`, `ALLOCATED_TO`, `SATISFIES`, `PERFORMS`, `CONTAINS`

## GraphRAG Context Use

The `/context/{elementId}` endpoint is GraphRAG-ready. It returns a bounded, connected model slice suitable for prompt context, change impact, traceability explanation, and assistant grounding.

## Files

- Backend service: `backend/Services/modeling_service.py`
- Backend routes: `backend/main.py`
- Frontend page and centralized graph-state hook: `frontend/src/pages/ModelWorkbenchPage.js`
- Frontend styles: `frontend/src/pages/ModelWorkbenchPage.css`
- Frontend API config: `frontend/src/config.js`
- Frontend API client: `frontend/src/services/apiClient.js`
- Navigation: `frontend/src/app/navigation.js`
- Optional metamodel JSON: `backend/config/modeling_metamodel.json`
- Routing: `frontend/src/App.js`

## Sirius-Web-Inspired Feature Coverage

Implemented in this app as a pragmatic ontology/Neo4j modeling workbench, not as a full Eclipse Sirius Web clone:

- Project and model explorer tree: `Project -> Package -> Element`.
- Representation browser: Diagram, Table, Tree, Form, and Validation views over the same model data.
- Viewpoint selector: MBSE, UAF, SysML, ArchiMate, and PLM profiles from metamodel configuration.
- Diagram semantic views: MBSE Traceability, UML/Component, BPMN Process, and ArchiMate Layers.
- Diagram tool strip: select/connect/expand intent, zoom controls, fit, and arrange refresh.
- Palette-driven element creation for domain object types.
- Property/form editor for selected nodes and relationships.
- Validation view and inline validation summary.
- Search over labels, types, property keys, property values, and model slices.
- Bounded 1-hop expansion using the modeling context API.

Not yet full Sirius parity:

- Collaborative multi-user editing/session locking.
- Declarative viewpoint DSL editor.
- Advanced edge routing and freehand diagram layout persistence.
- Undo/redo command stack persisted on the backend.
- Rich semantic creation tools per metamodel rule.
- Server-side representation registry/versioning.

These are intentionally separate from Graph Explorer. Graph Explorer remains knowledge-graph exploration; Modeling Workbench is semantic model authoring.
