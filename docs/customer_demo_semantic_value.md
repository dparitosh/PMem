# Customer Demo: Flexible Semantic Engineering Intelligence

## Demo Story

DEPO turns changing engineering data into a shared, traceable semantic model. The demo uses:

- AP242 or PLMXML ontology/schema data
- STEP/STPX or PLMXML instance data
- ReqIF requirements where available
- Neo4j for connected context and impact tracing
- Owlready2/RDFLib for ontology inspection and export
- Knowledge Companion for graph-grounded answers

The central message is:

> The customer does not need to redesign every integration when products change. They add or align new concepts, preserve provenance, and use the graph to trace the consequences.

## Prerequisites

1. Start Neo4j and verify the target database is configured.
2. Start the application stack:

```powershell
cd D:\Githuv_repo\PMem
powershell -NoProfile -ExecutionPolicy Bypass -File .\infra\deployment\invoke-depo-lifecycle.ps1 -Action Start -EnvFile .env.local
```

3. Open `http://localhost:3000/`.
4. Confirm these services before the demo:

```text
Frontend:  http://localhost:3000/
Graph:     http://localhost:8013/healthz
Ontology:  http://localhost:8011/healthz
Agentic:   http://localhost:8012/healthz
```

5. Use a clean demo database or a dedicated `demo` import identifier. Do not use **Clean Neo4j Schema** during a customer presentation unless the database is explicitly disposable.

## Demo Data

Representative files are available under:

```text
D:\FileHistory\Paritosh\DESKTOP-6V68C8J\Data\D\graphdb\DesktopDB\relate-data\dbmss\dbms-319603fc-d69d-4cf5-b4a4-9fbb86278426\import\SPLM
```

Recommended files:

```text
000687_A_1-INDUCTION MOTOR ASSY 5HP (...).stpx
000687_A_1-INDUCTIONMOTORASSY5 (...).xml
INDUCTION MOTOR ASSEMBLY 5HP (...).stp
DomainModel (...).xsd
```

Use the registered AP242 ontology in the application when available. Use ReqIF files for the requirements segment of the demo.

## Demo Sequence

### Ontology Junction Orientation

When introducing **Ontology Junction**, point out the visible three-step guide:

1. **Mapping Vocabulary**: standardize source terms and synonyms.
2. **Semantic Bridge**: connect imported data to ontology classes and properties.
3. **Inference Workbench**: preview conclusions derived from ontology rules.

Each step displays its next action and the output it produces. This gives the customer a task-oriented path before introducing OWL, RDF, or SWRL terminology.

### 1. Flexible Models When Products Change

**Customer problem:** Rigid data models require major redesign when a product or process evolves.

**UI steps:**

1. Open **Import**.
2. Select **Create ontology** for XSD, OWL, RDF, TTL, XMI, or EXPRESS schema input.
3. Add the AP242/XSD file and run the workflow through preview and registration.
4. Return to **Ontology Studio**.
5. Select the registered ontology from **Active Ontology**.
6. Open **Taxonomy / OWL** and show classes, properties, subclass hierarchy, domains, and ranges.
7. Use the export controls to show TTL, RDF, OWL, or JSON-LD output.

**What to show:**

- New classes and properties can be added through ontology registration and alignment.
- Existing graph data remains identifiable through stable business IDs and provenance.
- The ontology layer evolves independently from the instance graph and UI rendering.

**Customer message:**

> Product evolution becomes an ontology/versioning and mapping change instead of a full database redesign.

### 2. Shared Meaning and Controlled Vocabulary

**Customer problem:** Different systems use different terms for the same concept.

**UI steps:**

1. Open **Ontology Studio** and select the active ontology.
2. Select **1. Mapping Vocabulary** from the step guide.
3. Explain: “This is where different source terms are aligned to a shared vocabulary.”
4. Show source terms, target concepts, mapping type, and confidence.
5. Select **2. Semantic Bridge** from the step guide.
6. Select an instance term and an ontology class/property.
7. Create or review a mapping, then validate it against class, datatype, domain, and range rules.

**What to show:**

- One controlled ontology concept can represent variants from PLMXML, ReqIF, STEP, MBSE, or another source.
- Mapping evidence contains source, target, mapping type, confidence, validation state, and provenance.
- Ontology classes, data properties, object properties, and metadata mappings remain distinct.

**Customer message:**

> The platform separates a source system’s vocabulary from the enterprise meaning used for analysis.

### Optional Inference Workbench Demonstration

Use this short step immediately after Semantic Bridge when the customer wants to see ontology reasoning:

1. Select **3. Inference Workbench** from the step guide.
2. Choose rules such as transitive subclass, domain/range typing, or individual type closure.
3. Click **Run preview**.
4. Review the inferred statement table, evidence, confidence, and warnings.
5. Explain that this is a reviewable preview; inferred facts are not materialized into Neo4j without the appropriate approved workflow.

### 3. Automated Impact and Dependency Tracing

**Customer problem:** Change analysis requires manual investigation across many systems.

**UI steps:**

1. Open **Graph Explorer**.
2. Choose **Contextual Instances**.
3. Search for a known requirement, part, product, or business object such as `REQ-` or `Part`.
4. Select the exact matching node.
5. Expand one hop at a time to show connected requirements, functions, parts, processes, or documents.
6. Open **Where Used** for the selected business object.
7. Open **Recommendations** and run the change-impact scenario.

**Optional Knowledge Companion query:**

```text
What is the change impact of REQ-006 on its connected functions, parts, processes, and documents? Return the result as a traceability table with relationship type and source provenance.
```

**What to show:**

- The result is a connected contextual graph, not an unrelated full-graph dump.
- Relationships are named and traceable.
- Impact results identify upstream/downstream objects and relationship paths.
- The original source/import identifier remains available for audit.

**Customer message:**

> A change starts from one business object and follows explicit graph relationships instead of relying on manual spreadsheet investigation.

### 4. Explicit Cross-System Relationships

**Customer problem:** Connections between data are difficult to interpret.

**UI steps:**

1. Open **Graph Explorer** and choose **Full Graph** only for a small filtered slice.
2. Select the relevant ontology or source scope.
3. Search for `Part`, `Requirement`, or a known identifier.
4. Use the contextual view for readable one-hop exploration.
5. Click a relationship or node to inspect properties and provenance.
6. Use **Reports** to show relationship and XSD relational views where appropriate.

**What to show:**

- Raw relationship codes are displayed with meaningful labels where mappings exist.
- Each relationship has source and target endpoints.
- Business objects are shown as nodes; metadata-only XML tags are not treated as business objects.
- Domain/range and ontology property information explain why a relationship is valid.

**Customer message:**

> The graph is not only a picture. Every visible connection has a semantic type, endpoints, and provenance.

### 5. Domain Context for AI and GenAI

**Customer problem:** General AI can misinterpret engineering terms and relationships.

**UI steps:**

1. Open **Knowledge Companion** from the application header or graph tools.
2. Ask a domain-grounded question:

```text
Compare the impact of changing REQ-006 on the associated part, function, manufacturing process, and requirement relationships. Use only connected Neo4j context and state any missing evidence.
```

3. Ask for a structured result:

```text
Return: 1) direct impacts, 2) downstream impacts, 3) affected ontology concepts, 4) evidence paths, 5) unresolved references.
```

4. Ask a semantic question:

```text
What does the selected term mean in the active ontology, which class or property defines it, and which instance records use it?
```

5. For an external integration, use the chat API rather than calling Neo4j directly. The client should send a session identifier and user message, then handle the response asynchronously for long-running questions.

**What to show:**

- The assistant uses graph context and ontology terms rather than only keyword similarity.
- Answers can identify relationship paths and missing evidence.
- The assistant should state uncertainty when the graph lacks a required connection.
- No AI proposal should mutate Neo4j without an explicit approval workflow.

**Customer message:**

> Ontology and graph context constrain the answer, reducing unsupported interpretations and hallucinated engineering relationships.

## Optional OpenAPI Component Demo

1. Open **Admin**.
2. Open **Agentic Components**.
3. Click **Import OpenAPI JSON** in the top-right.
4. Select the customer API specification.
5. Show the normalized operation and schema catalog.
6. Explain that this catalog is available through the API for low-code/no-code orchestration.

API endpoint:

```http
POST http://localhost:8012/api/v1/openapi/import
```

The import inspects the specification only. It does not execute or register customer operations automatically.

## Suggested 20-Minute Timing

| Time | Demonstration |
|---:|---|
| 0-2 min | State the five customer problems |
| 2-6 min | Import/schema evolution and ontology view |
| 6-9 min | Mapping Vocabulary and Semantic Bridge |
| 9-11 min | Inference Workbench preview |
| 11-14 min | Contextual graph and one-hop expansion |
| 14-17 min | Where Used and Recommendations impact view |
| 17-19 min | Knowledge Companion graph-grounded question |
| 19-20 min | OpenAPI component catalog and close |

## Demo Acceptance Checklist

- [ ] Frontend, backend, Neo4j, and agentic adapter are healthy.
- [ ] Ontology is registered and selectable.
- [ ] Instance preview shows meaningful entities, not metadata-only XML tags.
- [ ] Semantic Bridge shows separate entity, attribute, relationship, and metadata mappings.
- [ ] Inference Workbench shows rule selection, preview results, evidence, and warnings.
- [ ] Contextual search returns connected instance nodes.
- [ ] One-hop expansion adds neighboring nodes without duplicates.
- [ ] Relationship labels and provenance are visible.
- [ ] Where Used returns business-object usage.
- [ ] Recommendation/change-impact output identifies evidence paths.
- [ ] Knowledge Companion answer states evidence and uncertainty.
- [ ] No destructive database action is used during the customer demo.

## Backup API Validation

If the UI is unavailable, validate the adapters without changing Neo4j:

```powershell
Invoke-RestMethod http://localhost:8000/health
Invoke-RestMethod http://localhost:8000/health/neo4j
Invoke-RestMethod http://localhost:8012/health
Invoke-RestMethod http://localhost:8012/api/v1/agents
Invoke-RestMethod http://localhost:8012/api/v1/tools
```

The API fallback should be used to diagnose a UI issue, not as a substitute for demonstrating the customer workflow.
