# Deliverables

The current consolidated architecture presentation is
[DEPO Functional Architecture and Deployment — analytics release](DEPO_Functional_Architecture_and_Deployment_2026-10-06_analytics_release.pptx).
It contains the service, agent/tool interaction and analytics-product slides.
Superseded intermediate decks were removed in the reviewed 2026-10-10 cleanup.

Other retained presentations are historical or topic-specific references, not
installation instructions or evidence that the current customer environment
passes release acceptance. Environment reference documents describe settings;
use the repository's INSTALLATION.md for the installation sequence.

Keep generation sources reproducible. Generated build logs and browser review
output belong in ignored release-evidence directories rather than this folder.

Environment reference generators are in `tools/documentation/`. Run
`python tools/documentation/expand_env_reference.py` from the repository root
with document-generation dependencies installed. Their output remains here.
