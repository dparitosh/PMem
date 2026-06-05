# Recommendation Engine Design — Feasibility & Architecture

## 1. Current Neo4j Schema (Verified from Live Database)

### Node Labels

| Label | Count | Key Properties |
|-------|-------|----------------|
| `OntologyClass` | 97 | uri, name, namespace, qname |
| `OntologyProperty` | 240 | uri, name, propType, domain, range |
| `Individual` | 81,448 | uri, name, source, namespace, prefix, local_name, qname + class-specific props |

### OntologyClass Instances (PLMXML namespace: `http://IAE-depo.com/plmxml-ontology#`)

| Class | Instances | Description |
|-------|-----------|-------------|
| UserData | 3,498 | Metadata attached to entities |
| Transform | 2,068 | 3D position/orientation matrices |
| ProductInstance | 1,327 | BOM tree nodes — assembly structure via `hasChildInstance` |
| ProductView | 899 | Product configurations |
| Part | 860 | Engineering parts, assemblies, change entities — discriminated by `sourceTag` |
| Form | 821 | Form data containers |
| ExternalFile | 429 | External file references |
| Process | 350 | Manufacturing processes and operations |
| ProcessInstance | 348 | Process execution instances |
| Document | 230 | Document references |
| Function | 207 | RFLP functional elements (F-layer) |
| ProcessView | 154 | Process structure views |
| PhysicalNode | 127 | RFLP physical architecture (P-layer) |
| GeneralRelation | 113 | Traceability link objects (typed by `traceSubType`) |
| LogicalComponent | 76 | RFLP logical components (L-layer) |
| Requirement | 31 | Engineering requirements (R-layer, with `catalogueId`) |
| PLMXMLFile | 8 | Source PLMXML files |

AP242 classes (namespace: `http://IAE-depo.com/ap242-bo#`): AP242 Assembly Occurrence (153), AP242 Part View (34), AP242 Part Version (34), AP242 Application Context (17), AP242 Part (17).

### Relationships Between Individuals

| Relationship | Count | Pattern |
|-------------|-------|---------|
| `contains` | 13,245 | PLMXMLFile → Part, ProductInstance, Process, etc. |
| `hasChildInstance` | 725 | ProductInstance → ProductInstance (assembly tree, max 4 levels) |
| `positionedBy` | 504 | ProductInstance → Transform |
| `referencesProductInstance` | 197 | ProcessInstance → ProductInstance (process→BOM linkage) |
| `source` | 118 | GeneralRelation → Part/Function/PhysicalNode |
| `target` | 103 | GeneralRelation → Part/Function/PhysicalNode/LogicalComponent |
| `tracesTo` | 37 | Part/Function → Part/Function (direct traceability) |
| `realizes` | 31 | Part/Function/PhysicalNode → Part/Function |
| `linkedTo` | 26 | Part → Part |
| `allocates` | 10 | Part → Part/Function |
| `INSTANCE_OF` | 11,922 | Individual → OntologyClass |
| `SUBCLASS_OF` | 85 | OntologyClass → OntologyClass |
| `DOMAIN` | 185 | OntologyProperty → OntologyClass |
| `RANGE` | 185 | OntologyProperty → OntologyClass |

### Datatype Properties by Class

| Class | Properties |
|-------|-----------|
| Part | `sourceTag`, `type`, `revision`, `rflpLayer`, `tcSubType`, `rawAttributes`, `Part_uid` |
| ProductInstance | `sourceTag`, `quantity`, `rawAttributes` |
| Requirement | `catalogueId`, `bodyText`, `revision`, `rflpLayer`, `lastModDate`, `objectString` |
| GeneralRelation | `traceSubType`, `tcLabel` |
| Process | `sourceTag`, `type`, `rawAttributes` |
| ProcessInstance | `sourceTag`, `rawAttributes` |
| Function | `sourceTag`, `revision`, `rflpLayer`, `tcSubType`, `type` |

### GeneralRelation Subtypes (Traceability Classification)

| traceSubType | Count | Purpose |
|-------------|-------|---------|
| FND_TraceLink | 35 | General traceability |
| Seg0Realize | 29 | Realization links |
| CMHasProblemItem | 18 | Change management — problem items |
| Seg0Satisfy | 14 | Requirement satisfaction |
| Seg0Allocate | 10 | Allocation links |
| CMHasImpactedItem | 4 | Change management — impacted items |
| CMHasSolutionItem | 3 | Change management — solution items |

### Key Design Patterns

**Part sourceTag discrimination:** The `Part` class (860) contains multiple entity types:
- `Item` / `ItemRevision` — actual engineering parts
- `ChangeNotice` / `ChangeNoticeRevision` / `ChangeRequestRevision` — change management entities
- `Mfg0MEResource` / `Mfg0MERevision` — manufacturing resources
- `Sys0PhysNodeComp` / `Sys0LogicalComp` — RFLP architecture nodes
- `Sys0PhysicalFunc` / `Sys0SystemFunc` — RFLP functions (also in Function class)

**Assembly tree:** `ProductInstance -[:hasChildInstance]-> ProductInstance`, max depth 4.

**Traceability:** `GeneralRelation` acts as a typed link object with `source` and `target` relationships. The `traceSubType` discriminates the link purpose.

**Change management:** Change entities are `Part` individuals with `sourceTag` = `ChangeNoticeRevision` or `ChangeRequestRevision`. Impacted items linked via `GeneralRelation` with `traceSubType='CMHasImpactedItem'` or `'CMHasProblemItem'`.

---

## 2. Recommendation Use Cases — Cypher Patterns

### Use Case A: Change Impact Recommendation

**Trigger:** Change request or notice entity name
**Output:** Impacted parts + requirements + assembly tree + processes

```cypher
// Find change entity
MATCH (cr:Individual)-[:INSTANCE_OF]->(:OntologyClass {name: 'Part'})
WHERE cr.sourceTag IN ['ChangeNoticeRevision', 'ChangeRequestRevision']
  AND cr.name CONTAINS $changeName

// Impacted parts via GeneralRelation
OPTIONAL MATCH (gr:Individual)-[:INSTANCE_OF]->(:OntologyClass {name: 'GeneralRelation'})
WHERE gr.traceSubType IN ['CMHasImpactedItem', 'CMHasProblemItem']
OPTIONAL MATCH (gr)-[:source]->(cr)
OPTIONAL MATCH (gr)-[:target]->(impacted:Individual)-[:INSTANCE_OF]->(:OntologyClass {name: 'Part'})

// Requirements satisfied by impacted parts (via Seg0Satisfy)
OPTIONAL MATCH (satGR:Individual {traceSubType: 'Seg0Satisfy'})-[:target]->(impacted)
OPTIONAL MATCH (satGR)-[:source]->(req:Individual)-[:INSTANCE_OF]->(:OntologyClass {name: 'Requirement'})

// Processes in same PLMXMLFile as impacted part
OPTIONAL MATCH (file:Individual)-[:contains]->(impacted)
OPTIONAL MATCH (file)-[:contains]->(proc:Individual)-[:INSTANCE_OF]->(:OntologyClass {name: 'Process'})

RETURN cr.name AS change_entity,
       collect(DISTINCT impacted.name) AS impacted_parts,
       collect(DISTINCT {req: req.name, catId: req.catalogueId}) AS requirements,
       collect(DISTINCT proc.name) AS affected_processes
```

### Use Case B: Similar Parts Recommendation

**Trigger:** Part name
**Scoring:** sourceTag match + RFLP layer + assembly co-occurrence + traceability links + name similarity

```cypher
MATCH (source:Individual)-[:INSTANCE_OF]->(:OntologyClass {name: 'Part'})
WHERE source.name = $partName AND source.sourceTag IN ['Item', 'ItemRevision']

// Parts in same PLMXMLFile (assembly siblings)
OPTIONAL MATCH (file:Individual)-[:contains]->(source)
OPTIONAL MATCH (file)-[:contains]->(sibling:Individual)-[:INSTANCE_OF]->(:OntologyClass {name: 'Part'})
WHERE sibling <> source AND sibling.sourceTag IN ['Item', 'ItemRevision']

// Parts connected via traceability
OPTIONAL MATCH (source)-[:tracesTo|realizes|linkedTo]-(connected:Individual)
  -[:INSTANCE_OF]->(:OntologyClass {name: 'Part'})
WHERE connected <> source

WITH source, collect(DISTINCT sibling) AS siblings, collect(DISTINCT connected) AS traced
// Score: assembly=30, trace=20, sourceTag=20, rflpLayer=15, name=15
```

### Use Case C: Manufacturing Process Recommendation

**Trigger:** Part name
**Output:** Processes from same PLMXMLFile + ProcessInstance chains + related part processes

```cypher
// Direct processes in same file
MATCH (p:Individual)-[:INSTANCE_OF]->(:OntologyClass {name: 'Part'})
WHERE p.name = $partName
MATCH (file:Individual)-[:contains]->(p)
MATCH (file)-[:contains]->(proc:Individual)-[:INSTANCE_OF]->(:OntologyClass {name: 'Process'})

// Process instances referencing the part's ProductInstance
OPTIONAL MATCH (file)-[:contains]->(bi:Individual)-[:INSTANCE_OF]->(:OntologyClass {name: 'ProductInstance'})
OPTIONAL MATCH (pi:Individual)-[:referencesProductInstance]->(bi)

RETURN proc.name AS process, proc.sourceTag AS process_type,
       collect(DISTINCT pi.name) AS process_instances
```

---

## 3. Data Availability Assessment

**What the graph CAN do today:**
- Change impact analysis via GeneralRelation (CMHasImpactedItem, CMHasProblemItem)
- Requirement traceability via GeneralRelation (Seg0Satisfy, FND_TraceLink)
- Assembly tree traversal via hasChildInstance (725 edges, 4 levels deep)
- Similar parts via assembly co-occurrence (PLMXMLFile contains) and traceability links
- Manufacturing process recommendation via file co-occurrence and ProcessInstance chains
- RFLP layer analysis (R→F→L→P via realizes, allocates, tracesTo)

**Limitations (no synthetic data needed — work with real data):**
- No material/geometry classification on part nodes (no `hasMaterial`, `hasGeometryClass`)
- No GD&T tolerance specs linked to parts (tolerances are in STEP AP242 entities, not linked to Part individuals)
- No machine/tooling/inspection entities
- No production run history or defect rates
- Change entities have limited properties (no crStatus, crPriority)
- Process entities have no cost/cycle time data

**Recommendation:** Build services using the EXISTING relationship patterns. Do not create synthetic data. Use graph traversal (assembly co-occurrence, traceability chains, file membership) as the primary scoring signals.
