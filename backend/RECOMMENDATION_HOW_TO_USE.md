# Recommendation Engine — How to Use Guide

## Overview

The Recommendation Engine provides three AI-powered analysis services that leverage the Neo4j knowledge graph to deliver actionable PLM insights. Each service can be accessed through **four entry points**: the Recommendations tab, node tooltips, the graph slide-in panel, and the chatbot.

---

## 1. Change Impact Analysis ⚡

### What It Does
Traces the ripple effect of a change request or any entity across the entire product structure:
- **Impacted Parts** — Parts linked via GeneralRelation (CMHasImpactedItem, CMHasProblemItem, CMHasSolutionItem)
- **Assembly Impact** — Assemblies affected via hasChildInstance tree traversal
- **Requirements** — Requirements connected via Seg0Satisfy / FND_TraceLink
- **Process Impact** — Processes in the same PLMXMLFile or connected via ProcessInstance chains
- **Realization Chain** — Entities linked via realizes / tracesTo / linkedTo / allocates
- **Impact Score** — Weighted 0–100 score reflecting overall severity

### How to Use

#### Via Recommendations Tab
1. Click the **⚡ Recommendations** tab at the bottom of the screen
2. Select the **⚡ Change Impact** card
3. Type a name in the search box (any Individual node name works):
   - Change requests: `Change the fit between bearing and shaft`
   - Parts: `Motor Cover Machined`, `id641`
   - Any entity: `SKF_6205_2Z7097_Deep Groove Ball Bearing`
4. Press **Enter** or click **Analyse**
5. Results appear in sections:
   - **Header** with entity name, type badge, and impact score bar
   - **🔎 View in Graph** button — switches to graph view and highlights all impacted nodes with gold pulsing rings
   - **🎯 Impact Radial View** — D3 concentric ring visualization showing Direct → Assembly → Requirements → Processes → Realization layers
   - **🔧 Impacted Parts** table
   - **🏗️ Assembly Impact** table
   - **📋 Requirements** table
   - **🏭 Process Impacts** table
   - **🔗 Realization Chain** table

#### Via Node Tooltip (Graph View)
1. Click any node in the graph
2. At the top of the tooltip, click **⚡ Impact**
3. A slide-in panel opens on the right side showing:
   - Impact score
   - Compact results (impacted parts, assemblies, processes)
   - **🔎 Highlight in Graph** button to mark affected nodes with gold rings

#### Via Chatbot
1. Open the chat panel (right side)
2. Ask in natural language:
   - *"What is the change impact of Change the fit between bearing and shaft?"*
   - *"Show me the impact analysis for Motor Cover Machined"*
   - *"What parts are affected by the bearing change?"*
3. The chatbot returns a formatted summary with counts for each impact category

### Example Inputs
| Input | Type | Expected Results |
|-------|------|-----------------|
| `Change the fit between bearing and shaft` | ChangeRequestRevision | 2 impacted parts, 46 assemblies, 466 processes |
| `First C2PC Request` | ChangeRequestRevision | Change-specific impacts |
| `Another CN` | ChangeNotice | Change notice impacts |
| `id641` | ProductInstance | Part-centric impact analysis |
| `SKF_6205_2Z7097_Deep Groove Ball Bearing` | ItemRevision | Part with 17 relationships |

### Understanding the Impact Score
| Score Range | Color | Meaning |
|------------|-------|---------|
| 0–40 | 🟢 Green | Low impact — few downstream effects |
| 41–70 | 🟡 Orange | Medium impact — moderate ripple effect |
| 71–100 | 🔴 Red | High impact — extensive cascading changes |

The score is computed from:
- Number of directly impacted parts (30% weight)
- Assembly tree depth and breadth (25%)
- Requirement count (20%)
- Process count (15%)
- Realization chain length (10%)

---

## 2. Similar Parts 🔍

### What It Does
Finds structurally and semantically similar parts using a multi-factor scoring algorithm:
- **sourceTag match** (20 pts) — Same entity type (e.g., both ItemRevision)
- **rflpLayer match** (15 pts) — Same RFLP layer
- **Assembly co-occurrence** (30 pts) — Appear in the same PLMXMLFile
- **Traceability links** (20 pts) — Connected via tracesTo / realizes / linkedTo / allocates
- **Name similarity** (15 pts) — Shared keywords in node name

### How to Use

#### Via Recommendations Tab
1. Select the **🔍 Similar Parts** card
2. Type a part name: `Rotor Shaft Machined`
3. Optionally adjust **Top N** (default: 10)
4. Press **Enter** or click **Analyse**
5. Results show:
   - Source part info with type badge
   - **🔎 View in Graph** button
   - Scored table with columns: Part Name, Score bar, Type Match ✅/—, RFLP Match, Assembly, Traceability

#### Via Node Tooltip
1. Click any node → click **🔍 Similar**
2. Slide-in panel shows top similar parts with score and badges

#### Via Chatbot
- *"What parts are similar to Rotor Shaft Machined?"*
- *"Find alternatives to Motor Flange"*
- *"Parts like Centrifugal Fan"*

### Example Inputs
| Input | Results |
|-------|---------|
| `Rotor Shaft Machined` | Rotor Shaft Key (score: 65), Flange_Machined, Motor Cover Machined |
| `Motor Cover Machined` | End Bell_Machined, Bearing Holder_Machined |
| `SKF_6205_2Z7097_Deep Groove Ball Bearing` | Similar bearing variants |
| `id641` | ProductInstances in the same assembly file |

### Reading the Score Breakdown
Each result shows which factors contributed:
- ✅ under **Type Match** = same sourceTag (20 pts)
- ✅ under **RFLP Match** = same rflpLayer (15 pts)
- ✅ under **Assembly** = shared PLMXMLFile (30 pts)
- Badge under **Traceability** = link type e.g., `realizes` (20 pts)
- Name keyword overlap is scored internally (15 pts max)

---

## 3. Manufacturing Process 🏭

### What It Does
Recommends manufacturing processes for a given part by traversing:
- **Direct processes** — Process nodes in the same PLMXMLFile
- **Process instances** — ProcessInstance chains via referencesProductInstance
- **Related-part processes** — Processes used on assembly siblings
- **Realization-chain processes** — Processes for parts connected via realizes/tracesTo

### How to Use

#### Via Recommendations Tab
1. Select the **🏭 Manufacturing Process** card
2. Type a part name: `INDUCTION MOTOR ASSY 5HP`
3. Press **Enter** or click **Analyse**
4. Results show:
   - Part info with Direct / Instance / Related counts
   - **🔎 View in Graph** button
   - **📊 Process Flow Timeline** — D3 vertical timeline grouped by type
   - **⚙️ Direct Processes** table
   - **🔄 Process Instances** table
   - **🔗 Related Part Processes** table
   - **📊 Process Type Summary** cards

#### Via Node Tooltip
1. Click any node → click **🏭 Process**
2. Slide-in panel shows process breakdown with highlight button

#### Via Chatbot
- *"What manufacturing processes are used for Motor Cover Machined?"*
- *"How is the Rotor Shaft made?"*
- *"Recommend processes for Laminated Stator Core"*

### Example Inputs
| Input | Direct | Instances | Related |
|-------|--------|-----------|---------|
| `INDUCTION MOTOR ASSY 5HP` | Varies | Multiple | Many |
| `Motor Cover Machined` | 0 | 1 | 49 |
| `Stator Core Welding` | Varies | Varies | Varies |
| `id641` | 0 | 2 | 49 |

---

## 4. "View in Graph" Feature

### What It Does
Highlights recommendation result nodes in the main D3 graph visualization with animated gold pulsing rings.

### How to Use
1. Run any analysis in the Recommendations tab
2. Click **🔎 View in Graph (N nodes)** in the result header
3. The app switches to the Graph View tab
4. Matched nodes appear with:
   - **Force-directed layout**: Gold dashed pulsing rings around nodes
   - **Tree layout**: Gold background highlight on matching rows
5. Highlights auto-clear after **15 seconds**

### From Slide-in Panel
1. Trigger analysis from a node tooltip (⚡/🔍/🏭)
2. In the slide-in panel results, click **🔎 Highlight in Graph**
3. The panel closes and matching nodes glow gold

---

## 5. Slide-in Panel

### What It Does
A compact right-side panel that shows recommendation results without leaving the graph view.

### How to Use
1. In the graph view, click any node
2. In the tooltip header, click ⚡ Impact, 🔍 Similar, or 🏭 Process
3. A 380px panel slides in from the right with:
   - Service name and entity name header
   - Loading spinner during analysis
   - Compact result summary
   - **🔎 Highlight in Graph** button
   - **✕** close button to dismiss

---

## 6. Chatbot Integration

### What It Does
The existing chatbot can invoke all three recommendation services via natural language.

### Supported Queries
| Query Pattern | Service Invoked |
|--------------|----------------|
| "What is the impact of [X]?" | Change Impact |
| "What parts are affected by [X]?" | Change Impact |
| "Show impact analysis for [X]" | Change Impact |
| "What parts are similar to [X]?" | Similar Parts |
| "Find alternatives to [X]" | Similar Parts |
| "Parts like [X]" | Similar Parts |
| "How is [X] manufactured?" | Manufacturing |
| "What processes for [X]?" | Manufacturing |
| "Recommend processes for [X]" | Manufacturing |

### Response Format
The chatbot returns a Markdown-formatted summary with:
- Entity name and type
- Counts for each impact/result category
- Top results listed with scores/types

---

## Tips & Troubleshooting

### Search is flexible
- You can search by **any** node name — not just Parts
- The search uses **case-insensitive CONTAINS** matching
- If multiple nodes match, the best fuzzy match is selected

### No results?
- Verify the node exists: search for it in the graph search bar first
- The node may have zero relationships (70K+ step-ap242 nodes are isolated)
- Try a more connected node like `SKF_6205_2Z7097_Deep Groove Ball Bearing`

### Performance
- Queries run against Neo4j Aura cloud — expect 1–5 second response times
- Assembly traversals are capped at depth 5 and 100 results
- Related processes are limited to 50 results to prevent timeouts

### API Endpoints (for developers)
| Endpoint | Method | Body |
|----------|--------|------|
| `/recommendations/change-impact` | POST | `{"change_name": "..."}` or `{"part_name": "..."}` |
| `/recommendations/similar-parts` | POST | `{"part_name": "...", "top_n": 10}` |
| `/recommendations/manufacturing` | POST | `{"part_name": "..."}` |
| `/recommendations/health` | GET | — |
