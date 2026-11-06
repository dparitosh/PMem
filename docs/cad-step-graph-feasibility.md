# CAD STEP Graph Feasibility

Date: 2026-07-04

## Reference

`steptools/STEPGraph` is a small C++ reference application that visualizes STEP files as a dynamic graph using Microsoft Automatic Graph Layout. It is useful as a concept reference for showing STEP entity references, but it is not a direct fit for the current DEPO stack because DEPO uses Python parsing, Neo4j storage, OWL/RDF export, and React/D3 visualization.

## Current DEPO Capability

The current application already has the core ingredients needed for a STEPGraph-like CAD graph:

- STEP/STPX parser support in `backend/Services/step_parser.py`
- STEP import routing in `backend/Services/unified_data_import.py`
- AP242 entity normalization
- STEP entity IDs such as `#123`
- entity type extraction
- raw argument preview
- `ref_ids` extraction for STEP cross references
- STPX parent-child hierarchy extraction
- PMI extraction for dimensions, tolerances, datum, annotations, and surface finish
- AP242 OWL/RDF export in `backend/Services/owl_step_engine.py`
- batch Neo4j relationship writing for `REFERENCES`
- batch Neo4j relationship writing for STPX `PARENT_OF`

## Feasibility Verdict

Feasible: yes.

Recommended implementation: add a dedicated CAD STEP graph projection rather than mixing raw STEP entity-reference graphing into the existing business-object contextual graph.

Reason: STEP files contain many low-level representation, topology, geometry, placement, and measure entities. If all of those are shown in the normal Graph Explorer full graph, the user gets a dense technical graph instead of meaningful product context.

## Recommended Graph Views

1. Business CAD graph
   - Product
   - ProductDefinition
   - ProductDefinitionFormation
   - Assembly usage
   - Part/assembly structure
   - Requirements/process/manufacturing traceability when linked

2. PMI graph
   - dimensions
   - tolerance values
   - datum features
   - geometric tolerances
   - measured/toleranced features

3. Raw STEP reference graph
   - all STEP entities as nodes
   - `REFERENCES` edges based on `#id` references
   - intended for expert/debug use only

4. Geometry/topology technical graph
   - shape representation
   - advanced face
   - edge loop
   - vertex/curve/surface references
   - should be filtered and paged because it can be very large

## Neo4j Modeling Recommendation

Keep these layers separate:

- `(:StepEntity)` for raw STEP instance records
- `(:CadBusinessObject)` or existing AP242 typed labels for product/part/assembly objects
- `(:PMIAnnotation)`, `(:Dimension)`, `(:Datum)`, `(:GeometricTolerance)` for semantic PMI
- `(:GeometryEntity)` / `(:TopologyEntity)` for low-level CAD geometry if needed

Relationship types:

- `REFERENCES` for raw STEP `#id` references
- `PARENT_OF` for STPX XML hierarchy
- `ASSEMBLY_USES` or normalized AP242 assembly relationships for business graph
- `MEASURES`, `TOLERANCES`, `HAS_DATUM`, `APPLIES_TO_FEATURE` for PMI semantics

## API Recommendation

Add a dedicated API family:

```text
GET /api/v1/cad/step/{import_id}/graph?view=business
GET /api/v1/cad/step/{import_id}/graph?view=pmi
GET /api/v1/cad/step/{import_id}/graph?view=references
GET /api/v1/cad/step/{import_id}/graph?view=geometry
GET /api/v1/cad/step/{import_id}/node/{node_id}/neighbors?hops=1
```

Return the same graph payload contract used elsewhere:

```json
{
  "nodes": [],
  "relationships": []
}
```

## UI Recommendation

Add this as a CAD-specific graph mode, not as the default Graph Explorer mode:

- Business
- PMI
- Raw References
- Geometry

Default should be Business. Raw References should be opt-in because it can look like a dense STEP debug graph.

## Release Risk

Low risk if implemented as a separate read-only projection/API.

High risk if merged directly into the existing full graph because it will increase node volume, visual clutter, and user confusion.

## Current Validation

Existing STEP tests pass:

```text
backend/tests/test_step_conversion.py: 16 passed
```

This confirms the parser and AP242/PMI conversion path are functioning at the unit-test level.
