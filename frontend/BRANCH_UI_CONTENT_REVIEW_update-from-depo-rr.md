# Branch UI Content Review

Branch: `update-from-depo-rr`
Review date: `2026-06-07`
Reviewer lens: `PLM / Digital Thread / Ontology UX`
Environment reviewed: local branch UI at `http://localhost:3000`

## Executive Summary

This branch presents strong domain intent, but most pages are carrying too much explanatory text before users reach the actual working surface. The experience currently reads more like an architecture presentation than an operational PLM workbench.

The main pattern is repeated across `Workspace`, `Import`, `Ontology Studio`, `Graph Explorer`, `Quality`, `Reports`, and `Admin`:

- large strategic page title
- long summary paragraph
- three insight callouts
- another explanatory subtitle
- then dense grid or tabular content

For expert users, especially PLM, digital thread, and ontology users, this creates unnecessary reading overhead and pushes the actionable controls too far down the page.

## Highest-Priority Findings

### 1. Page headers are over-explaining the product story

Affected screens:

- `Workspace`
- `Import`
- `Ontology Studio`
- `Graph Explorer`
- `Quality`
- `Reports`
- `Admin`

Pattern observed:

- eyebrow label
- long title
- long summary sentence
- three insight blocks with additional prose

Impact:

- consumes too much vertical space
- delays access to the real task surface
- repeats information that power users will learn once, not every visit
- makes every page feel equally important and equally verbose

Recommendation:

- keep only `title + one-line summary`
- move insights into optional help, tooltip, or collapsible guidance
- reserve long framing text for landing/help pages, not operational pages

### 2. Workspace and reports tables are too dense for first-pass interpretation

Observed in:

- `Workspace` current graph table
- `Reports` workbench
- `Admin` registries

Impact:

- raw graph-style data appears before business framing
- users see technical rows and many columns without hierarchy
- difficult to scan for PLM questions such as product scope, ontology coverage, or traceability status

Recommendation:

- show curated summary rows first
- reduce default visible columns
- use business-friendly labels
- separate expert-detail mode from default review mode

### 3. Some grid headers expose raw field names instead of user-facing labels

Observed example:

- `Workspace > Digital Thread Operating Model`
- visible headers include `Product_value`, `System_of_record`, and `Current_state`

Impact:

- looks unfinished
- breaks enterprise UI polish
- weakens trust in the semantic/governance positioning

Recommendation:

- explicitly set `headerName` for every user-visible grid column
- avoid underscore-based field names in rendered headers

### 4. Import page has the heaviest content stack

Observed in `Import`:

- strategic page header
- policy grid
- workflow workbench
- many workflow cards with long descriptions
- format lists inside each card

Impact:

- users must read too much before acting
- workflow cards compete equally for attention
- branch already contains too many concepts on one screen: import, ontology creation, linking, merge, validation, dictionary, taxonomy, chunking

Recommendation:

- split into primary actions and advanced actions
- shorten each workflow card to one sentence plus file family badges
- hide advanced workflows behind `More workflows`

### 5. Reports page is information-rich but cognitively overloaded

Observed in `Reports`:

- large page framing text
- multiple report tabs
- 27 visible columns
- technical uppercase column labels
- filter surface and export surface at the same time

Impact:

- strong for debugging
- weak for review and decision-making
- hard to identify the few fields that matter for ontology governance or digital thread auditing

Recommendation:

- define default report views by persona:
  - ontology governance
  - import lineage
  - graph quality
  - traceability
- cap default visible columns to 6-8
- move full technical schema into optional column expansion

## Page-by-Page Notes

### Home / Landing

What works:

- immediately signals domain and graph context
- ontology and relationship metrics are useful

What needs attention:

- title is long
- page carries several metric tables at once
- assistant prompt list adds more vertical density

### Workspace

What works:

- good digital thread framing
- KPIs and action cards are relevant

What needs attention:

- header text is too long
- operating model table uses raw header labels
- current graph table opens with low-level technical relationships rather than business-relevant summary

### Import

What works:

- broad coverage of engineering onboarding scenarios
- branch correctly recognizes ontology and instance work as different flows

What needs attention:

- too many workflow choices on one surface
- cards are text-heavy
- import strategy is repeated in header, grid, and workbench card descriptions

### Ontology Studio

What works:

- domain positioning is clear
- AP242/AP239 alignment message is relevant

What needs attention:

- page header still too long for repeat use
- screen needs stronger prioritization between mapping, namespace governance, dictionary, and harmonization

### Graph Explorer

What works:

- graph modes and ontology selection are clear
- action-oriented surface is stronger than most other pages

What needs attention:

- still carries more framing text than needed
- top-of-page copy should be reduced because the graph already explains the page purpose

### Quality

What works:

- recommendation areas are sensible
- governance framing is appropriate

What needs attention:

- quality header is conceptually strong but too verbose
- recommendation sections and sub-tabs will benefit from shorter summaries and more direct task framing

### Reports

What works:

- evidence and lineage positioning is strong

What needs attention:

- most overloaded screen in terms of tabs, columns, filters, and metadata
- not enough distinction between executive review view and technical export view

### Admin

What works:

- good separation between operations and registry intent

What needs attention:

- header is too long for a control-room page
- multiple wide registries create a heavy reading burden
- platform metadata should be progressively disclosed, not shown at equal weight

## Content Strategy Recommendations

### Default rule for every operational page

- one short title
- one short summary
- zero or one contextual hint
- action surface immediately visible

### Recommended copy style

- use verbs users act on: `Import`, `Map`, `Validate`, `Review`, `Publish`
- reduce architecture language in repeated page headers
- replace abstract phrases like `trusted engineering evidence` with task-specific outcomes

### Recommended table strategy

- default to concise business labels
- reduce initial visible columns
- group advanced technical columns under optional expansion
- prefer summary cards before raw rows

## Suggested Next Cleanup Order

1. Simplify shared page header usage across all pages.
2. Fix raw grid header labels in workspace and similar tables.
3. Reduce visible default columns and copy density on Reports.
4. Split Import workflows into primary versus advanced actions.
5. Rework Workspace table default view toward business-readable traceability summaries.

