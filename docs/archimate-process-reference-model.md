# ArchiMate Process Reference Model Support

## Purpose

The ArchiMate workflow imports ArchiMate Model Exchange XML as a process and architecture reference graph. It is intended for enterprise/process architecture traceability, not as a replacement for OWL ontology reasoning.

## Supported Input

- ArchiMate Model Exchange XML (`.archimate`)
- ArchiMate Model Exchange XML saved as `.xml` when the user selects **Import ArchiMate process model**
- Open Group ArchiMate 3.x exchange namespace, including `https://www.opengroup.org//xsd/archimate/3.1/` and normalized `opengroup.org/xsd/archimate` variants

## Import Flow

1. Select **Import ArchiMate process model** on the Import page.
2. Add an ArchiMate Model Exchange XML file.
3. Start the workflow.
4. Review parsed elements and relationships.
5. Commit to Neo4j.

## Graph Projection

ArchiMate elements become typed Neo4j nodes using their ArchiMate element type, for example:

- `BusinessProcess`
- `BusinessFunction`
- `Capability`
- `ApplicationComponent`
- `ApplicationService`
- `DataObject`
- `TechnologyNode`

ArchiMate relationships become typed Neo4j relationships, for example:

- `SERVING`
- `TRIGGERING`
- `FLOW`
- `REALIZATION`
- `ASSIGNMENT`
- `ACCESS`

The import preserves:

- `archimate_id`
- `archimate_type`
- `name`
- `description`
- `source_format = archimate`
- `ontology_prefix = archimate`
- source namespace
- model identifier and model name
- ArchiMate property definitions and element/relationship property values
- view metadata and element/relationship references for diagnostics
- unresolved relationship endpoint counts


## Graph Explorer View

After committing an ArchiMate import, open **Graph Explorer** and click the **Architecture Process** icon. This loads `/api/v1/graph/view/architecture/archimate` and shows only connected ArchiMate process/architecture nodes and typed relationships. The ontology schema view remains reserved for OWL/RDF ontology structure.

## How This Augments The Platform

Use ArchiMate as the architecture/process layer and Semantic Bridge for controlled linking to product ontology concepts:

- `BusinessProcess -> BOP / manufacturing process`
- `Capability -> MBSE capability`
- `ApplicationComponent -> application/service architecture`
- `DataObject -> data dictionary or PLM object`
- `Requirement -> OSLC RM requirement`

Graph Explorer and Knowledge Companion can then answer process-reference questions such as:

- Which business process is impacted by this requirement?
- Which application services support this manufacturing process?
- Which data objects are used by this capability?
- Show process-to-product traceability across MBSE, EBOM, MBOM, and BOP.

## Design Boundary

ArchiMate import creates a graph projection of architecture/process models. OWL/RDF semantics remain handled by the ontology layer using Owlready2/RDFLib, and mappings between ArchiMate elements and ontology concepts should be reviewed through Semantic Bridge.

### Folder and View Preservation

ArchiMate imports preserve the model organization layer instead of flattening the file:

- Archi/ArchiMate folders become `Package` nodes with their original folder names.
- Diagram/view definitions become `View` nodes with their original view names.
- Folder-to-folder, folder-to-element, and view-to-element membership is written as `CONTAINS` / `VIEW_CONTAINS` relationships.
- Architecture graph views can therefore show named folders such as `Business`, `Application`, `Views`, and process-group folders from the source file.
