# Ontology Endpoints & Accessibility Reference

## 1. ONTOLOGY CREATION/UPLOAD ENDPOINTS

### 1.1 File Import (Stage 1)
**Endpoint:** `POST /api/import/upload`
- **Method:** POST (multipart form-data)
- **Parameters:**
  - `file` (required): File upload (CSV, Excel, EXPRESS, PLMXML, STEP, XML)
  - `ontology_mapping` (optional, Form): Target ontology ID (e.g., "step_ap242", "windchill_ap242")
- **Returns:**
  - `task_id`: Unique task identifier for tracking
  - `filename`: Original filename
  - `file_type`: Detected format
  - `supported_formats`: List of supported formats
  - `message`: Status message
- **Response Code:** 200 OK
- **Example:** `http://localhost:8000/api/import/upload`

### 1.2 Schema Conversion to OWL (Stage 2)
**Endpoint:** `POST /api/import/convert-schema`
- **Method:** POST (multipart form-data)
- **Parameters:**
  - `file` (required): EXPRESS (.exp) or STEP (.stp/.step/.stpx) file
- **Returns:**
  - `task_id`: Task ID for tracking
  - `filename`: Schema filename
  - `schema_name`: Extracted schema name
  - `schema_metadata`: Entity count, constraints, references
  - `owl_ttl`: Full OWL/Turtle RDF representation
  - `owl_triple_count`: Number of RDF triples
  - `line_count`: Lines in OWL output
  - `byte_size`: Size of OWL in bytes
- **Response Code:** 200 OK
- **Purpose:** Converts EXPRESS/STEP schemas to OWL/Turtle for semantic understanding

---

## 2. ONTOLOGY ALIGNMENT MAPPING ENDPOINTS

### 2.1 Map Entities to Target Ontology (Stage 3)
**Endpoint:** `POST /api/import/map-ontology`
- **Method:** POST (JSON body)
- **Request Model:**
  ```json
  {
    "task_id": "string",
    "target_ontology": "windchill | ap242_product | pifrl",
    "confidence_threshold": 0.6  // float 0.0-1.0 (default: 0.6)
  }
  ```
- **Parameters:**
  - `task_id`: From Stage 2 (convert-schema)
  - `target_ontology`: One of:
    - `windchill`: Infineon Windchill product ontology
    - `ap242_product`: ISO 10303 AP242 product alignment
    - `pifrl`: Product Information and Fulfillment Reference Library
  - `confidence_threshold`: Minimum confidence for entity mappings (0.0-1.0)
- **Returns:**
  ```json
  {
    "task_id": "string",
    "source_namespace": "string",
    "target_namespace": "string",
    "entity_mappings_count": 45,
    "unmapped_entities_count": 3,
    "overall_confidence": 0.85,
    "mapping_metadata": {...},
    "aligned_owl_ttl": "string"  // Full aligned OWL
  }
  ```
- **Response Code:** 200 OK
- **Purpose:** Maps EXPRESS/STEP schema entities to target ontology namespace with confidence scoring

### 2.2 Get Available Target Ontologies
**Endpoint:** `GET /api/import/ontologies`
- **Method:** GET
- **Parameters:** None
- **Returns:**
  ```json
  {
    "available_ontologies": {
      "windchill": {
        "namespace": "http://infineon.com/windchill#",
        "entity_count": 542,
        "sample_entities": ["Product", "Part", "Assembly", "Component", "Property"]
      },
      "ap242_product": {
        "namespace": "http://iso.org/ap242/product#",
        "entity_count": 1024,
        "sample_entities": [...]
      },
      ...
    },
    "count": 3
  }
  ```
- **Response Code:** 200 OK
- **Purpose:** Lists all available target ontologies and their namespaces

---

## 3. AP239 ONTOLOGY-SPECIFIC ENDPOINTS

### 3.1 Get AP239 Data Dictionary
**Endpoint:** `GET /api/v1/ontology/ap239/data-dictionary`
- **Method:** GET
- **Parameters:** None
- **Returns:**
  ```json
  {
    "status": "success",
    "ontology": "ap239",
    "data": {
      "entities": {...},
      "relationships": {...},
      "properties": {...}
    },
    "entity_count": 250,
    "relationship_count": 180,
    "property_count": 450
  }
  ```
- **Response Code:** 200 OK
- **Purpose:** Returns AP239 entity definitions and electrical properties

### 3.2 Get AP239 Mappings for Source Format
**Endpoint:** `GET /api/v1/ontology/ap239/mappings/{source_format}`
- **Method:** GET
- **Parameters:**
  - `source_format` (path): Source format type
    - `plmxml`: PLMXML format
    - `step`: STEP format
    - `xmi`: XMI format
    - `xml`: Generic XML
- **Returns:**
  ```json
  {
    "status": "success",
    "source_format": "plmxml",
    "ontology": "ap239",
    "mappings": {
      "Component": "ElectronicComponent",
      "Signal": "SignalNet",
      ...
    },
    "mapping_count": 125
  }
  ```
- **Response Code:** 200 OK

### 3.3 Map Single Entity to AP239
**Endpoint:** `POST /api/v1/ontology/ap239/map-entity`
- **Method:** POST (JSON body)
- **Request Model:**
  ```json
  {
    "entity": { "name": "string", "type": "string", ...properties },
    "source_format": "plmxml | step | xmi | xml"
  }
  ```
- **Returns:**
  ```json
  {
    "status": "success",
    "original_entity": {...},
    "mapped_entity": {
      "type": "ElectronicComponent",
      "electronics_properties": {
        "voltage": 3.3,
        "current": 0.5,
        ...
      }
    }
  }
  ```
- **Response Code:** 200 OK

### 3.4 Get AP239 Domain Pipelines
**Endpoint:** `GET /api/v1/ontology/ap239/domain-pipelines`
- **Method:** GET
- **Parameters:** None
- **Returns:** List of domain-specific pipelines (schematic capture, PCB design, test & verification, manufacturing)
- **Response Code:** 200 OK

---

## 4. MULTI-DOMAIN PIPELINE ENDPOINTS

### 4.1 Get Available Domains
**Endpoint:** `GET /api/v1/ontology/pipelines/domains`
- **Method:** GET
- **Parameters:** None
- **Returns:**
  ```json
  {
    "status": "success",
    "domains": {
      "railway": {...},
      "automotive": {...},
      "aerospace": {...},
      "electronics": {...},
      "industrial": {...}
    },
    "domain_count": 5,
    "supported_formats_summary": {...}
  }
  ```
- **Response Code:** 200 OK
- **Available Domains:**
  - `railway`: Track, signals, rolling stock, coupling
  - `automotive`: Powertrains, electrical, safety, emissions
  - `aerospace`: FMEA, configuration management, maintenance
  - `electronics`: Schematics, PCB, signal integrity
  - `industrial`: Structural, motion, electrical, operations

### 4.2 Get Domain Configuration
**Endpoint:** `GET /api/v1/ontology/pipelines/domain/{domain_name}`
- **Method:** GET
- **Parameters:**
  - `domain_name` (path): Domain name (railway, automotive, aerospace, electronics, industrial)
- **Returns:**
  ```json
  {
    "status": "success",
    "domain": "railway",
    "configuration": {...},
    "required_entities": [...],
    "validation_rules": [...],
    "enrichment_modules": [...],
    "quality_metrics": [...]
  }
  ```
- **Response Code:** 200 OK

### 4.3 Process Data Through Domain Pipeline
**Endpoint:** `POST /api/v1/ontology/pipelines/process`
- **Method:** POST (JSON body)
- **Request Model:**
  ```json
  {
    "entities": [{...}, {...}],
    "relationships": [{...}, {...}],
    "domain": "railway | automotive | aerospace | electronics | industrial",
    "task_id": "optional-tracking-id"
  }
  ```
- **Returns:**
  ```json
  {
    "status": "success",
    "pipeline_result": {...},
    "total_entities_processed": 42,
    "total_relationships": 15,
    "validation_status": "passed"
  }
  ```
- **Response Code:** 200 OK

---

## 5. DYNAMIC ONTOLOGY LIST ENDPOINT

### 5.1 Get Available Ontologies (Dynamic List)
**Endpoint:** `GET /ontologies/available`
- **Method:** GET
- **Parameters:** None
- **Returns:**
  ```json
  {
    "ontologies": [
      {
        "id": "plmxml_ap242",
        "name": "PLMXML → AP242 Product Alignment",
        "type": "plmxml",
        "usageCount": 5,
        "lastUsed": "2026-05-23T14:32:00",
        "source": "dynamic"
      },
      {
        "id": "auto-step",
        "name": "Auto-detect (step)",
        "type": "step",
        "usageCount": 12,
        "lastUsed": "2026-05-23T14:15:00",
        "source": "dynamic"
      }
    ],
    "count": 3,
    "dynamicCount": 2
  }
  ```
- **Response Code:** 200 OK
- **Purpose:** Returns list of ontologies that are actually used in the system (tracked in Neo4j)

---

## 6. FRONTEND COMPONENTS

### 6.1 OntologyMapper Component
**File:** [frontend/src/Components/OntologyMapper.js](frontend/src/Components/OntologyMapper.js)
- **Purpose:** Display ontology data dictionaries, vocabulary mappings, and alignment information
- **Key Endpoints Called:**
  - `GET /ontologies/available` - Load available mapping options
  - `GET /ontology-mapper/{type}/data-dictionary` - Load terms
  - `GET /ontology-mapper/{type}/vocabulary` - Load mappings
  - `GET /ontology-mapper/{type}/stats` - Load statistics
- **Views:**
  - 📖 Data Dictionary: Lists terms with IDs, labels, and ontology prefixes
  - 🔗 Mapping Vocabulary: Shows term-to-term mappings with relationship types
  - 🔄 Ontology Alignment: Displays alignment metadata
- **Key Features:**
  - Prefix-based filtering
  - Search/filter functionality
  - CSV export of terms and mappings
  - Dynamic ontology selection dropdown

### 6.2 DataImportPipeline Component
**File:** [frontend/src/Components/DataImportPipeline.js](frontend/src/Components/DataImportPipeline.js)
- **Purpose:** Multi-stage data import workflow
- **Stages:**
  1. **Upload** (Stage 1): File selection and upload
  2. **Preview** (Stage 2): Data preview with schema detection
  3. **Map** (Stage 3): Ontology selection and entity mapping
  4. **Commit** (Stage 4+): Final data import
- **Ontology Selection:**
  - Displays `ontology_mapping` parameter in upload
  - Shows selected ontology throughout import process
  - Supports "Auto-detect" mode

---

## 7. WHAT MAKES AN ONTOLOGY "ACCESSIBLE"?

### 7.1 Dynamic Ontology Discovery
An ontology becomes "accessible" in the mapping list when:

1. **A successful import creates an `OntologyMetadata` node in Neo4j**
   - Created during Stage 4+ (ingest/commit phase)
   - Node properties:
     - `id`: Ontology identifier (e.g., "plmxml_ap242" or "auto-step")
     - `name`: Human-readable name
     - `type`: Mapping type (plmxml, step, windchill, etc.)
     - `created_at`: Timestamp of first use
     - `usage_count`: Number of times used
     - `last_used`: Timestamp of most recent use

2. **Cypher Query Used:**
   ```cypher
   MERGE (om:OntologyMetadata {
       id: $ontology_id,
       name: $ontology_name,
       type: $mapping_type
   })
   ON CREATE SET om.created_at = $timestamp, om.usage_count = 1
   ON MATCH SET om.usage_count = om.usage_count + 1, om.last_used = $timestamp
   ```

3. **Frontend Retrieval Process:**
   ```cypher
   MATCH (om:OntologyMetadata)
   RETURN om.id AS id, om.name AS name, om.type AS type, 
          om.usage_count AS usage_count, om.last_used AS last_used
   ORDER BY om.usage_count DESC, om.last_used DESC
   ```
   - Results are sorted by usage count (descending) then last used timestamp
   - Shows most frequently used ontologies first

### 7.2 Fallback Ontologies (When No Dynamic Ontologies Exist)
If no `OntologyMetadata` nodes exist in Neo4j, static fallback options are provided:
```json
[
  {
    "id": "plmxml_ap242",
    "name": "PLMXML → AP242 Product Alignment",
    "type": "plmxml",
    "usageCount": 0,
    "lastUsed": null,
    "source": "static"
  },
  {
    "id": "step_ap242",
    "name": "STEP → AP242 Mapping",
    "type": "step",
    "usageCount": 0,
    "lastUsed": null,
    "source": "static"
  },
  {
    "id": "windchill_ap242",
    "name": "Windchill → AP242 Product Alignment",
    "type": "windchill",
    "usageCount": 0,
    "lastUsed": null,
    "source": "static"
  }
]
```

### 7.3 Two Ontology Selection Modes

**1. Explicit Selection:**
- User selects a specific target ontology from dropdown
- Creates `OntologyMetadata` node with ID like "plmxml_ap242"
- Stored in upload form parameter: `ontology_mapping`

**2. Auto-Detection:**
- No ontology explicitly selected
- System detects format from file (plmxml, step, windchill, etc.)
- Creates `OntologyMetadata` node with ID like "auto-plmxml"
- Name becomes "Auto-detect (plmxml)"

---

## 8. API INTEGRATION FLOW

### Complete Import Workflow with Ontologies

```
USER UPLOADS FILE
        ↓
[Stage 1] POST /api/import/upload
    → Returns: task_id, file_type
    → Creates initial import task
        ↓
[Stage 2] POST /api/import/convert-schema (Optional for EXPRESS/STEP)
    → Converts schema to OWL/Turtle
    → Returns: owl_ttl, schema_metadata
        ↓
[Stage 3] POST /api/import/map-ontology
    → Maps to target ontology (windchill, ap242_product, pifrl)
    → Returns: entity_mappings, aligned_owl_ttl
    → Creates OntologyMetadata node in Neo4j
        ↓
[Stage 4-7] GET /api/import/status/{task_id} → Commit
    → Ingest data to Neo4j
    → Updates OntologyMetadata.usage_count
        ↓
[Next Import] GET /ontologies/available
    → Shows ontologies with usage counts
    → Sorted by most recently/frequently used
```

---

## 9. KEY IMPLEMENTATION DETAILS

### 9.1 OntologyMetadata Node Tracking
```python
# From data_import_service.py (line 648)
ont_cypher = """
MERGE (om:OntologyMetadata {
    id: $ontology_id,
    name: $ontology_name,
    type: $mapping_type
})
ON CREATE SET om.created_at = $timestamp, om.usage_count = 1
ON MATCH SET om.usage_count = om.usage_count + 1, om.last_used = $timestamp
"""

ontology_id = ontology_mapping or f"auto-{mapping_type}"
ontology_name = ontology_mapping or f"Auto-detect ({mapping_type})"
```

### 9.2 Frontend Mapping Type Management
```javascript
// From OntologyMapper.js
// Fetch available ontologies
const res = await fetch(`${API_BASE_URL}/ontologies/available`);
const json = await res.json();

// Each ontology has both 'value' (display) and 'type' (for API calls)
const options = json.ontologies.map(ont => ({
  value: ont.id,           // "plmxml_ap242" or "auto-step"
  type: ont.type,          // "plmxml" or "step" (used for API endpoints)
  label: ont.name,
  source: ont.source,
  usageCount: ont.usageCount,
}));
```

### 9.3 Sorting/Ordering
- **Primary Sort:** `usage_count DESC` (most frequently used first)
- **Secondary Sort:** `last_used DESC` (most recent first)
- **Display Order:** Same as database order

---

## 10. SUMMARY TABLE

| Endpoint | Method | Purpose | Key Parameters |
|----------|--------|---------|-----------------|
| `/api/import/upload` | POST | Upload file & start import | `file`, `ontology_mapping` (opt) |
| `/api/import/convert-schema` | POST | Convert to OWL/Turtle | `file` (EXPRESS/STEP) |
| `/api/import/map-ontology` | POST | Map to target ontology | `task_id`, `target_ontology`, `confidence_threshold` |
| `/api/import/ontologies` | GET | List target ontologies | — |
| `/api/v1/ontology/ap239/data-dictionary` | GET | AP239 entities | — |
| `/api/v1/ontology/ap239/mappings/{format}` | GET | AP239 format mappings | `source_format` |
| `/api/v1/ontology/ap239/map-entity` | POST | Map single entity | `entity`, `source_format` |
| `/api/v1/ontology/pipelines/domains` | GET | Available domains | — |
| `/api/v1/ontology/pipelines/domain/{name}` | GET | Domain config | `domain_name` |
| `/api/v1/ontology/pipelines/process` | POST | Process through pipeline | `entities`, `relationships`, `domain` |
| `/ontologies/available` | GET | **Dynamic ontology list** | — |

