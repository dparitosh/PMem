# Dynamic Ontology System

## Overview

The system now **automatically tracks used ontologies** in Neo4j and displays them dynamically in the frontend dropdown - instead of hardcoding a static list.

---

## How It Works

### 1️⃣ When Data is Imported

**Backend (data_import_service.py):**
- During the **Load stage**, after creating entities in Neo4j
- Creates an `OntologyMetadata` node for each ontology used
- Tracks: `id`, `name`, `type`, `usage_count`, `last_used`

```cypher
MERGE (om:OntologyMetadata {
    id: $ontology_id,
    name: $ontology_name,
    type: $mapping_type
})
ON CREATE SET om.created_at = $timestamp, om.usage_count = 1
ON MATCH SET om.usage_count = om.usage_count + 1, om.last_used = $timestamp
```

**Examples Created:**
```
Auto-detect (step)        → Tracks "step" auto-detection
step_ap242                → Tracks explicit selection
plmxml_ap242              → Tracks PLMXML mapping
```

### 2️⃣ Backend Exposes Endpoint

**New Endpoint:** `GET /ontologies/available`

Returns:
```json
{
  "ontologies": [
    {
      "id": "step_ap242",
      "name": "STEP → AP242 Mapping",
      "type": "step",
      "usageCount": 5,
      "lastUsed": "2026-05-23T10:30:00",
      "source": "dynamic"
    },
    {
      "id": "auto-step",
      "name": "Auto-detect (step)",
      "type": "step",
      "usageCount": 3,
      "lastUsed": "2026-05-23T09:15:00",
      "source": "dynamic"
    },
    {
      "id": "plmxml_ap242",
      "name": "PLMXML → AP242 Product Alignment",
      "type": "plmxml",
      "usageCount": 0,
      "lastUsed": null,
      "source": "static"
    }
  ],
  "count": 3,
  "dynamicCount": 2
}
```

### 3️⃣ Frontend Fetches Dynamically

**DataImportPipeline.js useEffect:**
```javascript
// Fetch from backend (gets dynamic list from Neo4j)
const res = await fetch(`${API_BASE_URL}/ontologies/available`);
const data = await res.json();
setAvailableOntologies(data.ontologies);

// Fallback to static if backend fails
```

### 4️⃣ Dropdown Shows Updated List

**Before:**
```
Ontology Alignment: [Auto-detect ▼]
  ├─ Auto-detect from file format
  ├─ PLMXML → AP242 Product Alignment
  ├─ STEP → AP242 Mapping
  └─ Windchill → AP242 Product Alignment
```

**After (Dynamic):**
```
Ontology Alignment: [Auto-detect ▼]
  ├─ Auto-detect from file format
  ├─ STEP → AP242 Mapping (used 5x) ✓ in Neo4j
  ├─ Auto-detect (step) (used 3x) ✓ in Neo4j
  ├─ PLMXML → AP242 Product Alignment
  └─ Windchill → AP242 Product Alignment
```

---

## Key Features

✅ **Dynamic List** - Shows all ontologies actually used in Neo4j  
✅ **Usage Tracking** - Shows how many times each was used  
✅ **Last Used** - Timestamp of most recent use  
✅ **Source Indicator** - Shows if from Neo4j (dynamic) or static files  
✅ **Fallback Safe** - Uses static list if Neo4j unavailable  
✅ **Auto-Detection Tracked** - Even "auto-detect" ontologies are recorded  

---

## Scenarios

### Scenario 1: First Time (No Data Imported Yet)

**Neo4j Status:** No OntologyMetadata nodes  
**Dropdown Shows:** Static fallback only
```
├─ PLMXML → AP242 Product Alignment
├─ STEP → AP242 Mapping
└─ Windchill → AP242 Product Alignment
```

### Scenario 2: After Importing STEP File with Auto-Detect

**Neo4j Creates:**
```cypher
OntologyMetadata {
  id: "auto-step",
  name: "Auto-detect (step)",
  type: "step",
  usage_count: 1,
  created_at: "2026-05-23T10:00:00"
}
```

**Dropdown Now Shows:**
```
├─ Auto-detect from file format
├─ Auto-detect (step) (used 1x) ✓ in Neo4j  ← NEW!
├─ PLMXML → AP242 Product Alignment
├─ STEP → AP242 Mapping
└─ Windchill → AP242 Product Alignment
```

### Scenario 3: After Importing with "STEP → AP242 Mapping" Selected

**Neo4j Creates:**
```cypher
OntologyMetadata {
  id: "step_ap242",
  name: "STEP → AP242 Mapping",
  type: "step",
  usage_count: 1,
  created_at: "2026-05-23T10:30:00"
}
```

**Dropdown Now Shows** (sorted by usage):
```
├─ Auto-detect from file format
├─ STEP → AP242 Mapping (used 1x) ✓ in Neo4j
├─ Auto-detect (step) (used 1x) ✓ in Neo4j
├─ PLMXML → AP242 Product Alignment
└─ Windchill → AP242 Product Alignment
```

---

## Technical Implementation

### Backend Changes

**File:** `backend/backend/Services/data_import_service.py`

**Location:** `_ingest_stage()` method, after entity creation

**Code:**
```python
# Create OntologyMetadata node to track used ontologies
ontology_mapping = import_tasks[task_id].get('ontology_mapping', '')
mapping_type = import_tasks[task_id].get('mapping_type', 'unknown')

ontology_id = ontology_mapping or f"auto-{mapping_type}"
ontology_name = ontology_mapping or f"Auto-detect ({mapping_type})"

graph.query(
    """
    MERGE (om:OntologyMetadata {
        id: $ontology_id,
        name: $ontology_name,
        type: $mapping_type
    })
    ON CREATE SET om.created_at = $timestamp, om.usage_count = 1
    ON MATCH SET om.usage_count = om.usage_count + 1, om.last_used = $timestamp
    """,
    {...}
)
```

### Backend API

**File:** `backend/backend/main.py`

**New Endpoint:** `GET /ontologies/available`

```python
@app.get("/ontologies/available")
def get_available_ontologies():
    """Get available ontologies from Neo4j (dynamic, based on imports)."""
    # Query OntologyMetadata nodes
    # Return with usage counts and last_used dates
    # Fallback to static list if empty
```

### Frontend Changes

**File:** `frontend/src/Components/DataImportPipeline.js`

**Changes:**
1. `useEffect` now fetches `/ontologies/available`
2. Maps response to match component format
3. Dropdown options include usage count and source indicator
4. Falls back to static list if fetch fails

---

## Neo4j Query for Manual Inspection

To see all tracked ontologies in Neo4j:

```cypher
MATCH (om:OntologyMetadata)
RETURN om.id, om.name, om.type, om.usage_count, om.last_used
ORDER BY om.usage_count DESC, om.last_used DESC
```

---

## Benefits

🎯 **User Sees What's Actually Used** - No mystery about available ontologies  
🎯 **Encourages Best Practices** - See popularity of each mapping  
🎯 **Automatic Discovery** - New ontologies appear automatically when used  
🎯 **Audit Trail** - Track which ontologies have been applied to data  
🎯 **Scalable** - Works for any number of ontologies  

---

## Answer to Your Question

> "It should not be static list. It should be dynamic. As output of data import ontology none will lead to creation of ontology, right?"

**YES! ✅**

- ✅ Auto-detect **creates** OntologyMetadata node (e.g., "auto-step")
- ✅ Selected ontology **creates** OntologyMetadata node (e.g., "step_ap242")
- ✅ Dropdown is now **DYNAMIC** - fetches from Neo4j
- ✅ Users see **what's actually in the graph**, not static hardcoded list

Every time you import data:
1. Backend creates/updates OntologyMetadata node
2. Frontend refetches `/ontologies/available`
3. User sees updated dropdown with usage counts

**System is now fully dynamic! 🚀**
