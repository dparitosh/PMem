# Deliverables

Current executive marketing bundle — updated 4 November 2026:

- [Business outcomes presentation](NEXUS-Business-Outcomes-Marketing.pptx): 22 slides with icons, diagrams and business outcomes.
- [Business brochure](NEXUS-Business-Outcomes-Marketing.docx): 8 pages, editable Word document.
- [Brochure PDF](NEXUS-Business-Outcomes-Marketing.pdf): visual reading copy; use Word for editable text.
- [Three-minute video script](NEXUS-Business-Outcomes-Video-Script.docx): six 30-second scenes with narration, captions and visual direction.

Dedicated coverage includes decision support, similarity, recommendations, a 360-degree product view, three memory perspectives, and the business value of services, workers, agents, skills and personas. Industry scenarios are applicability examples, not measured customer outcomes or certification claims. Approval remains an accountable human decision.

The DEPO-AI-Led-Engineering-Marketing filenames are compatibility copies of this current bundle. Earlier workflow and architecture decks below are background material and are not the current marketing deck.

## Earlier reference material



Earlier workflow presentation: [DEPO-Workflow-Audited.pptx](DEPO-Workflow-Audited.pptx).
The DEPO-AI-Led-Engineering-Marketing files now contain the current marketing bundle listed above.
Use these with the matching [Word brochure](DEPO-AI-Led-Engineering-Marketing.docx)
and [PDF brochure](DEPO-AI-Led-Engineering-Marketing.pdf), revised 3 November 2026.
Visible branding is Nexus; established filenames are retained for existing references.

The narrative starts from business decisions, user roles and functional journeys:
engineering change, part reuse, MBSE traceability, manufacturing/quality review,
controlled release, contextual conversation and reusable business analytics.
Dedicated HiTech, oil/gas, food/beverages and pharma scenarios are applicability
examples requiring customer records and reviewed mappings. Proposed pilot measures
are not measured ROI. The material does not claim sector certification or batch release.

The presentation includes 15 diagram slides and 82 native arrow/elbow connectors,
including business swimlanes, domain relationships, agent roles, contextual memory
and four industry workflows. The brochure includes four matching diagrams. Implementation references and capability boundaries are in speaker notes;
architecture internals do not lead the audience narrative. The six-page brochure
explains industry ontology in business terms and separates proposals, approvals and
released outcomes. The [demo user guide](../docs/DEMO-USER-GUIDE.md) remains the
presenter's operational companion.

Builders: `scripts/presentations/build_workflow_audited.mjs` and
`tools/documentation/build_marketing_literature.py`. Use bundled document/presentation
dependencies, validate exports and inspect every rendered slide/page before delivery.
Private renders and validation reports remain outside this folder.

The architecture decks below are background material; use the workflow deck
and current guide for demo instructions and known limitations.

The primary business presentation is
[DEPO Functional Architecture and Deployment](DEPO_Functional_Architecture_and_Deployment.pptx)
(18 slides, updated 21 October 2026). It covers engineering domains, the end-user
workflow, ontology/instance mapping, two dedicated MBSE slides, change impact,
agent contribution, data products, analytics and business ownership.

The Functional Architecture file has been replaced with the business-focused
version; it contains no technical deployment appendix. The same deck is also
available under [Business Domain and Functional Overview](DEPO_Business_Domain_and_Functional_Overview.pptx).
Engineering scenarios and KPI examples are illustrative, not measured results.

The dated analytics-release presentation and the other architecture decks are
historical or topic-specific references. They are not the current business deck.

Other retained presentations are historical or topic-specific references, not
installation instructions or evidence that the current customer environment
passes release acceptance. Environment reference documents describe settings;
use the repository's INSTALLATION.md for the installation sequence.

Keep generation sources reproducible. Generated build logs and browser review
output belong in ignored release-evidence directories rather than this folder.

The current presentation builder is `scripts/presentations/build_business_overview.mjs`.
It uses the bundled Artifact Tool runtime, reuses the current cover structure,
validates the editable business presentation and saves it under both names above.
Set `DEPO_ARTIFACT_MODULE`, `DEPO_PRESENTATION_SKILL_DIR`,
`DEPO_PRESENTATION_PYTHON` and `RUNTIME_NODE_MODULES` from the available runtime.
`DEPO_PRESENTATION_BUILD_ID` optionally selects a new private validation directory;
finalization does not overwrite an existing validated candidate. The older
`build_architecture.mjs` generates the historical technical narrative and should
not be used to regenerate the current business deck.

Environment reference generators are in `tools/documentation/`. Run
`python tools/documentation/expand_env_reference.py` from the repository root
with document-generation dependencies installed. Their output remains here.

## Final recorded demonstration

- [Combined live demonstration — 7 minutes](NEXUS-Final-Live-Demo.mp4), with [captions](NEXUS-Final-Live-Demo.srt) and [notes](NEXUS-Final-Live-Demo-Notes.txt). Includes Catalog, Data Products and Metadata Vocabulary, gentle piano without narration, and a five-second Change Impact reading pause.
- [PLMXML–AP242 merge review — 1 minute](NEXUS-PLMXML-AP242-Merge-Review.mp4), with [captions](NEXUS-PLMXML-AP242-Merge-Review.srt). Shows proposed matching scores; validation and publication are separate and were not completed in this recording.

Recordings use local demo evidence and preserve its underlying provenance. They do not establish customer approval, completed OWL-DL validation or materialized customer analytics.
