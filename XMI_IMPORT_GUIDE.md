# XMI Import & MBSE Ontology Visualization Guide

## ✅ Issues Fixed

### 1. **Path Configuration Corrected**
The backend was looking for `import_master` at the wrong location:
- ❌ **Before**: `C:\Users\895428\Depo_Onto_Engine\Depo\import_master\src` (incorrect)
- ✅ **After**: `C:\Users\895428\Depo\import_master\src` (correct)

**Files Updated:**
- `backend/backend/Services/data_import_service.py` - Line 90
- `backend/backend/Services/unified_data_import.py` - Line 40

### 2. **Duplicate Folder Removed**
Deleted redundant: `C:\Users\895428\Depo_Onto_Engine\import_master\`

### 3. **Real XMI Parser is Now Active**
- Parser Location: `C:\Users\895428\Depo\import_master\ontologies\external\xmi_parser.py`
- Status: ✅ Ready to parse XMI files with full MBSE ontology support

---

## 📊 MBSE Ontology Elements Supported

The XMI parser extracts and supports these SysML/MBSE element types:

### Core MBSE Elements
| Element Type | Purpose | Example |
|---|---|---|
| **Requirement** | System requirements | "Brake torque ≥ 100 Nm" |
| **UseCase** | System interactions | "Apply Emergency Brake" |
| **Activity** | Process flows | "Calculate deceleration" |
| **Block** | System architecture | "BrakeController", "Motor" |
| **Component** | Implementation units | "BrakeECU", "Actuator" |
| **ConstraintBlock** | Mathematical constraints | "PhysicsConstraint" |
| **ValueType** | Domain values | "Torque", "Acceleration" |
| **State** | Behavior states | "Ready", "Braking", "Idle" |
| **Actor** | External entities | "Driver", "Environment" |

---

## 🔗 Traceability Relationships Supported

The parser extracts **SysML traceability relationships** essential for system design:

### Traceability Links
| Relationship | Direction | Use Case |
|---|---|---|
| **SATISFY** | Requirement → Design Element | "Requirement X is satisfied by Component Y" |
| **VERIFY** | Requirement → Test/Activity | "Test case Z verifies Requirement X" |
| **TRACE** | Element → Element | "Design element traces back to Requirement" |
| **REFINE** | Abstract → Concrete | "High-level requirement refined into detailed specs" |
| **DERIVE_REQT** | Source Req → Derived Req | "Child requirement derived from parent" |
| **COPY** | Source Element → Copy | "Element copied from another model" |

### Structural Relationships
| Relationship | Direction | Use Case |
|---|---|---|
| **COMPOSITION** | Parent → Child (owned) | "BrakeSystem composed of: PedalUnit, Cylinder, Lines" |
| **AGGREGATION** | Whole → Part (shared) | "Vehicle aggregates: Engine, Brake, Steering" |
| **ASSOCIATION** | Element ↔ Element | "Driver associates with Vehicle" |
| **GENERALIZATION** | Specific → General | "EmergencyBrake is a Brake (inheritance)" |
| **ALLOCATION** | Function → Component | "Stop functionality allocated to BrakeController" |

---

## 🎯 Using XMI Files for Customer Demo

### Step 1: Prepare XMI File
- Export your MBSE model from MagicDraw/Cameo as `.xmi` file
- Ensure it contains:
  - Requirements (as SysML `Requirement` stereotypes)
  - Architecture (Blocks, Components)
  - Traceability (satisfy, verify, trace relationships)
  - Use cases and interactions

### Step 2: Upload via Frontend
1. Navigate to **Data Import Pipeline** tab
2. Click **"+ Add Files"** or drag-and-drop your `.xmi` file
3. Select ontology mapping (optional, auto-detected as XMI)
4. Click **"▶ Start Pipeline"**

### Step 3: Monitor Import Progress
The pipeline shows 7 stages:
```
[1. Upload] → [2. Convert] → [3. Map] → [4. Validate] → [5. Enrich] → [6. Load] → [7. Verify]
```

Status indicators:
- 🟦 **In Progress** - Currently processing
- 🟩 **Complete** - Stage finished successfully
- 🟥 **Error** - Stage failed (check logs)

### Step 4: Review & Commit
- When "Verify" stage reaches 75% or completes, **"✓ Commit"** button appears
- Review preview (columns, sample rows, node count)
- Click **"✓ Confirm Import"** to ingest into Neo4j

### Step 5: Visualize in Graph View
After successful commit:
1. Switch to **Graph Visualization** tab
2. System will display:
   - ✅ All MBSE elements as nodes
   - ✅ Traceability relationships (edges labeled SATISFY, VERIFY, TRACE, etc.)
   - ✅ Contextual connections between entities
   - ✅ Full model hierarchy (COMPOSITION, AGGREGATION)

---

## 📈 Graph Visualization Features

### Node Display
- **Color-coded by type**: Requirements (blue), Activities (green), Blocks (purple), etc.
- **Labels**: Element name, ID, type
- **Hover details**: All properties, stereotype info, documentation

### Edge Display
- **Relationship labels**: Shows SATISFY, VERIFY, TRACE, REFINE, etc.
- **Edge colors**: Different colors for different relationship types
- **Interactive**: Click to highlight path, expand related nodes

### Search & Filter
- Search by element name, requirement ID, component type
- Filter by relationship type (show only SATISFY links, etc.)
- Zoom and pan for large models

---

## 🔧 Backend Configuration

### Import Master Path
- **Location**: `C:\Users\895428\Depo\import_master\`
- **Parser**: `ontologies/external/xmi_parser.py`
- **Status**: ✅ Configured and ready

### Neo4j Database
- Store for parsed MBSE models
- Supports complex graph queries
- Default query limits: 2000 nodes (configurable)

### API Endpoints
```
POST   /data-import/upload              → Upload XMI file
GET    /data-import/status/{taskId}     → Check progress
POST   /data-import/commit/{taskId}     → Commit to Neo4j
GET    /graphvis                        → Fetch full graph
POST   /graphfilter                     → Search/filter nodes
GET    /schema                          → Get graph schema
```

---

## 🎨 Customization for Customer

### To Show Only Traceability (MBSE Focus)
Add to `backend/main.py` `/graphvis` endpoint:
```python
# Filter to show only SysML elements with traceability relationships
WHERE labels(n) IN ['Requirement', 'Activity', 'UseCase', 'ConstraintBlock']
  AND any(rel IN relationships WHERE type(rel) IN 
    ['SATISFY', 'VERIFY', 'TRACE', 'REFINE', 'DERIVE_REQT'])
```

### To Highlight Entity Relationships
Update graph visualization styling in `GraphHEB.js`:
```javascript
// Color code relationships
const relationshipColors = {
  SATISFY: '#00AA00',      // Green
  VERIFY: '#0000FF',       // Blue
  TRACE: '#FF9900',        // Orange
  REFINE: '#9900FF',       // Purple
  DERIVE_REQT: '#FF0000',  // Red
  ALLOCATION: '#00FFFF',   // Cyan
};
```

---

## ✅ Next Steps

1. **Restart Backend**
   ```powershell
   cd C:\Users\895428\Depo_Onto_Engine\backend
   python main.py
   ```

2. **Test with Sample XMI**
   - Use a small MBSE model first (50-100 elements)
   - Verify Requirements and Traceability links appear
   - Show customer the graph visualization

3. **Validate Data Import**
   - Check Neo4j Browser: `MATCH (n:Requirement) RETURN count(n)`
   - Should return number of requirements in your XMI file

4. **Scale for Customer Demo**
   - Import larger models (500+ elements)
   - Show traceability chains (Req → Activity → Component)
   - Demonstrate search and filtering

---

## 📋 Troubleshooting

| Issue | Cause | Solution |
|---|---|---|
| "import_master not found" | Path configuration wrong | Verify `C:\Users\895428\Depo\import_master\src` exists |
| Empty graph after import | Parsing failed silently | Check backend logs: `backend/logs/error.log` |
| Timeouts (30s) | Neo4j query too slow | Reduce LIMIT in `/graphvis` or add indexes |
| Missing traceability | Relationships not extracted | Verify XMI has dependency/abstraction elements |

---

## 📞 Support

For issues:
1. Check backend logs: `backend/logs/app.log` and `backend/logs/error.log`
2. Verify Neo4j is running: `curl http://localhost:7687`
3. Test parser directly with sample XMI file
4. Review XMI export from MagicDraw/Cameo for correct SysML stereotypes

---

**Ready to import MBSE models! 🚀**
