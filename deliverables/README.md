# Deliverables

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
