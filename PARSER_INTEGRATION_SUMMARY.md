# Parser Integration Technical Summary

## Overview
This document provides detailed analysis of the three file format parsers located in `C:\Users\895428\Depo\import_master\src\parsers\` directory. These parsers extract semantic information from industrial product lifecycle management (PLM) and design specification formats and normalize them into consistent Python dataclass structures for backend integration.

---

## 1. EXPRESS Schema Parser (`express_parser.py`)

### File Purpose
Parses ISO 10303 EXPRESS schema files (`.exp` format) and emits OWL/Turtle RDF representations. The parser translates EXPRESS schema constructs (entities, attributes, types, WHERE rules) into semantic web ontologies compatible with STEP processing pipelines.

### Main Classes

#### `ExpressAttribute`
```python
@dataclass
class ExpressAttribute:
    name: str
    type_ref: str              # Raw type name (entity, type, or primitive)
    optional: bool = False
    is_aggregate: bool = False # SET/LIST/BAG/ARRAY markers
```

#### `ExpressEntity`
```python
@dataclass
class ExpressEntity:
    name: str
    abstract: bool = False
    supertypes: List[str]      # SUBTYPE OF parents
    subtypes: List[str]        # SUPERTYPE OF ONEOF children
    attributes: List[ExpressAttribute]
    where_rules: List[ExpressWhereRule]
```

#### `ExpressWhereRule`
```python
@dataclass
class ExpressWhereRule:
    rule_id: str
    expression: str            # Raw EXPRESS boolean logic
```

#### `ExpressEnumType`
```python
@dataclass
class ExpressEnumType:
    name: str
    values: List[str]          # Enumeration literal tokens
```

#### `ExpressSelectType`
```python
@dataclass
class ExpressSelectType:
    name: str
    members: List[str]         # Union type member list
```

#### `ExpressSchema`
```python
@dataclass
class ExpressSchema:
    name: str
    entities: Dict[str, ExpressEntity]
    enumerations: Dict[str, ExpressEnumType]
    select_types: Dict[str, ExpressSelectType]
    type_aliases: Dict[str, str]  # Primitive alias mappings
```

### Main Functions

#### `parse_express(path: Path) → ExpressSchema`
- **Input**: Path to `.exp` file
- **Output**: Fully populated `ExpressSchema` dataclass
- **Logic**:
  1. Removes `(* ... *)` block comments
  2. Extracts ENTITY blocks with regex: `ENTITY name ... END_ENTITY;`
  3. Parses attributes with optional cardinality markers
  4. Extracts WHERE rules for constraint validation
  5. Collects inheritance chains (SUBTYPE/SUPERTYPE OF)
  6. Maps TYPE definitions (ENUMERATION, SELECT, primitive aliases)
  7. Logs aggregated statistics

#### `emit_owl_ttl(schema, base_uri, prefix, source_path) → str`
- **Input**: ExpressSchema, base URI, namespace prefix
- **Output**: Turtle RDF format string
- **Key Transforms**:
  - ENTITY → `owl:Class`
  - ABSTRACT flag → `owl:equivalentClass` marker
  - Inheritance → `rdfs:subClassOf`
  - ENUMERATION → `owl:Class` + `owl:oneOf` individuals
  - SELECT type → concept-only `owl:Class`
  - Attributes → `owl:ObjectProperty` (entity ranges) or `owl:DatatypeProperty` (primitives)
  - WHERE rules → `sh:NodeShape` + SHACL/SPARQL constraints

### External Dependencies
```python
from pathlib import Path
from loguru import logger
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional
```

### Key Entity Extraction Features

**Type Resolution:**
- Primitive types mapped via `_PRIM_TO_XSD` dictionary (STRING→xsd:string, INTEGER→xsd:integer, etc.)
- Alias tracking for custom type derivations
- SELECT type membership capture (no explicit members emitted)

**WHERE Rule Translation (Subset):**
- EXISTS patterns: `EXISTS(A) OR EXISTS(B)`
- NOT(EXISTS patterns with AND/OR combinations
- SIZEOF comparisons: `SIZEOF(A) = SIZEOF(B)` and against constants
- TYPEOF patterns: `TYPEOF(A) = TYPEOF(B)`
- TYPEOF membership: `'<TYPE>' IN TYPEOF(X)` patterns
- Composite rules: weight/unit contextual checks
- QUERY patterns for cartesian transformations and assembly contexts

**SPARQL Generation:**
- Optional path binding for inherited attributes
- Violation detection logic (inverted WHERE conditions)
- COUNT aggregations for cardinality validation
- FILTER expressions for constraint enforcement

### Special Handling
- **Attribute Path Resolution**: Handles SELF references and dotted paths (e.g., `SELF.Weight.Unit.Name`)
- **Cardinality**: SET/LIST/BAG/ARRAY markers tracked but not emitted as full SHACL cardinality
- **Case Sensitivity**: Normalizes case while preserving canonical names
- **Inheritance**: Tracks both SUBTYPE OF (parents) and SUPERTYPE OF (children)

---

## 2. PLMXML Parser (`plmxml_parser_v2.py`)

### File Purpose
Lightweight extraction layer for Teamcenter PLMXML (Product Lifecycle Management XML) payloads. Focuses on stable, high-frequency constructs: parts, products, processes, requirements, change notices, revisions, and traceability relationships.

### Main Classes (20+ dataclasses)

#### Core Product Structure
```python
@dataclass
class PlmxmlPart:
    id: str
    name: str = ""
    part_number: str = ""
    revision: str = ""
    description: str = ""
    part_type: str = ""
    master_ref: str = ""
    user_data_refs: List[str] = field(default_factory=list)
    properties: Dict[str, str] = field(default_factory=dict)

@dataclass
class PlmxmlProductView:
    id: str
    name: str = ""
    view_type: str = ""
    root_refs: List[str] = field(default_factory=list)
    product_ref: str = ""
    structure_type: str = ""
    properties: Dict[str, str] = field(default_factory=dict)

@dataclass
class PlmxmlProductInstance:
    id: str
    name: str = ""
    part_ref: str = ""
    transform_ref: str = ""
    parent_ref: str = ""
    quantity: int = 1
    occurrence_refs: List[str] = field(default_factory=list)
    user_data_refs: List[str] = field(default_factory=list)
    application_refs: List[str] = field(default_factory=list)
    properties: Dict[str, str] = field(default_factory=dict)
```

#### Process & Manufacturing
```python
@dataclass
class PlmxmlProcess:
    id: str
    name: str = ""
    process_type: str = ""
    description: str = ""
    time_required: float | None = None
    resources: List[str] = field(default_factory=list)
    properties: Dict[str, str] = field(default_factory=dict)

@dataclass
class PlmxmlProcessInstance:
    id: str
    process_ref: str = ""
    predecessor_refs: List[str] = field(default_factory=list)
    product_instance_refs: List[str] = field(default_factory=list)
    properties: Dict[str, str] = field(default_factory=dict)
```

#### Requirements & Traceability
```python
@dataclass
class PlmxmlRequirement:
    """Teamcenter R-layer of RFLP (Requirements-Functional-Logical-Physical)"""
    id: str
    name: str = ""
    catalogue_id: str = ""
    revision: str = ""
    revision_id: str = ""
    master_ref: str = ""
    body_text: str = ""
    last_mod_date: str = ""
    object_string: str = ""
    dataset_ref: str = ""
    user_data_refs: List[str] = field(default_factory=list)
    properties: Dict[str, str] = field(default_factory=dict)

@dataclass
class PlmxmlGeneralRelation:
    """Carries RFLP trace links (Seg0Realize/Allocate/Satisfy/FND_TraceLink)"""
    id: str
    sub_type: str = ""
    related_refs: List[str] = field(default_factory=list)
    tc_label: str = ""
    properties: Dict[str, str] = field(default_factory=dict)
```

#### Change & Revision Management
```python
@dataclass
class PlmxmlChangeNotice:
    id: str
    name: str = ""
    change_type: str = ""
    status: str = ""
    description: str = ""
    date: str = ""
    author: str = ""
    affected_items: List[str] = field(default_factory=list)
    properties: Dict[str, str] = field(default_factory=dict)

@dataclass
class PlmxmlRevision:
    id: str
    revision_id: str = ""
    base_ref: str = ""
    revision_type: str = ""
    date: str = ""
    description: str = ""
    change_notice_refs: List[str] = field(default_factory=list)
    properties: Dict[str, str] = field(default_factory=dict)
```

#### Supporting Structures
```python
@dataclass
class PlmxmlTransform:          # 4x4 transformation matrices
    id: str
    matrix: List[float] = field(default_factory=list)

@dataclass
class PlmxmlUserData:           # Teamcenter custom properties
    id: str
    type: str = ""
    title: str = ""
    values: Dict[str, str] = field(default_factory=dict)

@dataclass
class PlmxmlForm:               # ItemRevision master attributes
    id: str
    name: str = ""
    sub_type: str = ""
    sub_class: str = ""
    description: str = ""
    attributes: Dict[str, str] = field(default_factory=dict)
    properties: Dict[str, str] = field(default_factory=dict)

@dataclass
class PlmxmlDocument:           # Root container
    file_path: Path | None = None
    schema_version: str = ""
    author: str = ""
    date: str = ""
    root_refs: List[str] = field(default_factory=list)
    parts: Dict[str, PlmxmlPart]
    product_views: Dict[str, PlmxmlProductView]
    product_instances: List[PlmxmlProductInstance]
    processes: Dict[str, PlmxmlProcess]
    # ... 10+ additional dictionary/list fields
```

### Main Functions

#### `parse_plmxml_file(file_path: Path) → PlmxmlDocument`
- **Input**: Path to PLMXML file
- **Output**: Fully populated `PlmxmlDocument` with all entity types
- **Parsing Strategy**:
  1. Parses XML tree with ElementTree
  2. Extracts namespace-aware tags (`_local_name()` utility)
  3. Iterates all elements, dispatching by tag type to appropriate dataclass
  4. Handles attribute alias variants (Teamcenter schema flexibility)
  5. Extracts nested UserData structures (recursive title-value parsing)
  6. Merges RequirementRevision into Requirement masters
  7. Builds reference lists from comma/space-separated ID strings
  8. Parses transformation matrices (float arrays)
  9. Converts quantity/time strings to numeric types

#### `_rflp_layer(sub_type: str) → str`
- **Input**: Teamcenter subType string
- **Output**: RFLP layer letter (R/F/L/P) or empty string
- **Mapping**:
  - R (Requirements): `Requirement`, `RequirementRevision`
  - F (Functional): `Sys0SystemFunc*`, `Sys0LogicalFunc*`, `Sys0PhysicalFunc*`
  - L (Logical): `Sys0LogicalComp*`
  - P (Physical): `Sys0PhysNode*`, `Item*`

### External Dependencies
```python
from pathlib import Path
from dataclasses import dataclass, field
from typing import Dict, List
import xml.etree.ElementTree as ET
```

### Key Entity Extraction Features

**Attribute Alias Resolution:**
- Tag variants handled: `PartNumber` vs `number` vs `itemId`, `Revision` vs `revisionId`
- Flexible reference naming: `masterRef`, `baseRef`, `productRef` consolidated
- Root element attributes normalized with `_local_name()` for namespace stripping

**Quantity Parsing:**
- Handles string representations: `"1.5"`, `"2"`, `"qty=3"`
- Falls back to 1 on parse failure

**Time Parsing:**
- Searches `timeRequired` or `plannedTime` attributes
- Returns `float | None` for nullable time values

**Reference List Parsing:**
- Comma/space-separated IDs parsed via `_parse_refs()`
- Strips leading `#` from reference tokens
- Returns deduplicated lists

**Nested Data Extraction:**
- UserData → Title-Value child pairs
- Form → Description + UserData attributes
- RequirementRevision → PlainText (body), UserData (metadata), DataSet references

**Traceability Mapping:**
- GeneralRelation captures RFLP trace links with Teamcenter labels
- Requirement/RequirementRevision master-slave merging
- Dataset reference preservation

### Special Handling
- **Namespace Tolerance**: Handles both namespaced and non-namespaced tags
- **Form Master Merging**: RequirementRevision attributes merged into matching Requirement master
- **Property Preservation**: All unparsed attributes preserved in `properties` dict for extensibility
- **Root Reference Tracking**: Extracts document root_refs from root element attributes

---

## 3. STEP Parser (`step_parser.py`)

### File Purpose
Parses ISO 10303 STEP files in both Part21 (`.stp`, `.step`) and Part28 (`.stpx`, `.xml`) formats. Focuses on reliable entity extraction and Product Modeling Interface (PMI) (geometric tolerances, dimensions, datums) while maintaining conservative defaults for structural CAD data.

### Main Classes

#### Metadata & Document
```python
@dataclass
class StepFileMeta:
    format: str                # "p21" or "stpx"
    file_schema: Optional[str]
    file_name: str

@dataclass
class StepPMIDocument:
    metadata: StepFileMeta
    entities: List[StepP21Entity]
    entity_map: Dict[int, StepP21Entity]
    geometric_tolerances: List[StepGeometricTolerance]
    datums: List[StepDatum]
    dimensions: List[StepDimension]
    annotations: List[StepAnnotation]
    surface_finishes: List[StepSurfaceFinish]
    cad_products: List[StepCadEntity]
    cad_representations: List[StepCadEntity]
    cad_topology: List[StepCadEntity]
    cad_geometry: List[StepCadEntity]
```

#### Core Entity Extraction
```python
@dataclass
class StepP21Entity:
    """Raw parsed entity from STEP Part21 or Part28 syntax"""
    step_id: int
    entity_type: str           # Normalized AP242 entity name
    raw_args: str              # Unparsed argument list
    ref_ids: List[int] = field(default_factory=list)  # #ID references extracted
```

#### PMI Structures
```python
@dataclass
class StepGeometricTolerance:
    id: int
    tolerance_type: str = "UNKNOWN"
    name: str = ""
    description: str = ""
    magnitude: Optional[float] = None
    unit: str = ""
    datum_system_refs: List[int] = field(default_factory=list)
    toleranced_feature_refs: List[int] = field(default_factory=list)

@dataclass
class StepDatum:
    id: int
    label: str = ""
    datum_type: str = ""
    feature_refs: List[int] = field(default_factory=list)
    name: str = ""

@dataclass
class StepDimension:
    id: int
    dimension_type: str = ""
    name: str = ""
    description: str = ""
    nominal_value: Optional[float] = None
    upper_tolerance: Optional[float] = None
    lower_tolerance: Optional[float] = None
    unit: str = ""
    feature_refs: List[int] = field(default_factory=list)

@dataclass
class StepAnnotation:
    id: int
    annotation_type: str = ""
    text: str = ""
    name: str = ""
    presentation_refs: List[int] = field(default_factory=list)
    leader_refs: List[int] = field(default_factory=list)

@dataclass
class StepSurfaceFinish:
    id: int
    finish_type: str = ""
    roughness_average: Optional[float] = None
    roughness_max: Optional[float] = None
    unit: str = ""
    method: str = ""
    feature_refs: List[int] = field(default_factory=list)
```

#### CAD Structure Entities
```python
@dataclass
class StepCadEntity:
    """Classified CAD structural entities (products, representations, topology, geometry)"""
    id: int
    entity_type: str
    external_id: str = ""
    name: str = ""
    description: str = ""
    ref_ids: List[int] = field(default_factory=list)
```

### Main Functions

#### `detect_step_format(file_path: Path) → str`
- **Logic**:
  1. Checks file suffix: `.stpx` → "stpx", `.xml` → check content
  2. Reads file head for `iso_10303_28` namespace indicator
  3. Falls back to "p21" for uncertain cases

#### `parse_step_metadata(file_path: Path) → StepFileMeta`
- **Input**: File path
- **Output**: Metadata structure with format, schema version, filename
- **Logic**:
  1. Regex search for `FILE_SCHEMA('...')` in P21 files
  2. XML attribute extraction for Part28 files
  3. Error tolerance: returns defaults on parse failures

#### `iter_part21_entities(file_path: Path) → Iterator[StepP21Entity]`
- **Input**: File path
- **Output**: Generator yielding entities one at a time
- **Format Detection**: Delegates to `_iter_part21_entities()` or `_iter_part28_entities()`

#### `_iter_part21_entities(file_path: Path) → Iterator[StepP21Entity]`
- **Parsing Steps**:
  1. Reads file with UTF-8 error tolerance
  2. Extracts DATA section (between `DATA;` and `ENDSEC;`)
  3. Removes `/* ... */` comments
  4. Tokenizes records: state machine tracking:
     - Parenthesis depth (nesting)
     - Quote state (STEP strings escape quotes as `''`)
     - Semicolon terminators (only at depth 0)
  5. Applies regex: `#(\d+) = ([A-Z0-9_]+)(.*)`
  6. Extracts `#ID` references from raw argument string
  7. Normalizes entity type with `normalize_ap242_entity_type()`
  8. Yields `StepP21Entity` with all references resolved

#### `_iter_part28_entities(file_path: Path) → Iterator[StepP21Entity]`
- **XML Parsing**:
  1. Parses XML tree
  2. Pre-processes: builds `id → step_id` mapping
  3. Iterates elements, extracts tag name (namespace-aware) as entity type
  4. Collects attributes as `key=value` pairs
  5. Searches attribute values for ID references (both `#123` and bare ID tokens)
  6. Preserves text content (limited to 200 chars)
  7. Yields `StepP21Entity` with deduced step_id

#### `parse_step_with_pmi(file_path: Path) → StepPMIDocument`
- **Input**: STEP file path
- **Output**: Complete document with PMI and CAD entity classification
- **Logic**:
  1. Parses metadata with `parse_step_metadata()`
  2. Iterates all entities with `iter_part21_entities()`
  3. Classifies each entity via `_classify_cad_entity()`:
     - Product: checks `PRODUCT*` token
     - Representation: checks `REPRESENTATION` token
     - Topology: checks `EDGE|FACE|SHELL|TOPO` tokens
     - Geometry: checks `POINT|CURVE|SURFACE|GEOMETRIC` tokens
  4. Builds entity_map: `{step_id → StepP21Entity}`
  5. Populates CAD lists (empty PMI lists; can be populated by post-processors)

#### `get_pmi_summary(doc: StepPMIDocument) → Dict[str, int | bool]`
- **Output Dictionary**:
  - `total_entities`: Count of raw entities
  - `has_pmi`: Boolean (any PMI types present)
  - `geometric_tolerances`, `datums`, `dimensions`, `annotations`: Counts
  - `cad_products`, `cad_representations`, `cad_topology`, `cad_geometry`: Counts
  - `has_cad_semantics`: Boolean (any CAD structure present)

### External Dependencies
```python
from pathlib import Path
from dataclasses import dataclass, field
from typing import Dict, Iterator, List, Optional
import re
import xml.etree.ElementTree as ET
```

### Key Entity Extraction Features

**AP242 Entity Type Normalization:**
- Regex transforms: camelCase → UPPER_SNAKE_CASE
  - `ProductDefinition` → `PRODUCT_DEFINITION`
  - `NextAssemblyUsageOccurrence` → `NEXT_ASSEMBLY_USAGE_OCCURRENCE`
- Alias table `_AP242_ENTITY_ALIASES` maps Part28/XML variants to canonical names
- Handles encoding artifacts: removes non-alphanumeric characters

**Reference Extraction:**
- Part21: Regex `#(\d+)` on raw argument string
- Part28: Attribute value tokenization + ID mapping lookup
- Deduplicates and sorts reference lists

**PMI Placeholder Structure:**
- Initializes empty PMI lists (ready for post-processing by specialized extractors)
- Stores all geometries/tolerances for later semantic analysis
- Maintains ID map for entity resolution

**Robustness:**
- Handles malformed UTF-8 with error="ignore"
- Graceful fallback to defaults on missing metadata
- Tolerates missing DATA section boundaries
- Validates nested structure before emitting entities

### Special Handling
- **String Escaping**: STEP Part21 doubles single quotes (`''` = literal `'`)
- **State Machine Parsing**: Proper handling of nested parentheses across string literals
- **Comment Removal**: `/* ... */` multi-line comment stripping before parsing
- **XML Namespace Tolerance**: `_local_name()` strips namespace URI prefix
- **ID Mapping**: Part28 builds synthetic step_id mapping for consistency with Part21

---

## Integration with Backend Services

### Data Flow
```
[File Input]
   ↓
[Format Detection] → detect_step_format() / infer from extension
   ↓
[Parse Function] → parse_express() / parse_plmxml_file() / parse_step_with_pmi()
   ↓
[Dataclass Container] → ExpressSchema / PlmxmlDocument / StepPMIDocument
   ↓
[Service Consumers]
  - data_import_service.py (document ingestion)
  - ontology_mapper_service.py (RFLP traceability)
  - graph_embeddings.py (semantic relationships)
  - similar_parts_recommender.py (CAD structure analysis)
```

### Recommended Service Integration Points

**For Document Import Pipeline:**
```python
from src.parsers import parse_plmxml_file, parse_step_with_pmi, parse_express
from pathlib import Path

# PLMXML document ingestion
plm_doc = parse_plmxml_file(Path("vendor_catalog.plmxml"))
for part_id, part in plm_doc.parts.items():
    create_graph_node(part_id, "Part", part.properties)
    
# STEP model ingestion
step_doc = parse_step_with_pmi(Path("design.stp"))
summary = get_pmi_summary(step_doc)
if summary['has_cad_semantics']:
    process_cad_structure(step_doc.cad_products)
    
# EXPRESS schema ingestion
schema = parse_express(Path("DomainModel.exp"))
ttl_output = emit_owl_ttl(schema, base_uri="http://mycompany.com/ap242#")
```

**For Ontology Mapping:**
```python
# Extract RFLP requirements traceability
for req_id, requirement in plm_doc.requirements.items():
    layer = _rflp_layer(requirement.catalogue_id)
    map_rflp_trace(req_id, layer, requirement.body_text)
    
# Map traceability relations
for relation in plm_doc.general_relations:
    tc_link = TraceLink(relation.id, relation.sub_type, relation.related_refs)
    store_traceability(tc_link)
```

**For Validation & Constraint Checking:**
```python
# Leverage EXPRESS WHERE rules for validation
for entity_id, entity in schema.entities.items():
    for where_rule in entity.where_rules:
        sparql_constraint = emit_owl_ttl(schema, base_uri)
        # Register with graph validator
```

### Dependency Summary
- **EXPRESS Parser**: Requires `loguru` for logging
- **PLMXML Parser**: Standard library only (xml.etree)
- **STEP Parser**: Standard library only (re, pathlib, dataclasses)
- **All**: Python 3.10+ (Union type syntax `|`)

### Common Patterns for Backend Integration

**Error Handling:**
```python
try:
    doc = parse_plmxml_file(file_path)
except ET.ParseError:
    logger.error(f"Invalid PLMXML: {file_path}")
except OSError:
    logger.error(f"File not found: {file_path}")
```

**Entity Traversal:**
```python
# Depth-first traversal of product structure
def traverse_products(doc, parent_id=None, depth=0):
    for instance in doc.product_instances:
        if instance.parent_ref == parent_id:
            process_instance(instance, depth)
            traverse_products(doc, instance.id, depth + 1)
```

**Reference Resolution:**
```python
# Resolve ID references in STEP CAD entities
for entity in step_doc.cad_products:
    for ref_id in entity.ref_ids:
        referenced = step_doc.entity_map.get(ref_id)
        if referenced:
            link_entities(entity, referenced)
```

---

## Summary Table

| Aspect | EXPRESS | PLMXML | STEP |
|--------|---------|--------|------|
| **Input Format** | `.exp` text | `.plmxml` XML | `.stp`/`.stpx` |
| **Primary Use** | Schema/ontology definition | PLM product structures | CAD/PMI extraction |
| **Main Output Class** | `ExpressSchema` | `PlmxmlDocument` | `StepPMIDocument` |
| **Entity Types** | ENTITY, ENUMERATION, SELECT | Part, Process, Requirement | Product, Geometry, PMI |
| **Key Innovation** | WHERE rule → SPARQL translation | RFLP layer classification | Dual Part21/Part28 parsing |
| **Dependencies** | `loguru` + stdlib | stdlib only | stdlib only |
| **Reference Handling** | Type name resolution | URL ID references | Numeric #ID mapping |
| **Semantic Output** | OWL/Turtle RDF | Python dataclasses | Classified CAD + PMI |

---

## Deployment Checklist for Backend Integration

- [ ] Add parsers to backend module imports
- [ ] Configure file upload handlers to call appropriate parser based on file extension
- [ ] Implement error handlers for parsing exceptions (malformed files)
- [ ] Cache parsed schemas (EXPRESS rarely changes)
- [ ] Implement reference resolution post-processor for cross-entity linking
- [ ] Add metrics: parsing time, entity counts, reference density
- [ ] Document custom attribute mappings for organizational extensions
- [ ] Create validation tests with sample files from each format
- [ ] Set up async parsing pipeline for large documents (>100K entities)
- [ ] Implement incremental/delta parsing for periodic PLM syncs
