# Recommendation Services Development Prompt

Use the following prompt to develop the three recommendation services.

---

## Prompt

```
You are building a Python recommendation engine for an industrial PLM (Product Lifecycle Management) system.
The system uses Neo4j as its graph database, with an ontology derived from PLMXML, STEP AP242, and OWL.

### Architecture Context
- Python 3.11+ with FastAPI
- Neo4j graph database via langchain_neo4j.Neo4jGraph
- Existing project at: backend/
- API endpoints in: backend/main.py (add to existing FastAPI app)
- Service logic in: backend/Services/
- Neo4j client: backend/core/graph.py (exports `graph` object, use `graph.query(cypher, params={})`)
- LLM/Embeddings: backend/core/llm.py (Ollama via Azure API Manager proxy)
- Config: backend/.env with NEO4J_URI, NEO4J_USER, NEO4J_PASS, NEO4J_DATABASE
- LLM endpoint: http://azdtapimanager.azure-api.net/ollama (model: llama3.1:8b)
- Embeddings: nomic-embed-text:latest via same Ollama proxy

### Neo4j Graph Schema (real loaded data from PLMXML + STEP AP242)

Key relationship patterns between Individual nodes:
- (ProductInstance)-[:hasChildInstance]->(ProductInstance)     // assembly tree (725 edges, up to 4 levels)
- (GeneralRelation)-[:source]->(Part|Function|PhysicalNode)   // traceability source (118)
- (GeneralRelation)-[:target]->(Part|Function|PhysicalNode)   // traceability target (103)
- (Part)-[:tracesTo]->(Part|Function)                         // direct traceability (37)
- (Part)-[:realizes]->(Part|Function)                         // realization links (31)
- (Part)-[:linkedTo]->(Part)                                  // general part links (26)
- (Part)-[:allocates]->(Part|Function)                        // allocation (10)
- (ProcessInstance)-[:referencesProductInstance]->(ProductInstance) // process→BOM (197)
- (PLMXMLFile)-[:contains]->(Part|ProductInstance|Process|...) // file membership (13,245)

All data uses the standard OWL-to-Neo4j mapping. There are NO separate
labels like :Requirement, :TestCase, :ManufacturingProcess. Everything flows
through the three core node labels.

**Core node labels:**
- (:OntologyClass {uri, name, namespace, qname}) — owl:Class declarations (97 total)
- (:OntologyProperty {uri, name, propType, domain, range}) — property declarations (240 total)
- (:Individual {uri, name, ...datatype_props}) — every entity instance (81,448 total)

**Core structural relationships:**
- (Individual)-[:INSTANCE_OF]->(OntologyClass)  — rdf:type (11,922)
- (OntologyClass)-[:SUBCLASS_OF]->(OntologyClass) — class hierarchy (85)
- (OntologyProperty)-[:DOMAIN]->(OntologyClass)  — property domain (185)
- (OntologyProperty)-[:RANGE]->(OntologyClass)   — property range (185)

**OntologyClass nodes with instances** (namespace: `http://IAE-depo.com/plmxml-ontology#`):

| Class | Instances | Description |
|-------|-----------|-------------|
| Part | 861 | Parts, assemblies, materials, functions — discriminated by `sourceTag` |
| ProductInstance | 1,327 | BOM tree nodes (assembly structure via `hasChildInstance`) |
| Requirement | 31 | Engineering requirements (RFLP R-layer, with `catalogueId`) |
| GeneralRelation | 113 | Traceability link objects (classified by `traceSubType`) |
| Process | 350 | Manufacturing processes and operations |
| ProcessInstance | 348 | Process execution instances |
| Function | 207 | RFLP functional elements (F-layer) |
| PhysicalNode | 127 | RFLP physical architecture (P-layer) |
| LogicalComponent | 76 | RFLP logical components (L-layer) |
| PLMXMLFile | 8 | Source PLMXML files |

> **Change management:** ChangeNotice/ChangeRequest entities are stored as `Part`
> individuals with `sourceTag` = `'ChangeNotice'`, `'ChangeNoticeRevision'`, or
> `'ChangeRequestRevision'`. They link to impacted parts via `GeneralRelation` with
> `traceSubType='CMHasImpactedItem'` or `'CMHasProblemItem'`.

> **Assembly tree direction:** `hasChildInstance` links **parent** ProductInstance
> to **child**. Walk upward with `(child)<-[:hasChildInstance]-(parent)`. Max depth = 4.

> **Traceability:** `GeneralRelation` individuals have `source` and `target` relationships.
> The `traceSubType` property classifies the link:
> `FND_TraceLink` (35), `Seg0Realize` (29), `CMHasProblemItem` (18),
> `Seg0Satisfy` (14), `Seg0Allocate` (10), `CMHasImpactedItem` (4),
> `CMHasSolutionItem` (3).

**Datatype properties (stored as node properties on Individual nodes):**

- Part: `name`, `sourceTag`, `type`, `revision`, `rflpLayer`, `tcSubType`, `rawAttributes`, `Part_uid`
- ProductInstance: `name`, `sourceTag`, `quantity`, `rawAttributes`
- Requirement: `name`, `catalogueId`, `bodyText`, `revision`, `rflpLayer`, `lastModDate`, `objectString`
- GeneralRelation: `name`, `traceSubType`, `tcLabel`
- Process: `name`, `sourceTag`, `type`, `rawAttributes`
- ProcessInstance: `name`, `sourceTag`, `rawAttributes`
- Function: `name`, `sourceTag`, `revision`, `rflpLayer`, `tcSubType`, `type`
- Standard on every Individual: `uri`, `name`, `source`, `namespace`, `prefix`, `local_name`, `qname`

**IMPORTANT QUERY PATTERNS:**
```cypher
// Find all Part individuals
MATCH (p:Individual)-[:INSTANCE_OF]->(:OntologyClass {name: 'Part'})
RETURN p.name, p.sourceTag

// Find only "real" parts (not functions/change entities)
MATCH (p:Individual)-[:INSTANCE_OF]->(:OntologyClass {name: 'Part'})
WHERE p.sourceTag IN ['Item', 'ItemRevision']

// Find ChangeRequest/ChangeNotice entities
MATCH (cr:Individual)-[:INSTANCE_OF]->(:OntologyClass {name: 'Part'})
WHERE cr.sourceTag IN ['ChangeNotice', 'ChangeNoticeRevision', 'ChangeRequestRevision']

// Parts impacted by a change (via GeneralRelation)
MATCH (cr:Individual)-[:INSTANCE_OF]->(:OntologyClass {name: 'Part'})
WHERE cr.sourceTag = 'ChangeRequestRevision' AND cr.name = $changeName
MATCH (gr:Individual)-[:INSTANCE_OF]->(:OntologyClass {name: 'GeneralRelation'})
WHERE gr.traceSubType IN ['CMHasImpactedItem', 'CMHasProblemItem']
MATCH (gr)-[:source]->(cr)
MATCH (gr)-[:target]->(impacted:Individual)
RETURN impacted.name, gr.traceSubType

// Assembly tree — find all children
MATCH (parent:Individual)-[:hasChildInstance*1..4]->(child:Individual)
WHERE parent.name = $instanceName

// Requirements satisfied by a part (via GeneralRelation Seg0Satisfy)
MATCH (gr:Individual)-[:INSTANCE_OF]->(:OntologyClass {name: 'GeneralRelation'})
WHERE gr.traceSubType = 'Seg0Satisfy'
MATCH (gr)-[:source]->(req:Individual)-[:INSTANCE_OF]->(:OntologyClass {name: 'Requirement'})
MATCH (gr)-[:target]->(part:Individual)-[:INSTANCE_OF]->(:OntologyClass {name: 'Part'})
RETURN req.name, req.catalogueId, part.name

// Process plan for a ProductInstance
MATCH (pi:Individual)-[:INSTANCE_OF]->(:OntologyClass {name: 'ProcessInstance'})
MATCH (pi)-[:referencesProductInstance]->(bi:Individual)
RETURN pi.name, bi.name

// Processes in same file as a part
MATCH (file:Individual)-[:contains]->(p:Individual)-[:INSTANCE_OF]->(:OntologyClass {name: 'Part'})
WHERE p.name = $partName
MATCH (file)-[:contains]->(proc:Individual)-[:INSTANCE_OF]->(:OntologyClass {name: 'Process'})
RETURN proc.name, proc.sourceTag
```

### Task: Build three recommendation services

#### Service 1: ChangeImpactRecommender
File: Services/change_impact_recommender.py

Given a change entity name OR a part name, traverse the graph to find:
1. **Impacted parts** — via GeneralRelation with `traceSubType` in [`CMHasImpactedItem`, `CMHasProblemItem`, `CMHasSolutionItem`]
2. **Assembly impact** — find ProductInstances containing the impacted part, walk `hasChildInstance` tree upward to find top-level assemblies
3. **Impacted requirements** — via GeneralRelation with `traceSubType='Seg0Satisfy'` or `'FND_TraceLink'`
4. **Process impact** — via `contains` from same PLMXMLFile, and ProcessInstance → `referencesProductInstance`
5. **Propagated impacts** — follow assembly tree (hasChildInstance reverse) up to 4 levels
6. **Realization chain** — via `realizes` and `tracesTo` to find related Functions and Parts

Example Cypher:
```cypher
// Find change entity and impacted parts
MATCH (cr:Individual)-[:INSTANCE_OF]->(:OntologyClass {name: 'Part'})
WHERE cr.sourceTag IN ['ChangeNoticeRevision', 'ChangeRequestRevision']
  AND cr.name CONTAINS $changeName
OPTIONAL MATCH (gr:Individual)-[:source]->(cr)
OPTIONAL MATCH (gr)-[:target]->(impacted:Individual)-[:INSTANCE_OF]->(:OntologyClass {name: 'Part'})
WHERE gr.traceSubType IN ['CMHasImpactedItem', 'CMHasProblemItem']

// Requirements satisfied by impacted parts
OPTIONAL MATCH (satGR:Individual {traceSubType: 'Seg0Satisfy'})-[:target]->(impacted)
OPTIONAL MATCH (satGR)-[:source]->(req:Individual)-[:INSTANCE_OF]->(:OntologyClass {name: 'Requirement'})

RETURN cr.name, collect(DISTINCT impacted.name), collect(DISTINCT req.name)
```

Return a structured dict with:
```python
{
    "change_entity": {"name": str, "source_tag": str, "revision": str},
    "impacted_parts": [{"name": str, "source_tag": str, "relation_type": str}],
    "assembly_impact": [{"assembly_name": str, "depth": int}],
    "impacted_requirements": [{"name": str, "catalogue_id": str, "body_text": str}],
    "process_impacts": [{"process_name": str, "source_tag": str}],
    "realization_chain": [{"name": str, "link_type": str}],
    "impact_score": float  # 0-100 based on breadth of impact
}
```

#### Service 2: SimilarPartsRecommender
File: Services/similar_parts_recommender.py

Given a part name, find similar parts using weighted multi-factor scoring:
- **sourceTag match** (20 points) — same sourceTag (same entity type)
- **rflpLayer match** (15 points) — same RFLP layer
- **Assembly co-occurrence** (30 points) — in same PLMXMLFile or sibling ProductInstances
- **Traceability co-occurrence** (20 points) — connected via `tracesTo`, `realizes`, `linkedTo`
- **Name similarity** (15 points) — shared keywords in part name

Example Cypher:
```cypher
MATCH (source:Individual)-[:INSTANCE_OF]->(:OntologyClass {name: 'Part'})
WHERE source.name = $partName AND source.sourceTag IN ['Item', 'ItemRevision']

// Assembly siblings (parts in same PLMXMLFile)
OPTIONAL MATCH (file:Individual)-[:contains]->(source)
OPTIONAL MATCH (file)-[:contains]->(sibling:Individual)-[:INSTANCE_OF]->(:OntologyClass {name: 'Part'})
WHERE sibling <> source AND sibling.sourceTag IN ['Item', 'ItemRevision']

// Traceability connections
OPTIONAL MATCH (source)-[:tracesTo|realizes|linkedTo]-(connected:Individual)
WHERE connected <> source

// Score and return
```

Return top-N results sorted by score:
```python
{
    "source_part": {"name": str, "source_tag": str, "rflp_layer": str},
    "similar_parts": [
        {
            "name": str,
            "similarity_score": float,
            "source_tag_match": bool,
            "rflp_layer_match": bool,
            "shared_assembly": bool,
            "traceability_link": str,  # null or link type
        }
    ]
}
```

#### Service 3: ManufacturingProcessRecommender
File: Services/manufacturing_process_recommender.py

Given a part name, recommend manufacturing processes based on:
1. **Direct process linkage** — find Process individuals in the same PLMXMLFile as the part
2. **ProcessInstance chain** — ProcessInstance → `referencesProductInstance` → ProductInstance for the part
3. **Process type classification** — group by `sourceTag` (Operation, OperationRevision, ProcessRevision, Process)
4. **Related processes for similar parts** — use SimilarParts to find processes used on related parts
5. **RFLP realization** — if part has `realizes` links, check processes for realized parts too

Example Cypher:
```cypher
MATCH (p:Individual)-[:INSTANCE_OF]->(:OntologyClass {name: 'Part'})
WHERE p.name = $partName
MATCH (file:Individual)-[:contains]->(p)
MATCH (file)-[:contains]->(proc:Individual)-[:INSTANCE_OF]->(:OntologyClass {name: 'Process'})
OPTIONAL MATCH (file)-[:contains]->(bi:Individual)-[:INSTANCE_OF]->(:OntologyClass {name: 'ProductInstance'})
OPTIONAL MATCH (pi:Individual)-[:referencesProductInstance]->(bi)
RETURN proc.name AS process, proc.sourceTag AS process_type,
       collect(DISTINCT pi.name) AS process_instances
```

Return:
```python
{
    "part": {"name": str, "source_tag": str},
    "direct_processes": [
        {"name": str, "type": str, "source_tag": str}
    ],
    "process_instances": [
        {"name": str, "references_instance": str}
    ],
    "related_part_processes": [
        {"part_name": str, "process_name": str, "similarity_score": float}
    ]
}
```

### API Router
File: backend/main.py (add endpoints to existing FastAPI app)

Add endpoints to the existing `app` object with prefix pattern:
- POST /recommendations/change-impact  — body: {change_name: str} or {part_name: str}
- POST /recommendations/similar-parts  — body: {part_name: str, top_n: int = 10}
- POST /recommendations/manufacturing  — body: {part_name: str}
- GET  /recommendations/health         — returns service status and Neo4j node counts

### Requirements
- Use `graph` from `core.graph` for all DB access (pattern: `graph.query(cypher, params={})`) 
- Use parameterized Cypher queries (no string concatenation)
- Handle missing data gracefully (return partial results, not errors)
- Add logging with Python's logging module
- Each service should be a class with a constructor taking the `graph` object
- Include docstrings on public methods
- Test with real data:
  - Change impact: "Change the fit between bearing and shaft" (ChangeRequestRevision)
  - Similar parts: "Rotor Shaft Machined" (ItemRevision)
  - Manufacturing: "Motor Cover Machined" → find Die Casting, CNC processes
```

---

## Quick-Start After Services Are Built

```bash
# 1. Load the unified ontology into Neo4j (if not already done)
python direct_ttl_to_neo4j.py output/unified_plmxml_step_ap242/unified_plmxml_step_ap242.ttl

# 2. Start the API
python start_api.py

# 3. Test change impact
curl -X POST http://localhost:8000/recommendations/change-impact \
     -H "Content-Type: application/json" \
     -d '{"change_name": "Change the fit between bearing and shaft"}'

# 4. Test similar parts
curl -X POST http://localhost:8000/recommendations/similar-parts \
     -H "Content-Type: application/json" \
     -d '{"part_name": "Rotor Shaft Machined", "top_n": 5}'

# 5. Test manufacturing recommendation
curl -X POST http://localhost:8000/recommendations/manufacturing \
     -H "Content-Type: application/json" \
     -d '{"part_name": "Motor Cover Machined"}'
```

## Expected Results (Based on Real Data)

**Change Impact for "Change the fit between bearing and shaft":**
- Source: ChangeRequestRevision individual
- Impacted parts via CMHasImpactedItem/CMHasProblemItem: INDUCTION MOTOR ASSY 5HP and related
- Requirements: REQ-000024 (Low Bearing Noise/Vibration), REQ-000027 (Bearing Life)
- Assembly tree: ProductInstance hierarchy up to 4 levels deep
- Process impact: Manufacturing processes from the BoP PLMXML

**Similar Parts to "Rotor Shaft Machined":**
- Parts in same PLMXML file with sourceTag=ItemRevision
- Parts connected via tracesTo/realizes/linkedTo
- Parts sharing assembly siblings in the ProductInstance tree

**Manufacturing for "Motor Cover Machined":**
- Die Casting Preparatory Process (ProcessRevision)
- Die-Casting (OperationRevision)
- Load Motor Cover on Electric Oven (Operation)
- Related ProcessInstances with referencesProductInstance links

## Real Data Summary

| Entity Type | Count | Key Properties |
|-------------|-------|----------------|
| Part | 860 | name, sourceTag, revision, rflpLayer, tcSubType |
| ProductInstance | 1,327 | name, quantity, sourceTag |
| Requirement | 31 | name, catalogueId, bodyText, revision |
| GeneralRelation | 113 | traceSubType, tcLabel |
| Process | 350 | name, sourceTag, type |
| ProcessInstance | 348 | name, sourceTag |
| Function | 207 | name, sourceTag, rflpLayer |
| PhysicalNode | 127 | name, sourceTag |
| LogicalComponent | 76 | name, sourceTag |

| Relationship | Count | Pattern |
|-------------|-------|---------|
| contains | 13,245 | PLMXMLFile → various entities |
| hasChildInstance | 725 | ProductInstance → ProductInstance |
| positionedBy | 504 | ProductInstance → Transform |
| referencesProductInstance | 197 | ProcessInstance → ProductInstance |
| source | 118 | GeneralRelation → Part/Function/PhysicalNode |
| target | 103 | GeneralRelation → Part/Function/PhysicalNode |
| tracesTo | 37 | Part/Function → Part/Function |
| realizes | 31 | Part/Function/PhysicalNode → Part/Function |
| linkedTo | 26 | Part → Part |
| allocates | 10 | Part → Part/Function |

| GeneralRelation Subtype | Count | Purpose |
|------------------------|-------|---------|
| FND_TraceLink | 35 | General traceability |
| Seg0Realize | 29 | Realization links |
| CMHasProblemItem | 18 | Change mgmt — problem items |
| Seg0Satisfy | 14 | Requirement satisfaction |
| Seg0Allocate | 10 | Allocation links |
| CMHasImpactedItem | 4 | Change mgmt — impacted items |
| CMHasSolutionItem | 3 | Change mgmt — solution items |
