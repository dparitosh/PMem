# Ontology-Driven Modeling Framework

This application now separates modeling concerns into reusable layers instead of embedding ArchiMate/UAF/PLM logic directly in React pages.

## Layers

- React UI: `frontend/src/Components/*`, `frontend/src/pages/ModelWorkbenchPage.js`
- Diagram engine: `frontend/src/diagram/engine/diagramEngine.js`
- Diagram registry: `frontend/src/diagram/registry/diagramRegistry.js`
- Layouts/rendering adapters: `frontend/src/diagram/layouts`, `frontend/src/adapters/reactFlowAdapter.js`
- Semantic mapping: `frontend/src/config/semanticMappings`
- Ontology-independent validation: `frontend/src/validation/diagramValidation.js`
- Neo4j persistence: `backend/Services/modeling_service.py`
- Agentic AI proposals/audit: `backend/Services/agentic_modeling_service.py`

## Common Graph Format

```js
nodes: [{ id, label, type, properties, metadata, style }]
links: [{ id, source, target, type, properties, metadata }]
```

The backend returns frontend-ready graph JSON and uses `elementId()` for Neo4j IDs.

## Adding a New Diagram Type

1. Add a config object in `frontend/src/config/diagramTypes/index.js`:

```js
export const myDiagramType = {
  id: 'my-profile',
  label: 'My Profile',
  renderer: 'svg-fallback',
  explorerRenderer: 'cytoscape-or-d3',
  palette: ['Requirement', 'Function', 'Part', 'Relationship'],
  layers: ['requirements', 'functional', 'product'],
  allowedRelationships: ['SATISFIES', 'ALLOCATED_TO'],
  requiredProperties: { default: ['name'], Requirement: ['name', 'text'] },
};
```

2. Register it by adding it to `diagramTypeConfigs`.
3. Add semantic class/property mappings in `frontend/src/config/semanticMappings/index.js`.
4. Use existing backend CRUD APIs; do not add React hardcoding for the new profile.

## Backend APIs

- `GET /api/v1/modeling/graph`
- `GET /api/v1/modeling/tree`
- `GET /api/v1/modeling/context/{element_id}`
- `POST /api/v1/modeling/nodes`
- `PUT /api/v1/modeling/nodes/{element_id}`
- `DELETE /api/v1/modeling/nodes/{element_id}`
- `POST /api/v1/modeling/links`
- `PUT /api/v1/modeling/links/{element_id}`
- `DELETE /api/v1/modeling/links/{element_id}`
- `GET /api/v1/modeling/validation`
- `POST /api/v1/modeling/agent/proposals`
- `GET /api/v1/modeling/agent/proposals`
- `POST /api/v1/modeling/agent/proposals/{proposal_id}/approve`
- `POST /api/v1/modeling/agent/proposals/{proposal_id}/reject`

## Agentic AI Safety Model

Agentic AI creates proposals only. It separates:

1. Proposal
2. Validation
3. Human approval/rejection
4. Explicit execution through safe CRUD/import APIs

It does not execute arbitrary generated Cypher.

## React Flow Status

`@xyflow/react` / React Flow is not currently installed in `frontend/package.json`. The framework includes `frontend/src/adapters/reactFlowAdapter.js` so migration is isolated once the dependency is approved and installed.

Recommended next step:

```bash
cd frontend
npm install @xyflow/react
```

Then replace the active SVG fallback canvas with a React Flow renderer under `frontend/src/diagram/renderers` without changing semantic mapping, validation, or backend APIs.

## Remaining Gaps

- Active `ModelWorkbenchPage.js` still uses the SVG fallback renderer for release safety.
- Full undo/redo is not yet implemented; add it in the diagram engine state layer when React Flow is introduced.
- Agent proposal execution is intentionally not automatic; approved proposals must be mapped to explicit safe CRUD/import operations.
- Unstructured ingestion can call the same semantic mapping layer, but deeper extraction quality still depends on configured OCR/chunking/LLM services.


